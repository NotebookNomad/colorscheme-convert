"""Tokyo Night palettes.

Hex values follow the reference implementation of folke/tokyonight.nvim
(the four published variants: night, storm, moon, day).
"""

from __future__ import annotations

PALETTES: dict[str, dict[str, str]] = {
    "night": {
        "bg_dark": "#16161e",
        "bg": "#1a1b26",
        "bg_highlight": "#292e42",
        "blue7": "#394b70",
        "fg_gutter": "#3b4261",
        "blue0": "#3d59a1",
        "terminal_black": "#414868",
        "dark3": "#545c7e",
        "comment": "#565f89",
        "dark5": "#737aa2",
        "blue": "#7aa2f7",
        "cyan": "#7dcfff",
        "blue1": "#2ac3de",
        "blue2": "#0db9d7",
        "blue5": "#89ddff",
        "blue6": "#b4f9f8",
        "magenta": "#bb9af7",
        "magenta2": "#ff007c",
        "purple": "#9d7cd8",
        "orange": "#ff9e64",
        "yellow": "#e0af68",
        "green": "#9ece6a",
        "green1": "#73daca",
        "green2": "#41a6b5",
        "teal": "#1abc9c",
        "red": "#f7768e",
        "red1": "#db4b4b",
        "fg_dark": "#a9b1d6",
        "fg": "#c0caf5",
    },
    "storm": {
        "bg_dark": "#1f2335",
        "bg": "#24283b",
        "bg_highlight": "#292e42",
        "blue7": "#394b70",
        "fg_gutter": "#3b4261",
        "blue0": "#3d59a1",
        "terminal_black": "#414868",
        "dark3": "#545c7e",
        "comment": "#565f89",
        "dark5": "#737aa2",
        "blue": "#7aa2f7",
        "cyan": "#7dcfff",
        "blue1": "#2ac3de",
        "blue2": "#0db9d7",
        "blue5": "#89ddff",
        "blue6": "#b4f9f8",
        "magenta": "#bb9af7",
        "magenta2": "#ff007c",
        "purple": "#9d7cd8",
        "orange": "#ff9e64",
        "yellow": "#e0af68",
        "green": "#9ece6a",
        "green1": "#73daca",
        "green2": "#41a6b5",
        "teal": "#1abc9c",
        "red": "#f7768e",
        "red1": "#db4b4b",
        "fg_dark": "#a9b1d6",
        "fg": "#c0caf5",
    },
    "moon": {
        "bg_dark": "#1e2030",
        "bg": "#222436",
        "bg_highlight": "#2f334d",
        "blue7": "#394b70",
        "fg_gutter": "#3b4261",
        "blue0": "#3e68d7",
        "terminal_black": "#444a73",
        "dark3": "#545c7e",
        "comment": "#636da6",
        "dark5": "#737aa2",
        "blue": "#82aaff",
        "cyan": "#86e1fc",
        "blue1": "#65bcff",
        "blue2": "#0db9d7",
        "blue5": "#89ddff",
        "blue6": "#b4f9f8",
        "magenta": "#c099ff",
        "magenta2": "#ff007c",
        "purple": "#fca7ea",
        "orange": "#ff966c",
        "yellow": "#ffc777",
        "green": "#c3e88d",
        "green1": "#4fd6be",
        "green2": "#41a6b5",
        "teal": "#4fd6be",
        "red": "#ff757f",
        "red1": "#c53b53",
        "fg_dark": "#828bb8",
        "fg": "#c8d3f5",
    },
    "day": {
        "bg_dark": "#d0d5e3",
        "bg": "#e1e2e7",
        "bg_highlight": "#c4c8da",
        "blue7": "#92a6d5",
        "fg_gutter": "#a8aecb",
        "blue0": "#7890dd",
        "terminal_black": "#a1a6c5",
        "dark3": "#8990b3",
        "comment": "#848cb5",
        "dark5": "#68709a",
        "blue": "#2e7de9",
        "cyan": "#007197",
        "blue1": "#188092",
        "blue2": "#07879d",
        "blue5": "#006a83",
        "blue6": "#2e5857",
        "magenta": "#9854f1",
        "magenta2": "#d20065",
        "purple": "#7847bd",
        "orange": "#b15c00",
        "yellow": "#8c6c3e",
        "green": "#587539",
        "green1": "#387068",
        "green2": "#325b64",
        "teal": "#118c74",
        "red": "#f52a65",
        "red1": "#c64343",
        "fg_dark": "#6172b0",
        "fg": "#3760bf",
    },
}

DEFAULT_VARIANT = "night"

# Roles that are pure UI chrome and rarely help as image colors: they sit very
# close to other entries and only add banding when mapping photographic input.
_CHROME_ROLES = ("bg_highlight", "fg_gutter", "terminal_black", "dark3", "dark5")


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    if len(value) != 6:
        raise ValueError(f"not a hex color: #{value}")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#%02x%02x%02x" % tuple(int(c) for c in rgb)


# The scheme's neutral spine, darkest to lightest. Gradient-mapping onto these
# reads as Tokyo Night; mapping onto the accent colors just makes a rainbow.
RAMP_ROLES = (
    "bg_dark",
    "bg",
    "bg_highlight",
    "blue7",
    "fg_gutter",
    "terminal_black",
    "dark3",
    "comment",
    "dark5",
    "fg_dark",
    "fg",
)


def get_palette(variant: str = DEFAULT_VARIANT, *, full: bool = False) -> list[tuple[str, tuple[int, int, int]]]:
    """Return [(role, (r, g, b)), ...] for a variant.

    With ``full=False`` the near-duplicate chrome shades are dropped, which
    gives cleaner results on photographs.
    """
    try:
        scheme = PALETTES[variant]
    except KeyError:
        raise ValueError(
            f"unknown variant {variant!r}; choose from: {', '.join(PALETTES)}"
        ) from None
    return [
        (role, hex_to_rgb(hexval))
        for role, hexval in scheme.items()
        if full or role not in _CHROME_ROLES
    ]


def get_ramp(variant: str = DEFAULT_VARIANT) -> list[tuple[int, int, int]]:
    """The neutral dark-to-light ramp for gradient mapping."""
    scheme = dict(get_palette(variant, full=True))
    return [scheme[role] for role in RAMP_ROLES]
