#!/usr/bin/env python3
"""Recolor an image into the Tokyo Night colorscheme.

    ./convert.py photo.png -o photo-tokyonight.png

All color math happens in Oklab so that "nearest color" means nearest as the
eye sees it, not nearest in RGB cube distance.
"""

from __future__ import annotations

import argparse
import sys
from functools import partial
from pathlib import Path

import numpy as np
from PIL import Image

from palettes import DEFAULT_VARIANT, PALETTES, get_palette, get_ramp, rgb_to_hex

METHODS = ("nearest", "blend", "gradient")
DITHERS = ("none", "bayer", "floyd")
RAMPS = ("neutral", "all")

# Pixels per batch. Sized so a batch's (pixels, palette) distance block stays
# cache-resident; larger batches measure no faster and cost real memory.
CHUNK = 1 << 16

# ---------------------------------------------------------------------------
# color space
# ---------------------------------------------------------------------------

_LMS_FROM_LRGB = np.array(
    [
        [0.4122214708, 0.5363325363, 0.0514459929],
        [0.2119034982, 0.6806995451, 0.1073969566],
        [0.0883024619, 0.2817188376, 0.6299787005],
    ]
)
_OKLAB_FROM_LMS = np.array(
    [
        [0.2104542553, 0.7936177850, -0.0040720468],
        [1.9779984951, -2.4285922050, 0.4505937099],
        [0.0259040371, 0.7827717662, -0.8086757660],
    ]
)
_LMS_FROM_OKLAB = np.array(
    [
        [1.0, 0.3963377774, 0.2158037573],
        [1.0, -0.1055613458, -0.0638541728],
        [1.0, -0.0894841775, -1.2914855480],
    ]
)
_LRGB_FROM_LMS = np.array(
    [
        [4.0767416621, -3.3077115913, 0.2309699292],
        [-1.2684380046, 2.6097574011, -0.3413193965],
        [-0.0041960863, -0.7034186147, 1.7076147010],
    ]
)


def srgb_to_linear(c: np.ndarray) -> np.ndarray:
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(c: np.ndarray) -> np.ndarray:
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.clip(c, 0, None) ** (1 / 2.4) - 0.055)


# Every image and palette entering the pipeline is 8-bit, so the transfer
# function only ever sees 256 distinct values: tabulate it once.
_LINEAR_FROM_U8 = srgb_to_linear(np.arange(256) / 255.0)


def oklab_from_u8(rgb8: np.ndarray) -> np.ndarray:
    """(..., 3) uint8 sRGB -> (..., 3) Oklab."""
    lms = _LINEAR_FROM_U8[rgb8] @ _LMS_FROM_LRGB.T
    return np.cbrt(lms) @ _OKLAB_FROM_LMS.T


def oklab_to_rgb(lab: np.ndarray) -> np.ndarray:
    """(..., 3) Oklab -> (..., 3) sRGB clipped to [0, 1]."""
    lms = lab @ _LMS_FROM_OKLAB.T
    linear = (lms**3) @ _LRGB_FROM_LMS.T
    return np.clip(linear_to_srgb(linear), 0.0, 1.0)


def u8_from_oklab(lab: np.ndarray) -> np.ndarray:
    """(..., 3) Oklab -> (..., 3) uint8 sRGB."""
    return np.rint(oklab_to_rgb(lab) * 255.0).astype(np.uint8)


# ---------------------------------------------------------------------------
# mapping strategies
# ---------------------------------------------------------------------------


def _sq_distances(lab: np.ndarray, pal_lab: np.ndarray, chroma_weight: float) -> np.ndarray:
    """Squared Oklab distance from every pixel to every palette entry.

    ``chroma_weight`` scales the a/b axes: below 1.0 the match leans on
    lightness (safer for photos), above 1.0 it chases hue.

    Expanded as |a|^2 - 2a.b + |b|^2 so the work lands in one BLAS matmul and
    no (pixels, palette, 3) intermediate is ever allocated.
    """
    scale = np.array([1.0, chroma_weight, chroma_weight])
    a, b = lab * scale, pal_lab * scale
    d2 = (a * a).sum(1)[:, None] - 2.0 * (a @ b.T)
    d2 += (b * b).sum(1)
    # Cancellation can leave near-zero distances a hair below zero.
    return np.maximum(d2, 0.0, out=d2)


