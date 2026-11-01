"""Color scheme registry.

A scheme is a JSON file. Built-ins ship in ``themes/`` beside this module; user
schemes live in ``$XDG_CONFIG_HOME/colorscheme-convert/themes`` (by default
``~/.config/colorscheme-convert/themes``) and shadow a built-in of the same
name. The theme name is the file's stem, so ``my-theme.json`` is ``my-theme``.

Three JSON shapes are accepted, smallest first::

    ["#1a1b26", "#7aa2f7", "#c0caf5"]

    {"bg": "#1a1b26", "blue": "#7aa2f7", "fg": "#c0caf5"}

    {"colors": <either of the above>,
     "ramp":    ["bg", "blue", "fg"],   optional, see Theme.ramp
     "exclude": ["blue"]}               optional, see Theme.entries
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

import oklab

DEFAULT_THEME = "tokyonight-night"

BUILTIN_DIR = Path(__file__).resolve().parent / "themes"

# A theme name is a lookup key derived from a file stem, and it also becomes
# part of an output filename. Both jobs want it boring: no directory
# separators, and no leading dot or dash to be mistaken for a hidden file or a
# CLI flag.
_SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")

Rgb = tuple[int, int, int]


def hex_to_rgb(value: str) -> Rgb:
    if not isinstance(value, str):
        raise ValueError(f"not a hex color: {value!r}")
    text = value.lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    try:
        if len(text) != 6:
            raise ValueError
        r, g, b = bytes.fromhex(text)
    except ValueError:
        raise ValueError(f"not a hex color: {value!r}") from None
    return r, g, b


def rgb_to_hex(rgb: Rgb) -> str:
    return "#%02x%02x%02x" % tuple(int(c) for c in rgb)


def rgb_array(colors: Iterable[Rgb]) -> np.ndarray:
    """(N, 3) uint8 — the shape every mapping function expects."""
    # An empty iterable gives numpy shape (0,), which blows up far downstream
    # in a matmul; reshape pins the second axis so the promise above holds.
    return np.array(list(colors), dtype=np.uint8).reshape(-1, 3)


@dataclass(frozen=True)
class Theme:
    """A named set of colors, plus optional hints about how to use them."""

    name: str
    colors: tuple[tuple[str, Rgb], ...]
    ramp: tuple[Rgb, ...]
    exclude: frozenset[str]

    def entries(self, *, full: bool = False) -> list[tuple[str, Rgb]]:
        """Colors to map against, as [(role, rgb), ...].

        A theme's ``exclude`` list names colors that sit so close to another
        entry that keeping them only adds banding on photographic input; they
        are dropped unless ``full`` is set.
        """
        drop = frozenset() if full else self.exclude
        return [(role, rgb) for role, rgb in self.colors if role not in drop]


def derive_ramp(colors: Iterable[Rgb]) -> tuple[Rgb, ...]:
    """Pick a neutral dark-to-light spine out of an arbitrary palette.

    Gradient mapping wants low-chroma colors — run it over a theme's accents
    and you get rainbow banding. This is what a theme gets when it declares no
    ``ramp`` of its own.
    """
    rgb = rgb_array(colors)
    lab = oklab.oklab_from_u8(rgb)
    chroma = oklab.chroma(lab)
    keep = chroma <= max(0.04, float(np.median(chroma)) * 0.6)
    if keep.sum() < 3:
        # Palette has no real neutrals; take the least saturated colors anyway.
        keep = np.zeros(len(lab), dtype=bool)
        keep[np.argsort(chroma)[:5]] = True
    idx = np.flatnonzero(keep)
    return tuple(tuple(int(v) for v in rgb[i]) for i in idx[np.argsort(lab[idx, 0])])


def _parse_colors(raw: object, name: str) -> tuple[tuple[str, Rgb], ...]:
    if isinstance(raw, list):
        pairs = [(str(i), value) for i, value in enumerate(raw)]
    elif isinstance(raw, dict):
        pairs = list(raw.items())
    else:
        raise ValueError(f"theme {name!r}: 'colors' must be a list or an object")
    if not pairs:
        raise ValueError(f"theme {name!r}: no colors")

    out = []
    for role, value in pairs:
        try:
            out.append((str(role), hex_to_rgb(value)))
        except ValueError as exc:
            raise ValueError(f"theme {name!r}, color {role!r}: {exc}") from None
    return tuple(out)


def _parse_roles(raw: object, key: str, known: set[str], name: str) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list) or not all(isinstance(r, str) for r in raw):
        raise ValueError(f"theme {name!r}: {key!r} must be a list of color names")
    unknown = [r for r in raw if r not in known]
    if unknown:
        raise ValueError(
            f"theme {name!r}: {key!r} names colors that do not exist: {', '.join(unknown)}"
        )
    return tuple(raw)


def parse_theme(data: object, name: str) -> Theme:
    """Build a Theme from already-decoded JSON."""
    if not _SAFE_NAME.fullmatch(name):
        raise ValueError(
            f"theme name {name!r} must start with a letter or digit and contain "
            "only letters, digits, dot, dash or underscore"
        )

    if isinstance(data, dict) and "colors" in data:
        raw_colors, raw_ramp, raw_exclude = data["colors"], data.get("ramp"), data.get("exclude")
    else:
        # Bare list of colors, or a bare {role: hex} object.
        raw_colors, raw_ramp, raw_exclude = data, None, None

    colors = _parse_colors(raw_colors, name)
    lookup = dict(colors)
    known = set(lookup)

    ramp_roles = _parse_roles(raw_ramp, "ramp", known, name)
    if ramp_roles and len(ramp_roles) < 2:
        raise ValueError(f"theme {name!r}: 'ramp' needs at least two colors")
    # Ramps resolve against every color the theme defines, including any the
    # palette drops, since the excluded shades are exactly the neutral ones.
    if ramp_roles:
        ramp = tuple(lookup[role] for role in ramp_roles)
    else:
        ramp = derive_ramp(rgb for _, rgb in colors)

    exclude = frozenset(_parse_roles(raw_exclude, "exclude", known, name))
    if exclude.issuperset(role for role, _ in colors):
        raise ValueError(
            f"theme {name!r}: 'exclude' leaves no colors to match against"
        )

    return Theme(name=name, colors=colors, ramp=ramp, exclude=exclude)


def load_theme_file(path: Path) -> Theme:
    """Load a theme from an explicit JSON file. Its name is the file stem."""
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        raise ValueError(f"no such theme file: {path}") from None
    except OSError as exc:
        raise ValueError(f"cannot read theme file {path}: {exc.strerror}") from None
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid JSON ({exc})") from None
    return parse_theme(data, path.stem)


def user_dir() -> Path:
    root = os.environ.get("XDG_CONFIG_HOME")
    base = Path(root) if root else Path.home() / ".config"
    return base / "colorscheme-convert" / "themes"


def discover() -> dict[str, Path]:
    """Map theme name -> file. User themes shadow built-ins of the same name."""
    found: dict[str, Path] = {}
    for directory in (BUILTIN_DIR, user_dir()):
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.json")):
            if _SAFE_NAME.fullmatch(path.stem):
                found[path.stem] = path
    return found


def get_theme(name: str = DEFAULT_THEME) -> Theme:
    """Load a theme by name from the built-in and user directories."""
    available = discover()
    try:
        path = available[name]
    except KeyError:
        raise ValueError(
            f"unknown theme {name!r}; available: {', '.join(sorted(available))}"
        ) from None
    return load_theme_file(path)


def list_themes() -> list[tuple[str, str, Path]]:
    """[(name, "built-in" | "user", path), ...] sorted by name."""
    return [
        (name, "built-in" if path.parent == BUILTIN_DIR else "user", path)
        for name, path in sorted(discover().items())
    ]
