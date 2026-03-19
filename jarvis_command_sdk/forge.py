"""Forge spec generator — introspects SDK interfaces to produce authoring documentation.

Walks all SDK interface classes, reads their type hints, docstrings, abstract methods,
and __forge_hints__ metadata to produce a structured JSON spec. This spec is used by
the Forge (AI-powered package builder) as system prompt context.

Usage:
    from jarvis_command_sdk.forge import generate_spec
    spec = generate_spec()  # returns JSON-serializable dict
"""

from __future__ import annotations

import inspect
from dataclasses import fields, is_dataclass
from typing import Any, get_type_hints

from .agent import AgentSchedule, Alert, IJarvisAgent
from .authentication import AuthenticationConfig
from .button import IJarvisButton
from .command import CommandExample, IJarvisCommand
from .device_manager import DeviceManagerDevice, IJarvisDeviceManager
from .device_protocol import DeviceControlResult, DiscoveredDevice, IJarvisDeviceProtocol
from .package import JarvisPackage
from .parameter import JarvisParameter
from .request import RequestInformation
from .response import CommandResponse
from .secret import JarvisSecret
from .validation import ValidationResult

# The four main interface classes authors implement
INTERFACE_CLASSES: list[type] = [
    IJarvisCommand,
    IJarvisAgent,
    IJarvisDeviceProtocol,
    IJarvisDeviceManager,
]

# Supporting dataclasses/classes authors use in their implementations
SUPPORTING_CLASSES: list[type] = [
    CommandResponse,
    JarvisParameter,
    JarvisSecret,
    CommandExample,
    AgentSchedule,
    Alert,
    AuthenticationConfig,
    DiscoveredDevice,
    DeviceControlResult,
    DeviceManagerDevice,
    RequestInformation,
    ValidationResult,
    JarvisPackage,
    IJarvisButton,
]

# Manifest YAML schema — the source of truth for jarvis_command.yaml / jarvis_package.yaml
MANIFEST_SCHEMA: dict[str, Any] = {
    "description": (
        "The manifest file (jarvis_command.yaml or jarvis_package.yaml) declares "
        "package metadata, parameters, secrets, and components. It lives at the "
        "repo root alongside the source code."
    ),
    "filenames": ["jarvis_command.yaml", "jarvis_package.yaml"],
    "fields": {
        "schema_version": {"type": "int", "default": 1, "description": "Manifest schema version"},
        "name": {"type": "string", "required": True, "description": "Package name (snake_case, unique)"},
        "display_name": {"type": "string", "required": True, "description": "Human-readable name for UI display"},
        "description": {"type": "string", "required": True, "description": "What this package does (1-2 sentences)"},
        "version": {"type": "string", "required": True, "description": "Semantic version (e.g., '1.0.0')"},
        "author": {
            "type": "object",
            "description": "Author info",
            "fields": {
                "github": {"type": "string", "required": True, "description": "GitHub username"},
            },
        },
        "keywords": {
            "type": "list[string]",
            "description": "Keywords for search/discovery (also used for voice command routing)",
        },
        "categories": {
            "type": "list[string]",
            "description": "Category tags for browsing",
            "valid_values": [
                "automation", "calendar", "communication", "entertainment", "finance",
                "fitness", "food", "games", "health", "home", "information", "media",
                "music", "news", "productivity", "shopping", "smart-home", "sports",
                "travel", "utilities", "weather",
            ],
        },
        "platforms": {
            "type": "list[string]",
            "description": "Supported platforms (empty = all). Values: 'darwin', 'linux', 'win32'",
        },
        "parameters": {
            "type": "list[object]",
            "description": "Parameters the LLM extracts from voice input",
            "item_fields": {
                "name": {"type": "string", "required": True},
                "param_type": {
                    "type": "string", "required": True,
                    "valid_values": ["string", "int", "float", "bool", "enum", "date", "time", "datetime"],
                },
                "description": {"type": "string"},
                "required": {"type": "bool", "default": False},
                "default_value": {"type": "any"},
                "enum_values": {"type": "list[string]", "description": "Only for param_type='enum'"},
            },
        },
        "secrets": {
            "type": "list[object]",
            "description": "API keys, URLs, and config values stored encrypted on the node",
            "item_fields": {
                "key": {"type": "string", "required": True, "description": "Unique key (e.g., 'WEATHER_API_KEY')"},
                "scope": {"type": "string", "required": True, "valid_values": ["integration", "node"]},
                "value_type": {"type": "string", "required": True, "valid_values": ["string", "int", "bool"]},
                "description": {"type": "string"},
                "required": {"type": "bool", "default": True},
                "is_sensitive": {"type": "bool", "default": True},
                "friendly_name": {"type": "string", "description": "Display name in mobile settings UI"},
            },
        },
        "packages": {
            "type": "list[object]",
            "description": "Python pip dependencies",
            "item_fields": {
                "name": {"type": "string", "required": True, "description": "PyPI package name"},
                "version": {"type": "string", "description": "Version spec (e.g., '>=1.0,<2.0')"},
            },
        },
        "authentication": {
            "type": "object",
            "description": "OAuth config (only if calling external APIs that require OAuth)",
            "item_fields": {
                "type": {"type": "string", "required": True, "description": "'oauth'"},
                "provider": {"type": "string", "required": True, "description": "e.g., 'spotify', 'home_assistant'"},
                "friendly_name": {"type": "string", "required": True},
                "client_id": {"type": "string", "required": True},
                "keys": {"type": "list[string]", "required": True},
                "authorize_url": {"type": "string"},
                "exchange_url": {"type": "string"},
                "scopes": {"type": "list[string]"},
                "supports_pkce": {"type": "bool", "default": False},
            },
        },
        "components": {
            "type": "list[object]",
            "description": "For multi-component bundles. Omit for single-command packages.",
            "item_fields": {
                "type": {
                    "type": "string", "required": True,
                    "valid_values": ["command", "agent", "device_protocol", "device_manager"],
                },
                "name": {"type": "string", "required": True},
                "path": {"type": "string", "required": True, "description": "Relative path to entry file"},
                "description": {"type": "string"},
            },
        },
        "min_jarvis_version": {"type": "string", "default": "0.9.0"},
        "license": {"type": "string", "default": "MIT"},
        "homepage": {"type": "string", "description": "URL to project homepage or docs"},
    },
}

