"""Tests for the shared named-color palette and resolver."""

from __future__ import annotations

import pytest

from jarvis_command_sdk import Color, NAMED_COLORS, resolve_color


class TestColorEnum:
    def test_member_value_is_rgb_tuple(self) -> None:
        assert Color.GREEN.rgb == (0, 255, 0)
        assert Color.RED.value == (255, 0, 0)
        assert Color.WARM_WHITE.rgb == (255, 214, 170)

    def test_spoken_name_underscore_to_space(self) -> None:
        assert Color.WARM_WHITE.spoken_name == "warm white"
        assert Color.SKY_BLUE.spoken_name == "sky blue"
        assert Color.RED.spoken_name == "red"

    def test_values_are_unique_no_alias_collapsing(self) -> None:
        # Duplicate enum values silently collapse into aliases, dropping
        # members from iteration. Guard against that regression.
        values = [c.value for c in Color]
        assert len(values) == len(set(values))

    def test_from_name(self) -> None:
        assert Color.from_name("green") is Color.GREEN
        assert Color.from_name("Warm White") is Color.WARM_WHITE
        assert Color.from_name("grey") is Color.GRAY  # synonym
        assert Color.from_name("nonsense") is None


class TestNamedColors:
    def test_derived_from_enum(self) -> None:
        for color in Color:
            assert NAMED_COLORS[color.spoken_name] == color.rgb

    def test_synonyms_present(self) -> None:
        assert NAMED_COLORS["grey"] == Color.GRAY.rgb
        assert NAMED_COLORS["aqua"] == Color.CYAN.rgb
        assert NAMED_COLORS["lime"] == Color.GREEN.rgb
        assert NAMED_COLORS["fuchsia"] == Color.MAGENTA.rgb


class TestResolveColor:
    @pytest.mark.parametrize(
        "value,expected",
        [
            ("green", (0, 255, 0)),
            ("Green", (0, 255, 0)),
            ("  RED  ", (255, 0, 0)),
            ("warm white", (255, 214, 170)),
            ("warm-white", (255, 214, 170)),
            ("warm_white", (255, 214, 170)),
            ("sky blue", (135, 206, 235)),
            ("grey", (128, 128, 128)),
            ("aqua", (0, 255, 255)),
        ],
    )
    def test_named(self, value: str, expected: tuple[int, int, int]) -> None:
        assert resolve_color(value) == expected

    @pytest.mark.parametrize(
        "value,expected",
        [
            ("255,0,128", (255, 0, 128)),
            ("255, 0, 128", (255, 0, 128)),
            ("0,0,0", (0, 0, 0)),
        ],
    )
    def test_csv(self, value: str, expected: tuple[int, int, int]) -> None:
        assert resolve_color(value) == expected

    @pytest.mark.parametrize(
        "value,expected",
        [
            ("#ff0080", (255, 0, 128)),
            ("#FFFFFF", (255, 255, 255)),
            ("#000000", (0, 0, 0)),
        ],
    )
    def test_hex_requires_hash(self, value: str, expected: tuple[int, int, int]) -> None:
        assert resolve_color(value) == expected

    @pytest.mark.parametrize("value", ["facade", "decade", "beaded", "ff0080", "abcdef"])
    def test_bare_hex_words_are_not_colors(self, value: str) -> None:
        # Without the '#' sigil, 6-letter hex-valid words must NOT be read as hex.
        assert resolve_color(value) is None

    def test_sequence_passthrough(self) -> None:
        assert resolve_color([12, 34, 56]) == (12, 34, 56)
        assert resolve_color((255, 255, 255)) == (255, 255, 255)

    @pytest.mark.parametrize(
        "value",
        [
            None,
            "",
            "   ",
            "chartreuse",          # not in palette
            "256,0,0",             # out of range
            "1,2",                 # wrong arity
            "1,2,3,4",             # wrong arity
            "0,0,green",           # non-numeric
            [1, 2],                # wrong arity sequence
            [300, 0, 0],           # out-of-range sequence
            42,                    # wrong type
            "#ff00",               # bad hex length
            "#gggggg",             # bad hex chars
        ],
    )
    def test_unknown_returns_none(self, value: object) -> None:
        assert resolve_color(value) is None
