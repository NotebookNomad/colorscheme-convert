# colorscheme-convert

Recolor any image into the [Tokyo Night](https://github.com/folke/tokyonight.nvim)
colorscheme. All color matching happens in **Oklab**, so "nearest color" means
nearest as the eye sees it rather than nearest in the RGB cube.

## Setup

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Usage

```sh
.venv/bin/python convert.py wallpaper.png
# -> wallpaper-tokyonight-night.png
```

```sh
convert.py [-o OUT] [--variant night|storm|moon|day]
           [-m nearest|blend|gradient] [-d none|bayer|floyd]
           [-k 0..1] [-c W] [-s S] [--ramp neutral|all]
           [--full-palette] [--no-normalize] IMAGE [IMAGE ...]
```

Multiple inputs are converted in one pass (each gets an auto-named output);
`-o` is for a single input. Alpha channels pass through untouched.

## Methods

| `-m` | What it does | Good for |
| --- | --- | --- |
| `nearest` *(default)* | Hard-quantizes every pixel to its closest palette color. Output contains **only** Tokyo Night colors. | Wallpapers, UI screenshots, the flat poster look |
| `blend` | Softmax-weighted mix of nearby palette colors. Smooth, no banding, but colors are off-palette. | Photographs, gradients |
| `gradient` | Classic gradient map: source lightness indexes the scheme's neutral dark→light ramp. | Monochrome, tinted look |

## Tuning

- **`-d`, `--dither`** (with `-m nearest`) — `bayer` for a clean ordered
  crosshatch, `floyd` for error diffusion. Dithering trades hard color bands
  for texture and keeps the output strictly on-palette.
- **`-k`, `--keep-lightness`** `0..1` — mixes the original lightness back into
  the result, restoring detail that quantizing flattened. `0.4`–`0.6` rescues
  a photo that came out too posterized. Note this pulls pixels off-palette, and
  that it has no effect under `-d floyd`, which quantizes in sRGB.
- **`-c`, `--chroma-weight`** — below `1.0` matches mostly on lightness (safer,
  more neutral); above `1.0` chases hue and gets more colorful.
- **`-s`, `--softness`** (with `-m blend`) — mix radius. Smaller is punchier and
  closer to the palette, larger is smoother and more washed out.
- **`--ramp all`** (with `-m gradient`) — index every palette color by lightness
  instead of the neutral spine. Produces a deliberate rainbow banding effect.
- **`--no-normalize`** — by default the source lightness range is stretched onto
  the palette's range, so a bright photo doesn't collapse into the scheme's
  handful of light colors. Disable to preserve absolute exposure.
- **`--full-palette`** — include the near-duplicate UI chrome shades
  (`bg_highlight`, `fg_gutter`, `terminal_black`, `dark3`, `dark5`), which are
  dropped by default because they only add banding on photographic input.

## Recipes

```sh
# Wallpaper, strictly on-palette, softened banding
.venv/bin/python convert.py wall.png -d bayer

# Photo that keeps its detail
.venv/bin/python convert.py photo.png -m blend -k 0.5 -s 0.06

# Pixel art / low-color source
.venv/bin/python convert.py sprite.png -d floyd --variant moon

# Light-theme version
.venv/bin/python convert.py diagram.png --variant day -m nearest

# Inspect a variant (prints hex values, writes swatch-storm.png)
.venv/bin/python convert.py --show-palette storm
```

`sample.png` is a synthetic hue/lightness test chart — useful for comparing
options side by side.

## Using it as a library

```python
from PIL import Image
import numpy as np
from convert import convert_image
from palettes import get_palette

pal = np.array([rgb for _, rgb in get_palette("moon")], dtype=np.uint8)
out = convert_image(Image.open("in.png"), pal, method="blend", keep_lightness=0.4)
out.save("out.png")
```

`convert_image` / `convert_array` take the same keywords as the flags above and
raise `ValueError` on an unusable combination; `get_palette` raises `ValueError`
for an unknown variant.
