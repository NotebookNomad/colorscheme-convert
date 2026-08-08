"""Oklab conversions.

Kept apart from the pipeline so that both the image code and the theme code can
match colors perceptually without importing each other.
"""

from __future__ import annotations

import numpy as np

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


def chroma(lab: np.ndarray) -> np.ndarray:
    """(..., 3) Oklab -> colorfulness, 0 for pure greys."""
    return np.hypot(lab[..., 1], lab[..., 2])