def map_nearest(lab: np.ndarray, pal_lab: np.ndarray, chroma_weight: float) -> np.ndarray:
    idx = np.argmin(_sq_distances(lab, pal_lab, chroma_weight), axis=1)
    return pal_lab[idx]


def map_blend(lab: np.ndarray, pal_lab: np.ndarray, chroma_weight: float, softness: float) -> np.ndarray:
    """Softmax-weighted mix of nearby palette colors: keeps gradients smooth."""
    d2 = _sq_distances(lab, pal_lab, chroma_weight)
    # Subtract the per-pixel minimum before exponentiating (numerically safe,
    # and makes the result independent of absolute distance scale).
    w = np.exp(-(d2 - d2.min(axis=1, keepdims=True)) / max(softness, 1e-6) ** 2)
    w /= w.sum(axis=1, keepdims=True)
    return w @ pal_lab


def map_gradient(lab: np.ndarray, ramp_lab: np.ndarray) -> np.ndarray:
    """Classic gradient map: source lightness indexes a ramp.

    ``ramp_lab`` must already be sorted by lightness. Stops are spaced evenly
    across the ramp's lightness span rather than at their own lightness values,
    so every color in the ramp gets an equal share of the output.
    """
    stops = np.linspace(ramp_lab[0, 0], ramp_lab[-1, 0], len(ramp_lab))
    return np.stack(
        [np.interp(lab[:, 0], stops, ramp_lab[:, c]) for c in range(3)], axis=1
    )


_BAYER8 = (
    np.array(
        [
            [0, 32, 8, 40, 2, 34, 10, 42],
            [48, 16, 56, 24, 50, 18, 58, 26],
            [12, 44, 4, 36, 14, 46, 6, 38],
            [60, 28, 52, 20, 62, 30, 54, 22],
            [3, 35, 11, 43, 1, 33, 9, 41],
            [51, 19, 59, 27, 49, 17, 57, 25],
            [15, 47, 7, 39, 13, 45, 5, 37],
            [63, 31, 55, 23, 61, 29, 53, 21],
        ]
    )
    / 64.0
    - 0.5
)