# File layout conventions
FILE_LAYOUT: dict[str, Any] = {
    "single_command": {
        "description": "Simple package with one voice command",
        "structure": [
            "jarvis_command.yaml    # manifest",
            "command.py             # IJarvisCommand implementation",
            "README.md              # optional",
        ],
    },
    "bundle": {
        "description": "Multi-component package (commands + agents + protocols + managers)",
        "structure": [
            "jarvis_package.yaml                    # manifest with components list",
            "commands/{name}/command.py              # command implementations",
            "agents/{name}/agent.py                  # agent implementations",
            "device_families/{name}/protocol.py      # device protocol implementations",
            "device_managers/{name}/manager.py        # device manager implementations",
            "{package_name}_shared/                  # shared code across components",
            "README.md                               # optional",
        ],
        "shared_code_rules": [
            "Put shared code in a package-specific directory (e.g., 'lifx_shared/')",
            "NEVER use 'services/', 'utils/', 'core/', or other node built-in names",
            "These names shadow the node runtime packages and break installations",
        ],
    },
    "convention_inference": {
        "description": "If 'components' is not declared in the manifest, the pipeline infers from directory structure",
        "rules": {
            "commands/{name}/command.py": "command",
            "agents/{name}/agent.py": "agent",
            "device_families/{name}/protocol.py": "device_protocol",
            "device_managers/{name}/manager.py": "device_manager",
            "command.py (at root)": "single command",
        },
    },
}

# Validation rules the Pantry enforces
VALIDATION_RULES: dict[str, Any] = {
    "static_analysis": {
        "description": "AST-based checks run on every submission",
        "checks": [
            "Syntax must parse (valid Python 3.11+)",
            "Must contain a class inheriting from the correct base class",
            "All required abstract methods must be implemented",
            "Version must be valid semver (X.Y.Z)",
            "Categories must be from the valid list",
            "Parameter types must be from the allowed set",
            "Secret scopes must be 'integration' or 'node'",
        ],
        "dangerous_patterns_flagged": [
            "subprocess, os, shutil, ctypes, importlib imports",
            "eval(), exec(), compile(), __import__() calls",
            "Raw database imports (sqlite3, sqlalchemy) — use CommandDataRepository instead",
            "SQL mutation keywords in string literals",
            "Cross-command data access via CommandDataRepository",
        ],
        "shared_dir_conflicts": (
            "Top-level directories matching node built-in package names "
            "(services, utils, core, agents, commands, etc.) are flagged as warnings"
        ),
    },
    "container_tests": {
        "description": "Behavioral tests run in sandboxed Docker containers",
        "constraints": {
            "memory": "128MB",
            "cpu": "0.5 cores",
            "network": "none (--network=none)",
            "filesystem": "read-only (--read-only) with 32MB writable /tmp",
            "timeout": "90 seconds default",
        },
        "what_is_tested": [
            "Class can be instantiated",
            "All required properties return correct types",
            "command_name is snake_case",
            "parameters returns list of valid parameter objects",
            "required_secrets returns list of valid secret objects",
            "generate_prompt_examples returns list of CommandExample",
        ],
    },
}

