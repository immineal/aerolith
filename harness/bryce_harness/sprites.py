"""Turn Bryce renders into web sprites with real alpha.

Bryce 2 has no alpha channel, so each element is rendered against two known backdrops
(black and white, same scene otherwise) and optionally once as a flat-white silhouette:

    alpha  = 1 - (white - black) / 255        (difference matting; glass gets partial alpha)
    colour = black / alpha                    (un-premultiply)
    mask   = silhouette render (crisp coverage, antialiased); clamps alpha outside the object

Renders are made at `ss`x the target size and box-filtered down for clean antialiasing.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image


def load(p) -> np.ndarray:
    return np.asarray(Image.open(p).convert("RGB"), dtype=np.float64) / 255.0


def difference_matte(black: np.ndarray, white: np.ndarray, mask: np.ndarray | None = None,
                     floor: float = 0.0) -> np.ndarray:
    """RGBA float image from renders over a black and a white backdrop."""
    diff = (white - black).mean(axis=2)
    alpha = np.clip(1.0 - diff, 0.0, 1.0)
    if mask is not None:
        m = mask.mean(axis=2) if mask.ndim == 3 else mask
        alpha = np.minimum(alpha, m) if floor <= 0 else np.minimum(np.maximum(alpha, floor * m), m)
    a = np.maximum(alpha, 1e-6)[..., None]
    rgb = np.clip(black / a, 0.0, 1.0)
    rgb[alpha <= 1e-6] = 0.0
    return np.dstack([rgb, alpha])


def downsample(rgba: np.ndarray, factor: int) -> np.ndarray:
    """Box-filter downsample in premultiplied space (no dark fringes)."""
    if factor == 1:
        return rgba
    h, w = rgba.shape[:2]
    h2, w2 = h // factor, w // factor
    x = rgba[:h2 * factor, :w2 * factor]
    pre = np.dstack([x[..., :3] * x[..., 3:4], x[..., 3:4]])
    pre = pre.reshape(h2, factor, w2, factor, 4).mean(axis=(1, 3))
    a = pre[..., 3:4]
    rgb = np.where(a > 1e-6, pre[..., :3] / np.maximum(a, 1e-6), 0.0)
    return np.dstack([rgb, a[..., 0]])


def to_image(rgba: np.ndarray) -> Image.Image:
    return Image.fromarray(np.clip(np.round(rgba * 255), 0, 255).astype(np.uint8), "RGBA")


def trim(img: Image.Image, pad: int = 2) -> tuple[Image.Image, tuple[int, int, int, int]]:
    """Crop to the non-transparent bounding box (+pad). Returns the image and the box used."""
    bb = img.getchannel("A").point(lambda v: 255 if v > 2 else 0).getbbox()
    if not bb:
        return img, (0, 0, img.width, img.height)
    x0, y0, x1, y1 = bb
    box = (max(0, x0 - pad), max(0, y0 - pad), min(img.width, x1 + pad), min(img.height, y1 + pad))
    return img.crop(box), box


def make_sprite(black_path, white_path, out_path, mask_path=None, ss: int = 1, pad: int = 2,
                do_trim: bool = True) -> dict:
    black, white = load(black_path), load(white_path)
    mask = load(mask_path) if mask_path else None
    rgba = downsample(difference_matte(black, white, mask), ss)
    img = to_image(rgba)
    box = (0, 0, img.width, img.height)
    if do_trim:
        img, box = trim(img, pad)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, optimize=True)
    return {"file": str(out_path), "size": img.size, "box": box}


def slice3(img: Image.Image, left: int, right: int) -> dict:
    """Horizontal 3-slice for stretchable pills/bars: CSS border-image widths."""
    return {"width": img.width, "height": img.height, "slice": [0, right, 0, left]}


def slice9(img: Image.Image, top: int, right: int, bottom: int, left: int) -> dict:
    return {"width": img.width, "height": img.height, "slice": [top, right, bottom, left]}
