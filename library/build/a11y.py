"""Accessibility checks that need the actual rendered pixels.

Glossy sprites are not one colour, so "the" background contrast of a label is the worst case
over every pixel under the label box, after compositing the sprite over each page background
it may sit on (semi-transparent glass lets the page through).
"""
from __future__ import annotations

import numpy as np
from PIL import Image

PAGE_BACKGROUNDS = {"light": "#f4f8fc", "dark": "#10161f", "sky": "#7fb8ec", "grass": "#86c95a"}


def hex_rgb(h: str) -> np.ndarray:
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], float) / 255


def srgb_to_lin(c):
    c = np.asarray(c, float)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def luminance(rgb) -> np.ndarray:
    lin = srgb_to_lin(rgb)
    return lin[..., 0] * 0.2126 + lin[..., 1] * 0.7152 + lin[..., 2] * 0.0722


def wcag_ratio(l1, l2):
    hi, lo = np.maximum(l1, l2), np.minimum(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def apca_lc(text_rgb, bg_rgb):
    """APCA-W3 0.1.9 lightness contrast (signed; |Lc| 60 ≈ body text minimum, 75 preferred)."""
    def y(c):
        c = np.asarray(c, float)
        v = (c ** 2.4) @ np.array([0.2126729, 0.7151522, 0.0721750])
        return np.where(v > 0.022, v, v + np.clip(0.022 - v, 0, None) ** 1.414)
    yt, yb = y(text_rgb), y(bg_rgb)
    normal = (yb ** 0.56 - yt ** 0.57) * 1.14
    reverse = (yb ** 0.65 - yt ** 0.62) * 1.14
    s = np.where(yb > yt, normal, reverse)
    s = np.where(np.abs(s) < 0.1, 0.0, np.where(s > 0, s - 0.027, s + 0.027))
    return s * 100


def composite(sprite: np.ndarray, page_hex: str) -> np.ndarray:
    a = sprite[..., 3:4]
    return sprite[..., :3] * a + hex_rgb(page_hex) * (1 - a)


def label_contrast(sprite_png: str, label_box_css, text_hex: str, dpr: int = 1,
                   backgrounds=PAGE_BACKGROUNDS, pct: float = 0.0) -> dict:
    """Worst-case (or `pct` percentile) WCAG ratio and APCA |Lc| of text over the label box.
    Returns per page background."""
    img = np.asarray(Image.open(sprite_png).convert("RGBA"), float) / 255
    x0, y0, x1, y1 = (int(round(v * dpr)) for v in label_box_css)
    region = img[y0:y1, x0:x1]
    t = hex_rgb(text_hex)
    out = {}
    for name, bg in backgrounds.items():
        px = composite(region, bg).reshape(-1, 3)
        r = wcag_ratio(luminance(px), luminance(t))
        lc = np.abs(apca_lc(t, px))
        out[name] = {"wcag_min": float(np.percentile(r, pct * 100)), "apca_min": float(np.percentile(lc, pct * 100))}
    return out


def edge_contrast(sprite_png: str, backgrounds=PAGE_BACKGROUNDS, ring_px: int = 2) -> dict:
    """Non-text contrast (WCAG 1.4.11) of a control's outer boundary against each page background:
    median luminance ratio of the opaque rim pixels vs the page colour."""
    from scipy import ndimage
    img = np.asarray(Image.open(sprite_png).convert("RGBA"), float) / 255
    solid = img[..., 3] > 0.5
    rim = solid & ~ndimage.binary_erosion(solid, iterations=ring_px)
    out = {}
    for name, bg in backgrounds.items():
        px = composite(img, bg)[rim]
        r = wcag_ratio(luminance(px), luminance(hex_rgb(bg)))
        out[name] = float(np.median(r)) if len(r) else 0.0
    return out


def report(manifest="../dist/sprites.json", pct=0.05, dpr=3, band=(0.25, 0.75)):
    """Label contrast of every sprite that declares a label box and text colour, at the `pct`
    percentile of the label area (before any text halo). Light sprites are checked over the
    light, sky and grass pages; ".dark" sprites over the dark page."""
    import json
    from pathlib import Path
    base = Path(manifest).resolve().parent
    entries = json.loads(Path(manifest).read_text())
    rows = []
    for name, e in sorted(entries.items()):
        if not e.get("label") or not e.get("text") or name.startswith("btn-disabled"):
            continue
        t, r, b, l = e.get("outset") or (0, 0, 0, 0)
        x0, y0, x1, y1 = e["label"]
        # the glyph band: cap height of a centred label line, not the whole flat face
        y0, y1 = y0 + (y1 - y0) * band[0], y0 + (y1 - y0) * band[1]
        box = (x0 + l, y0 + t, x1 + l, y1 + t)
        dark = name.endswith(".dark")
        bgs = {"dark": PAGE_BACKGROUNDS["dark"]} if dark else {k: v for k, v in PAGE_BACKGROUNDS.items() if k != "dark"}
        res = label_contrast(str(base / e["files"][str(dpr)] if isinstance(next(iter(e["files"])), str) else base / e["files"][dpr]),
                             box, e["text"], dpr, bgs, pct)
        worst = min(v["wcag_min"] for v in res.values())
        rows.append((name, e["text"], worst))
    return rows


if __name__ == "__main__":
    for name, text, worst in report():
        flag = "ok " if worst >= 4.5 else "AA-large" if worst >= 3 else "LOW"
        print(f"{flag:8} {worst:5.2f}  {text}  {name}")