def bayer_offsets(height: int, width: int) -> np.ndarray:
    """(H*W, 1) ordered-dither offsets in [-0.5, 0.5]."""
    tile = np.tile(_BAYER8, (height // 8 + 1, width // 8 + 1))[:height, :width]
    return tile.reshape(-1, 1)


def palette_spacing(pal_lab: np.ndarray) -> float:
    """Median distance from each palette color to its closest neighbor."""
    d2 = _sq_distances(pal_lab, pal_lab, 1.0)
    np.fill_diagonal(d2, np.inf)
    return float(np.median(np.sqrt(d2.min(axis=1))))


def floyd_steinberg(rgb8: np.ndarray, pal_rgb8: np.ndarray) -> np.ndarray:
    """Error-diffusion dither via Pillow's C implementation (sRGB space)."""
    flat = pal_rgb8.ravel().tolist()
    pal_img = Image.new("P", (1, 1))
    pal_img.putpalette(flat + [0] * (768 - len(flat)))
    quantized = Image.fromarray(rgb8, "RGB").quantize(
        palette=pal_img, dither=Image.Dither.FLOYDSTEINBERG
    )
    return np.asarray(quantized.convert("RGB"))


# ---------------------------------------------------------------------------
# pipeline
# ---------------------------------------------------------------------------


def convert_array(
    rgb8: np.ndarray,
    pal_rgb: np.ndarray,
    *,
    ramp_rgb: np.ndarray | None = None,
    method: str = "nearest",
    dither: str = "none",
    chroma_weight: float = 1.0,
    softness: float = 0.10,
    keep_lightness: float = 0.0,
    normalize: bool = True,
) -> np.ndarray:
    """Recolor an (H, W, 3) uint8 array. Returns the same shape/dtype."""
    if method not in METHODS:
        raise ValueError(f"unknown method {method!r}; choose from: {', '.join(METHODS)}")
    if dither not in DITHERS:
        raise ValueError(f"unknown dither {dither!r}; choose from: {', '.join(DITHERS)}")
    if dither != "none" and method != "nearest":
        raise ValueError(f"dither {dither!r} only applies to method 'nearest'")

    h, w, _ = rgb8.shape
    pal_lab = oklab_from_u8(pal_rgb)
    ramp_lab = pal_lab if ramp_rgb is None else oklab_from_u8(ramp_rgb)
    target_lab = ramp_lab if method == "gradient" else pal_lab

    lab = oklab_from_u8(rgb8.reshape(-1, 3))
    # Normalization below rewrites the lightness column in place, so stash it
    # first — but only if it is going to be read again.
    src_lightness = lab[:, 0].copy() if keep_lightness > 0.0 else None

    if normalize:
        # Stretch source lightness onto the target's lightness range so a
        # bright photo does not collapse into the scheme's few light colors.
        p1, p99 = np.percentile(lab[:, 0], [1.0, 99.0])
        if p99 - p1 > 1e-6:
            lo, hi = target_lab[:, 0].min(), target_lab[:, 0].max()
            lab[:, 0] = np.clip((lab[:, 0] - p1) / (p99 - p1), 0.0, 1.0) * (hi - lo) + lo

    if dither == "floyd":
        # Error diffusion is inherently whole-image and Pillow runs it in sRGB,
        # so this path leaves the chunked Oklab mapping behind — which also
        # means keep_lightness has nothing to act on.
        return floyd_steinberg(u8_from_oklab(lab).reshape(h, w, 3), pal_rgb)

    if dither == "bayer":
        lab += bayer_offsets(h, w) * (palette_spacing(pal_lab) * np.array([1.0, 0.5, 0.5]))

    if method == "nearest":
        mapper = partial(map_nearest, pal_lab=pal_lab, chroma_weight=chroma_weight)
    elif method == "blend":
        mapper = partial(map_blend, pal_lab=pal_lab, chroma_weight=chroma_weight, softness=softness)
    else:
        mapper = partial(map_gradient, ramp_lab=ramp_lab[np.argsort(ramp_lab[:, 0])])

    out = np.empty_like(lab)
    for start in range(0, len(lab), CHUNK):
        out[start : start + CHUNK] = mapper(lab[start : start + CHUNK])

    if src_lightness is not None:
        # Re-introduce original detail by pulling lightness back toward source.
        out[:, 0] = out[:, 0] * (1 - keep_lightness) + src_lightness * keep_lightness

    return u8_from_oklab(out).reshape(h, w, 3)


def convert_image(image: Image.Image, pal_rgb: np.ndarray, **kwargs) -> Image.Image:
    """Recolor a PIL image, carrying any alpha channel through untouched."""
    alpha = image.convert("RGBA").getchannel("A") if image.has_transparency_data else None

    rgb8 = np.asarray(image.convert("RGB"))
    out = Image.fromarray(convert_array(rgb8, pal_rgb, **kwargs), "RGB")

    if alpha is not None:
        out.putalpha(alpha)
    return out


def palette_swatch(pal_rgb: np.ndarray, cell: int = 64) -> Image.Image:
    """A strip of the palette, handy for eyeballing a variant."""
    cols = min(len(pal_rgb), 8)
    rows = (len(pal_rgb) + cols - 1) // cols
    grid = np.zeros((rows * cols, 3), dtype=np.uint8)
    grid[: len(pal_rgb)] = pal_rgb
    grid = grid.reshape(rows, cols, 3)
    return Image.fromarray(np.repeat(np.repeat(grid, cell, 0), cell, 1), "RGB")


def default_output(path: Path, variant: str) -> Path:
    return path.with_name(f"{path.stem}-tokyonight-{variant}.png")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="convert.py",
        description="Recolor an image into the Tokyo Night colorscheme.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  ./convert.py wallpaper.png\n"
            "  ./convert.py photo.png -m blend -k 0.5 -o out.png\n"
            "  ./convert.py pixelart.png -d floyd --variant moon\n"
            "  ./convert.py --show-palette storm\n"
        ),
    )
    p.add_argument("images", nargs="*", type=Path, help="input image(s)")
    p.add_argument("-o", "--output", type=Path, help="output path (single input only)")
    p.add_argument(
        "--variant",
        default=DEFAULT_VARIANT,
        choices=sorted(PALETTES),
        help=f"Tokyo Night variant (default: {DEFAULT_VARIANT})",
    )
    p.add_argument(
        "-m",
        "--method",
        default="nearest",
        choices=METHODS,
        help="nearest: hard quantize; blend: soft mix; gradient: lightness ramp "
        "(default: nearest)",
    )
    p.add_argument(
        "-d",
        "--dither",
        default="none",
        choices=DITHERS,
        help="dithering for --method nearest (default: none)",
    )
    p.add_argument(
        "-k",
        "--keep-lightness",
        type=float,
        default=0.0,
        metavar="0..1",
        help="blend original lightness back in to retain detail; ignored with "
        "--dither floyd (default: 0)",
    )
    p.add_argument(
        "-c",
        "--chroma-weight",
        type=float,
        default=1.0,
        metavar="W",
        help="<1 matches on lightness, >1 chases hue (default: 1.0)",
    )
    p.add_argument(
        "-s",
        "--softness",
        type=float,
        default=0.10,
        metavar="S",
        help="mix radius for --method blend (default: 0.10)",
    )
    p.add_argument(
        "--ramp",
        default="neutral",
        choices=RAMPS,
        help="ramp used by --method gradient: the scheme's neutral spine, or "
        "every palette color sorted by lightness (default: neutral)",
    )
    p.add_argument(
        "--full-palette",
        action="store_true",
        help="include the near-duplicate UI chrome shades",
    )
    p.add_argument(
        "--no-normalize",
        dest="normalize",
        action="store_false",
        help="do not stretch source lightness onto the palette's range",
    )
    p.add_argument(
        "--show-palette",
        nargs="?",
        const=DEFAULT_VARIANT,
        choices=sorted(PALETTES),
        metavar="VARIANT",
        help="print the palette (and write swatch.png) instead of converting",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.show_palette:
        entries = get_palette(args.show_palette, full=args.full_palette)
        for role, rgb in entries:
            print(f"{role:>15}  {rgb_to_hex(rgb)}  {rgb}")
        out = Path(f"swatch-{args.show_palette}.png")
        palette_swatch(np.array([rgb for _, rgb in entries], dtype=np.uint8)).save(out)
        print(f"\n{len(entries)} colors -> {out}")
        return 0

    if not args.images:
        parser.error("no input images (or use --show-palette)")
    if args.output and len(args.images) > 1:
        parser.error("--output takes a single input image")
    if not 0.0 <= args.keep_lightness <= 1.0:
        parser.error("--keep-lightness must be between 0 and 1")
    if args.dither != "none" and args.method != "nearest":
        parser.error(f"--dither {args.dither} only applies to --method nearest")

    pal_rgb = np.array(
        [rgb for _, rgb in get_palette(args.variant, full=args.full_palette)],
        dtype=np.uint8,
    )
    ramp_rgb = None if args.ramp == "all" else np.array(get_ramp(args.variant), dtype=np.uint8)

    for path in args.images:
        if not path.is_file():
            print(f"skipping {path}: not a file", file=sys.stderr)
            continue
        with Image.open(path) as img:
            img.load()
            out_img = convert_image(
                img,
                pal_rgb,
                ramp_rgb=ramp_rgb,
                method=args.method,
                dither=args.dither,
                chroma_weight=args.chroma_weight,
                softness=args.softness,
                keep_lightness=args.keep_lightness,
                normalize=args.normalize,
            )
        dest = args.output or default_output(path, args.variant)
        out_img.save(dest)
        print(f"{path} -> {dest}  [{args.variant}/{args.method}"
              f"{'/' + args.dither if args.dither != 'none' else ''}]")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