# Import patterns for community packages
IMPORT_PATTERNS: dict[str, str] = {
    "sdk": "from jarvis_command_sdk import IJarvisCommand, CommandResponse, JarvisParameter",
    "logging": (
        "try:\n"
        "    from jarvis_log_client import JarvisLogger\n"
        "except ImportError:\n"
        "    import logging\n"
        "    class JarvisLogger:\n"
        "        def __init__(self, **kw): self._log = logging.getLogger(kw.get('service', __name__))\n"
        "        def info(self, msg, **kw): self._log.info(msg)\n"
        "        def warning(self, msg, **kw): self._log.warning(msg)\n"
        "        def error(self, msg, **kw): self._log.error(msg)\n"
        "        def debug(self, msg, **kw): self._log.debug(msg)"
    ),
}


def _get_type_name(annotation: Any) -> str:
    """Convert a type annotation to a readable string."""
    if annotation is inspect.Parameter.empty:
        return "Any"
    origin = getattr(annotation, "__origin__", None)
    if origin is not None:
        args = getattr(annotation, "__args__", ())
        args_str = ", ".join(_get_type_name(a) for a in args) if args else ""
        origin_name = getattr(origin, "__name__", str(origin))
        if origin_name == "Union":
            parts = [_get_type_name(a) for a in args if a is not type(None)]
            if len(parts) == 1 and type(None) in args:
                return f"{parts[0]} | None"
            return " | ".join(parts)
        return f"{origin_name}[{args_str}]" if args_str else origin_name
    if hasattr(annotation, "__name__"):
        return annotation.__name__
    return str(annotation).replace("typing.", "")


def _introspect_method(cls: type, name: str) -> dict[str, Any]:
    """Introspect a method/property and return its spec."""
    member = getattr(cls, name, None)
    if member is None:
        return {"name": name}

    result: dict[str, Any] = {"name": name}

    # Check if it's a property
    for klass in cls.__mro__:
        if name in klass.__dict__:
            attr = klass.__dict__[name]
            if isinstance(attr, property):
                result["kind"] = "property"
                if attr.fget and attr.fget.__doc__:
                    result["description"] = attr.fget.__doc__.strip()
                # Get return type from fget
                try:
                    try:
                        fget_hints = get_type_hints(attr.fget)
                    except Exception:
                        fget_hints = getattr(attr.fget, "__annotations__", {})
                    if "return" in fget_hints:
                        result["return_type"] = _get_type_name(fget_hints["return"])
                except Exception:
                    pass
                return result
            break

    # It's a method
    result["kind"] = "method"
    if callable(member) and member.__doc__:
        result["description"] = member.__doc__.strip()

    try:
        try:
            hints = get_type_hints(member)
        except Exception:
            hints = getattr(member, "__annotations__", {})
        if "return" in hints:
            result["return_type"] = _get_type_name(hints["return"])
        sig = inspect.signature(member)
        params = []
        for pname, param in sig.parameters.items():
            if pname == "self":
                continue
            p: dict[str, Any] = {"name": pname}
            if pname in hints:
                p["type"] = _get_type_name(hints[pname])
            if param.default is not inspect.Parameter.empty:
                p["default"] = repr(param.default)
            params.append(p)
        if params:
            result["parameters"] = params
    except (ValueError, TypeError):
        pass

    # Check if abstract
    if getattr(member, "__isabstractmethod__", False):
        result["abstract"] = True

    return result


def _introspect_dataclass(cls: type) -> dict[str, Any]:
    """Introspect a dataclass and return its spec."""
    result: dict[str, Any] = {
        "name": cls.__name__,
        "description": (cls.__doc__ or "").strip(),
    }

    hints = getattr(cls, "__forge_hints__", None)
    if hints:
        result["forge_hints"] = hints

    if is_dataclass(cls):
        dc_fields = []
        for f in fields(cls):
            field_info: dict[str, Any] = {
                "name": f.name,
                "type": _get_type_name(f.type) if f.type else "Any",
            }
            if f.default is not f.default_factory:  # type: ignore[comparison-overlap]
                if f.default is not inspect.Parameter.empty and str(f.default) != "MISSING":
                    field_info["default"] = repr(f.default)
            dc_fields.append(field_info)
        result["fields"] = dc_fields

    # Include class methods (factory methods like CommandResponse.success_response)
    class_methods = []
    for name in dir(cls):
        if name.startswith("_"):
            continue
        attr = getattr(cls, name, None)
        if attr and isinstance(inspect.getattr_static(cls, name, None), classmethod):
            method_info = _introspect_method(cls, name)
            method_info["kind"] = "classmethod"
            class_methods.append(method_info)
    if class_methods:
        result["class_methods"] = class_methods

    return result


