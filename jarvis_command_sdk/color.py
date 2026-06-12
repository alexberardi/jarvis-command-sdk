"""Shared named-color palette and resolution for Jarvis device protocols.

Voice commands like "turn the light green" or "set the lamp to warm white"
need a spoken color name turned into an RGB triple that each light protocol
(Hue, Govee, LIFX, ...) can translate into its own wire format. This module
is the single source of truth for that mapping so every device package
resolves colors identically.

Usage:
    from jarvis_command_sdk import Color, NAMED_COLORS, resolve_color

    resolve_color("green")        # (0, 255, 0)
    resolve_color("warm white")   # (255, 214, 170)
    resolve_color("255, 0, 128")  # (255, 0, 128)
    resolve_color("#ff0080")      # (255, 0, 128)
    resolve_color("chartreuse")   # None  (unknown)
    Color.GREEN.rgb               # (0, 255, 0)
"""

from __future__ import annotations

from enum import Enum

# (r, g, b), each component 0-255.
RGB = tuple[int, int, int]


class Color(Enum):
    """Named colors mapped to their canonical RGB (0-255) triple.

    Each member's value IS its ``(r, g, b)`` tuple. Spoken synonyms
    (e.g. "grey" -> GRAY, "aqua" -> CYAN, "lime" -> GREEN) are handled by
    :data:`NAMED_COLORS` and :func:`resolve_color` rather than as separate
    members, so iterating the enum yields one entry per distinct color.
    """

    RED = (255, 0, 0)
    ORANGE = (255, 165, 0)
    AMBER = (255, 191, 0)
    YELLOW = (255, 255, 0)
    GREEN = (0, 255, 0)
    BLUE = (0, 0, 255)
    CYAN = (0, 255, 255)
    TEAL = (0, 128, 128)
    TURQUOISE = (64, 224, 208)
    SKY_BLUE = (135, 206, 235)
    NAVY = (0, 0, 128)
    INDIGO = (75, 0, 130)
    PURPLE = (128, 0, 128)
    VIOLET = (148, 0, 211)
    MAGENTA = (255, 0, 255)
    PINK = (255, 105, 180)
    LAVENDER = (200, 162, 200)
    CORAL = (255, 127, 80)
    SALMON = (250, 128, 114)
    PEACH = (255, 218, 185)
    GOLD = (255, 215, 0)
    MINT = (152, 255, 152)
    MAROON = (128, 0, 0)
    BROWN = (139, 69, 19)
    OLIVE = (128, 128, 0)
    CRIMSON = (220, 20, 60)
    WHITE = (255, 255, 255)
    WARM_WHITE = (255, 214, 170)
    COOL_WHITE = (200, 220, 255)
    GRAY = (128, 128, 128)

    @property
    def rgb(self) -> RGB:
        """The ``(r, g, b)`` triple for this color, each 0-255."""
        return self.value

    @property
    def spoken_name(self) -> str:
        """Lower-case spoken form of the name (``WARM_WHITE`` -> ``warm white``)."""
        return self.name.lower().replace("_", " ")

    @classmethod
    def from_name(cls, name: str) -> "Color | None":
        """Resolve a spoken color name (incl. synonyms) to a member, or None."""
        norm = _normalize(name)
        for color in cls:
            if color.spoken_name == norm:
                return color
        canonical = _ALIASES.get(norm)
        return cls.from_name(canonical) if canonical else None


def _normalize(name: str) -> str:
    """Lower-case and collapse separators so "Warm-White" == "warm white"."""
    return " ".join(name.strip().lower().replace("-", " ").replace("_", " ").split())


# Spoken synonyms that map onto an existing canonical color.
_ALIASES: dict[str, str] = {
    "lime": "green",
    "grey": "gray",
    "aqua": "cyan",
    "fuchsia": "magenta",
    "light blue": "sky blue",
    "hot pink": "pink",
    "soft white": "warm white",
    "daylight": "cool white",
}


# name -> RGB lookup. Derived from :class:`Color` (one source of truth),
# then extended with spoken synonyms.
NAMED_COLORS: dict[str, RGB] = {color.spoken_name: color.rgb for color in Color}
for _alias, _canonical in _ALIASES.items():
    NAMED_COLORS[_alias] = NAMED_COLORS[_canonical]


def resolve_color(value: object) -> RGB | None:
    """Resolve a spoken color name, ``"r,g,b"`` string, or hex code to RGB.

    Accepts:
      * named colors, case/space/hyphen-insensitive ("Warm-White", "warm white")
      * an existing ``(r, g, b)`` sequence (validated and passed through)
      * ``"r,g,b"`` with each component 0-255 ("255, 0, 128")
      * hex ("#ff0080" or "ff0080")

    Returns an ``(r, g, b)`` tuple (each 0-255), or ``None`` if unrecognized.
    """
    if value is None:
        return None

    # Already an (r, g, b) sequence (list/tuple)? Validate and pass through.
    if isinstance(value, (list, tuple)):
        if len(value) != 3:
            return None
        try:
            r, g, b = (int(c) for c in value)
        except (TypeError, ValueError):
            return None
        return (r, g, b) if all(0 <= c <= 255 for c in (r, g, b)) else None

    if not isinstance(value, str):
        return None

    text = value.strip()
    if not text:
        return None

    # "r,g,b"
    if "," in text:
        parts = [p.strip() for p in text.split(",")]
        if len(parts) != 3:
            return None
        try:
            r, g, b = (int(p) for p in parts)
        except ValueError:
            return None
        return (r, g, b) if all(0 <= c <= 255 for c in (r, g, b)) else None

    # hex "#rrggbb" — the leading '#' is REQUIRED. Without it, bare 6-letter
    # words that happen to be valid hex ("facade", "decade", "beaded") would be
    # misread as colors instead of falling through to the named-color lookup.
    if text.startswith("#"):
        hex_text = text[1:]
        if len(hex_text) == 6 and all(c in "0123456789abcdefABCDEF" for c in hex_text):
            return (
                int(hex_text[0:2], 16),
                int(hex_text[2:4], 16),
                int(hex_text[4:6], 16),
            )
        return None

    # named color (incl. synonyms)
    return NAMED_COLORS.get(_normalize(text))
