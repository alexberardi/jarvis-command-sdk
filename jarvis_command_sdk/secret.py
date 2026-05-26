from abc import ABC, abstractmethod


class IJarvisSecret(ABC):
    @property
    @abstractmethod
    def key(self) -> str:
        pass

    @property
    @abstractmethod
    def scope(self) -> str:
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        pass

    @property
    @abstractmethod
    def value_type(self) -> str:
        pass

    @property
    @abstractmethod
    def required(self) -> bool:
        pass

    @property
    def friendly_name(self) -> str | None:
        """Short display name for the UI (e.g. "REST URL", "API Key").

        Defaults to None, in which case the mobile app falls back to the key.
        """
        return None

    @property
    def is_sensitive(self) -> bool:
        """Whether this secret contains sensitive data (API keys, passwords, tokens).

        Defaults to True. Override to False for non-sensitive config like URLs,
        units, locations, etc. Non-sensitive values are included in settings
        snapshots so the mobile app can display them.
        """
        return True

    @property
    def enum_values(self) -> list[str] | None:
        """Optional list of allowed values for this secret.

        When set, the mobile app renders a dropdown picker instead of free-text
        input. Only valid for value_type='string'.
        """
        return None

    @property
    def presets(self) -> dict[str, dict[str, str]] | None:
        """Maps enum values to dicts of {secret_key: default_value}.

        When the user selects an enum value in the mobile app, it offers to
        auto-fill these dependent secrets. Keys must be members of enum_values.
        """
        return None


class JarvisSecret(IJarvisSecret):
    """Concrete secret implementation for declaring API keys, URLs, and config values.

    Secrets are stored encrypted on the node. The mobile app settings UI
    lets users enter values. Non-sensitive secrets (is_sensitive=False) are
    visible in settings snapshots.
    """

    __forge_hints__ = {
        "role": "Declares a secret (API key, URL, config) stored encrypted on the node",
        "constructor": "JarvisSecret(key, description, scope, value_type, required=True, is_sensitive=True, friendly_name=None, enum_values=None, presets=None)",
        "allowed_scopes": ["integration", "user"],
        "allowed_value_types": ["string", "int", "bool"],
        "example": 'JarvisSecret(key="WEATHER_API_KEY", description="OpenWeather API key", scope="integration", value_type="string")',
        "tips": [
            "scope='integration' means shared across the household (every node sees the same value)",
            "scope='user' means per-user (e.g., personal email credentials — each family member has their own)",
            "Set is_sensitive=False for non-secret config like URLs, units, locations",
            "friendly_name is shown in the mobile settings UI instead of the key",
            "Commands sharing an AuthenticationConfig provider share secrets automatically",
            "Use enum_values to constrain a secret to specific allowed values (mobile renders a dropdown)",
            "Use presets to auto-fill related secrets when an enum value is chosen (e.g. provider-specific IMAP settings)",
        ],
    }

    def __init__(
        self,
        key: str,
        description: str,
        scope: str,
        value_type: str,
        required: bool = True,
        is_sensitive: bool = True,
        friendly_name: str | None = None,
        enum_values: list[str] | None = None,
        presets: dict[str, dict[str, str]] | None = None,
    ):
        self._key = key
        self._description = description
        if scope not in ("integration", "user"):
            raise ValueError(f"Scope must be integration or user for {key}")
        self._scope = scope

        if value_type != "int" and value_type != "string" and value_type != "bool":
            raise ValueError(f"Value Type must be int, string or bool for {key}")
        self._value_type = value_type
        self._required = required
        self._is_sensitive = is_sensitive
        self._friendly_name = friendly_name

        if enum_values is not None and value_type != "string":
            raise ValueError(f"enum_values requires value_type='string' for {key}")
        self._enum_values = enum_values

        if presets is not None:
            if enum_values is None:
                raise ValueError(f"presets requires enum_values for {key}")
            invalid_keys = set(presets.keys()) - set(enum_values)
            if invalid_keys:
                raise ValueError(
                    f"Preset keys {invalid_keys} not in enum_values for {key}"
                )
        self._presets = presets

    @property
    def is_sensitive(self) -> bool:
        return self._is_sensitive

    @property
    def friendly_name(self) -> str | None:
        return self._friendly_name

    @property
    def key(self) -> str:
        return self._key

    @property
    def description(self) -> str:
        return self._description

    @property
    def scope(self) -> str:
        return self._scope

    @property
    def value_type(self) -> str:
        return self._value_type

    @property
    def required(self) -> bool:
        return self._required

    @property
    def enum_values(self) -> list[str] | None:
        return self._enum_values

    @property
    def presets(self) -> dict[str, dict[str, str]] | None:
        return self._presets