def _introspect_interface(cls: type) -> dict[str, Any]:
    """Introspect an interface class and return its full spec."""
    result: dict[str, Any] = {
        "name": cls.__name__,
        "description": (cls.__doc__ or "").strip(),
    }

    hints = getattr(cls, "__forge_hints__", None)
    if hints:
        result["forge_hints"] = hints

    # Collect all abstract and concrete methods/properties
    abstract_members: list[dict[str, Any]] = []
    optional_members: list[dict[str, Any]] = []

    # Walk MRO to find all relevant members
    seen: set[str] = set()
    for klass in cls.__mro__:
        if klass is object:
            continue
        for name, attr in klass.__dict__.items():
            if name.startswith("_") and name != "__init__":
                continue
            if name in seen:
                continue
            seen.add(name)

            spec = _introspect_method(cls, name)

            # Determine if abstract
            is_abstract = False
            if isinstance(attr, property) and attr.fget:
                is_abstract = getattr(attr.fget, "__isabstractmethod__", False)
            elif callable(attr):
                is_abstract = getattr(attr, "__isabstractmethod__", False)

            if is_abstract:
                spec["abstract"] = True
                abstract_members.append(spec)
            else:
                optional_members.append(spec)

    result["required_members"] = abstract_members
    result["optional_members"] = optional_members

    return result


def generate_spec() -> dict[str, Any]:
    """Generate the complete Forge authoring spec from SDK introspection.

    Returns a JSON-serializable dict containing:
    - interfaces: Full spec for each interface class (methods, types, hints)
    - supporting_classes: Specs for dataclasses authors use (CommandResponse, etc.)
    - manifest_schema: YAML manifest field reference
    - file_layout: Directory structure conventions
    - validation_rules: What the Pantry checks during submission
    - import_patterns: Correct import statements for community packages

    This is the single source of truth for the Forge's system prompt.
    """
    spec: dict[str, Any] = {
        "version": "1.0.0",
        "description": (
            "Jarvis Command SDK authoring spec — auto-generated from SDK source code. "
            "Use this to build valid Jarvis packages (commands, agents, device protocols, "
            "and device managers) that pass the Pantry validation pipeline."
        ),
        "interfaces": {},
        "supporting_classes": {},
        "manifest_schema": MANIFEST_SCHEMA,
        "file_layout": FILE_LAYOUT,
        "validation_rules": VALIDATION_RULES,
        "import_patterns": IMPORT_PATTERNS,
    }

    for cls in INTERFACE_CLASSES:
        spec["interfaces"][cls.__name__] = _introspect_interface(cls)

    for cls in SUPPORTING_CLASSES:
        spec["supporting_classes"][cls.__name__] = _introspect_dataclass(cls)

    return spec


