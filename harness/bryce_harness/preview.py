"""Preview helpers: composite RGBA sprites over test backgrounds."""
from __future__ import annotations
import numpy as np
from PIL import Image


def backdrop(w, h, kind="aero"):
    y = np.linspace(0, 1, h)[:, None, None]
    x = np.linspace(0, 1, w)[None, :, None]
    if kind == "aero":      # sky-to-grass Frutiger Aero gradient
        top, mid, bot = np.array([0.45, 0.75, 1.0]), np.array([0.85, 0.95, 1.0]), np.array([0.55, 0.85, 0.35])
        c = np.where(y < 0.6, top + (mid - top) * (y / 0.6), mid + (bot - mid) * ((y - 0.6) / 0.4))
        return np.broadcast_to(c, (h, w, 3)).copy()
    if kind == "checker":
        c = (((np.arange(h)[:, None] // 12) + (np.arange(w)[None, :] // 12)) % 2) * 0.25 + 0.6
        return np.repeat(c[..., None], 3, 2)
    if kind == "dark":
        return np.broadcast_to(np.array([0.08, 0.1, 0.16]) + 0.1 * x, (h, w, 3)).copy()
    raise ValueError(kind)


def over(rgba: np.ndarray, kind="aero") -> np.ndarray:
    h, w = rgba.shape[:2]
    bg = backdrop(w, h, kind)
    a = rgba[..., 3:4]
    return rgba[..., :3] * a + bg * (1 - a)


def strip(rgba: np.ndarray, kinds=("aero", "checker", "dark")) -> Image.Image:
    panels = [over(rgba, k) for k in kinds]
    return Image.fromarray(np.clip(np.concatenate(panels, 0) * 255, 0, 255).astype(np.uint8))
