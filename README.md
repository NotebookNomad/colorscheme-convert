# colorscheme-convert

Recolor any image into a terminal/editor color scheme. Ships with 13 schemes and
reads your own from JSON. All color matching happens in **Oklab**, so "nearest
color" means nearest as the eye sees it rather than nearest in the RGB cube.

## Setup

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Usage

```sh
.venv/bin/python convert.py wallpaper.png
# -> wallpaper-tokyonight-night.png

.venv/bin/python convert.py wallpaper.png -t gruvbox-dark
# -> wallpaper-gruvbox-dark.png
```

```sh
convert.py [-o OUT] [-t THEME | --theme-file PATH] [--list-themes]
           [-m nearest|blend|gradient] [-d none|bayer|floyd]
           [-k 0..1] [-b B] [-c W] [-s S] [--ramp neutral|all]
           [--full-palette] [--no-normalize] [--show-palette] IMAGE [IMAGE ...]
```

Multiple inputs are converted in one pass (each gets an auto-named output);
`-o` is for a single input. Alpha channels pass through untouched.

## Themes

`--list-themes` shows what's available and where each one came from.

| | |
| --- | --- |
| Tokyo Night | `tokyonight-night` *(default)*, `tokyonight-storm`, `tokyonight-moon`, `tokyonight-day` |
| Gruvbox | `gruvbox-dark`, `gruvbox-light` |
| Catppuccin | `catppuccin-mocha`, `catppuccin-latte` |
| Others | `nord`, `dracula`, `solarized`, `rose-pine`, `everforest-dark` |

### Adding your own

Drop a `.json` file in `~/.config/colorscheme-convert/themes/` (or
`$XDG_CONFIG_HOME/colorscheme-convert/themes/`). The filename is the theme name,
so `synthwave.json` becomes `-t synthwave`. A user theme shadows a built-in of
the same name, so you can override any of the above. `--theme-file path.json`
loads one directly without installing it.

Built-in themes live in `themes/` and use the exact same format — copy one as a
starting point. Three shapes are accepted, smallest first:

```json
["#0b0f14", "#1b262c", "#3a5a6c", "#7fa1b3", "#c9d6db", "#e85d75", "#f0a35e"]
```

```json
{ "ink": "#12121a", "slate": "#2b2b3a", "ash": "#8a8a9e", "rust": "#c65f3f" }
```

```json
{
  "colors": { "bg": "#1a1b26", "mid": "#565f89", "fg": "#c0caf5", "red": "#f7768e" },
  "ramp": ["bg", "mid", "fg"],
  "exclude": ["mid"]
}
```

Both `#rgb` and `#rrggbb` are accepted. The two optional keys:

- **`ramp`** — the neutral dark-to-light spine used by `-m gradient`. Omit it and
  one is derived automatically by picking the palette's least saturated colors
  and sorting them by lightness, which is usually right; declare it when you
  want specific stops.
- **`exclude`** — colors to drop from matching by default, for shades that sit so
  close to another entry that they only add banding. `--full-palette` puts them
  back. Omit it and every color is used.

## Methods

| `-m` | What it does | Good for |
| --- | --- | --- |
| `nearest` *(default)* | Hard-quantizes every pixel to its closest palette color. Output contains **only** scheme colors. | Wallpapers, UI screenshots, the flat poster look |
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
- **`-b`, `--brightness`** — bends the tone curve before palette matching, so it
  steers *which* palette colors get picked rather than washing out the result
  afterwards. Below `1.0` darkens, above `1.0` lightens; `0.6`–`0.8` is the fix
  when output comes out too light. Endpoints stay put, so the full tonal range
  is still used.
- **`-c`, `--chroma-weight`** — below `1.0` matches mostly on lightness (safer,
  more neutral); above `1.0` chases hue and gets more colorful.
- **`-s`, `--softness`** (with `-m blend`) — mix radius. Smaller is punchier and
  closer to the palette, larger is smoother and more washed out.
- **`--ramp all`** (with `-m gradient`) — index every palette color by lightness
  instead of the neutral spine. Produces a deliberate rainbow banding effect.
- **`--no-normalize`** — by default the source lightness range is stretched onto
  the palette's range, so a bright photo doesn't collapse into the scheme's
  handful of light colors. Disable to preserve absolute exposure.
- **`--full-palette`** — include the shades a theme lists under `exclude`.

## Recipes

```sh
# Output came out too light — darken it
.venv/bin/python convert.py wall.png -b 0.7

# Wallpaper, strictly on-palette, softened banding
.venv/bin/python convert.py wall.png -d bayer

# Photo that keeps its detail
.venv/bin/python convert.py photo.png -m blend -k 0.5 -s 0.06

# Pixel art / low-color source
.venv/bin/python convert.py sprite.png -d floyd -t gruvbox-dark

# Light-theme version
.venv/bin/python convert.py diagram.png -t catppuccin-latte

# Try a palette without installing it
.venv/bin/python convert.py photo.png --theme-file ~/Downloads/palette.json

# Inspect a scheme (prints hex values, writes swatch-nord.png)
.venv/bin/python convert.py --show-palette -t nord
```

`sample.png` is a synthetic hue/lightness test chart — useful for comparing
options side by side.

## Using it as a library

```python
from PIL import Image
from convert import convert_image, resolve_palette
from theme import get_theme, load_theme_file

pal, ramp = resolve_palette(get_theme("catppuccin-mocha"))
out = convert_image(Image.open("in.png"), pal, ramp_rgb=ramp,
                    method="blend", keep_lightness=0.4)
out.save("out.png")
```

`load_theme_file(Path(...))` loads a scheme from disk by path. `convert_image` /
`convert_array` take the same keywords as the flags above and raise `ValueError`
on an unusable combination; theme loading raises `ValueError` on an unknown name
or malformed file.

## Accuracy note

Tokyo Night values follow the reference implementation of
[folke/tokyonight.nvim](https://github.com/folke/tokyonight.nvim). The other
schemes were transcribed from their published palettes; if you spot a hex that
drifts from upstream, it's a one-line fix in `themes/`.