def generate_spec_markdown() -> str:
    """Generate a human-readable Markdown version of the Forge spec.

    Useful for debugging or embedding directly in LLM prompts as text.
    """
    spec = generate_spec()
    lines: list[str] = []

    lines.append("# Jarvis Command SDK — Authoring Reference")
    lines.append("")
    lines.append(spec["description"])
    lines.append("")

    # Interfaces
    lines.append("## Component Interfaces")
    lines.append("")
    for name, iface in spec["interfaces"].items():
        hints = iface.get("forge_hints", {})
        lines.append(f"### {name}")
        lines.append("")
        lines.append(iface["description"])
        lines.append("")

        if hints.get("example_import"):
            lines.append(f"**Import:** `{hints['example_import']}`")
            lines.append("")
        if hints.get("entry_file"):
            lines.append(f"**Entry file:** `{hints['entry_file']}`")
        if hints.get("convention_dir"):
            lines.append(f"**Convention dir:** `{hints['convention_dir']}`")
        lines.append("")

        if hints.get("tips"):
            lines.append("**Tips:**")
            for tip in hints["tips"]:
                lines.append(f"- {tip}")
            lines.append("")

        lines.append("**Required members (must implement):**")
        lines.append("")
        for member in iface.get("required_members", []):
            ret = member.get("return_type", "")
            ret_str = f" -> {ret}" if ret else ""
            kind = member.get("kind", "method")
            desc = member.get("description", "").split("\n")[0] if member.get("description") else ""
            if kind == "property":
                lines.append(f"- `{member['name']}`{ret_str} (property) — {desc}")
            else:
                params = member.get("parameters", [])
                params_str = ", ".join(
                    f"{p['name']}: {p.get('type', 'Any')}" for p in params
                )
                lines.append(f"- `{member['name']}({params_str})`{ret_str} — {desc}")
        lines.append("")

        optional = iface.get("optional_members", [])
        if optional:
            lines.append("**Optional members (have defaults, override if needed):**")
            lines.append("")
            for member in optional:
                ret = member.get("return_type", "")
                ret_str = f" -> {ret}" if ret else ""
                desc = member.get("description", "").split("\n")[0] if member.get("description") else ""
                lines.append(f"- `{member['name']}`{ret_str} — {desc}")
            lines.append("")

    # Supporting classes
    lines.append("## Supporting Classes")
    lines.append("")
    for name, cls_spec in spec["supporting_classes"].items():
        lines.append(f"### {name}")
        lines.append("")
        lines.append(cls_spec["description"])
        lines.append("")

        hints = cls_spec.get("forge_hints", {})
        if hints.get("tips"):
            lines.append("**Tips:**")
            for tip in hints["tips"]:
                lines.append(f"- {tip}")
            lines.append("")

        if cls_spec.get("fields"):
            lines.append("**Fields:**")
            for f in cls_spec["fields"]:
                default = f" = {f['default']}" if "default" in f else ""
                lines.append(f"- `{f['name']}: {f['type']}{default}`")
            lines.append("")

        if cls_spec.get("class_methods"):
            lines.append("**Factory methods:**")
            for m in cls_spec["class_methods"]:
                lines.append(f"- `{name}.{m['name']}()`")
            lines.append("")

    # Manifest schema
    lines.append("## Manifest Schema (jarvis_command.yaml / jarvis_package.yaml)")
    lines.append("")
    lines.append(spec["manifest_schema"]["description"])
    lines.append("")
    for fname, finfo in spec["manifest_schema"]["fields"].items():
        req = " **(required)**" if finfo.get("required") else ""
        desc = finfo.get("description", "")
        default = f" (default: {finfo['default']})" if "default" in finfo else ""
        lines.append(f"- `{fname}`: {finfo['type']}{req}{default} — {desc}")
        if "valid_values" in finfo:
            lines.append(f"  Valid values: {', '.join(finfo['valid_values'])}")
    lines.append("")

    # File layout
    lines.append("## File Layout")
    lines.append("")
    for layout_name, layout in spec["file_layout"].items():
        lines.append(f"### {layout_name}")
        lines.append("")
        lines.append(layout.get("description", ""))
        lines.append("")
        if "structure" in layout:
            lines.append("```")
            for line in layout["structure"]:
                lines.append(line)
            lines.append("```")
            lines.append("")
        if "shared_code_rules" in layout:
            lines.append("**Shared code rules:**")
            for rule in layout["shared_code_rules"]:
                lines.append(f"- {rule}")
            lines.append("")
        if "rules" in layout:
            for pattern, comp_type in layout["rules"].items():
                lines.append(f"- `{pattern}` → {comp_type}")
            lines.append("")

    # Validation rules
    lines.append("## Validation Rules")
    lines.append("")
    for section_name, section in spec["validation_rules"].items():
        lines.append(f"### {section_name}")
        lines.append("")
        lines.append(section["description"])
        lines.append("")
        if "checks" in section:
            for check in section["checks"]:
                lines.append(f"- {check}")
            lines.append("")
        if "dangerous_patterns_flagged" in section:
            lines.append("**Flagged as dangerous:**")
            for pattern in section["dangerous_patterns_flagged"]:
                lines.append(f"- {pattern}")
            lines.append("")
        if "constraints" in section:
            lines.append("**Container constraints:**")
            for k, v in section["constraints"].items():
                lines.append(f"- {k}: {v}")
            lines.append("")
        if "what_is_tested" in section:
            lines.append("**Behavioral tests:**")
            for test in section["what_is_tested"]:
                lines.append(f"- {test}")
            lines.append("")

    # Import patterns
    lines.append("## Import Patterns")
    lines.append("")
    for pattern_name, pattern in spec["import_patterns"].items():
        lines.append(f"### {pattern_name}")
        lines.append("```python")
        lines.append(pattern)
        lines.append("```")
        lines.append("")

    return "\n".join(lines)
