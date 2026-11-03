"""Sheet → web sprites.

Sheets are rendered at RENDER_SCALE (6) render pixels per CSS px: 3x device pixel ratio with 2x
supersampling. A sprite box on the sheet is snapped to the 6-px grid, so every DPR variant is
an exact box-filter of the same pixels:

    @3x = 2x2 average, @2x = 3x3, @1x = 6x6     (premultiplied alpha, no fringes)

Each sprite is described in CSS px (size, slice insets, label box) and produces
dist/sprites/<name>@{1,2,3}x.png plus an entry in the manifest used for CSS generation and
for the accessibility checks.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field, asdict
from pathlib import Path

import numpy as np
from PIL import Image

RENDER_SCALE = 6
DPRS = (1, 2, 3)
LIB = Path(__file__).resolve().parents[1]
DIST = LIB / "dist"


@dataclass
class Sprite:
    name: str                       # e.g. "btn-primary-m-hover"; a ".dark" suffix = dark-theme variant
    box: tuple                      # (x0, y0, x1, y1) crop region on the sheet, render px
    slice: tuple | None = None      # (top, right, bottom, left) insets, CSS px, measured from `shape`
    shape: tuple | None = None      # (x0, y0, x1, y1) the object's outline, render px: everything
                                    # outside it (glow, shadow, glint) becomes border-image-outset
    label: tuple | None = None      # (x0, y0, x1, y1) CSS px relative to `shape`: where text sits
    text: str | None = None         # text colour used on it, '#rrggbb'
    hit: tuple | None = None        # (w, h) CSS px of the interactive area (target-size check)
    meta: dict = field(default_factory=dict)


def box_downsample(rgba: np.ndarray, f: int) -> np.ndarray:
    if f == 1:
        return rgba
    h, w = rgba.shape[0] // f * f, rgba.shape[1] // f * f
    x = rgba[:h, :w]
    pre = np.dstack([x[..., :3] * x[..., 3:4], x[..., 3:4]])
    pre = pre.reshape(h // f, f, w // f, f, 4).mean(axis=(1, 3))
    a = pre[..., 3:4]
    rgb = np.where(a > 1e-6, pre[..., :3] / np.maximum(a, 1e-6), 0.0)
    return np.dstack([rgb, a[..., 0]])


def snap(box, sheet_shape, grid=RENDER_SCALE):
    x0, y0, x1, y1 = box
    x0, y0 = x0 // grid * grid, y0 // grid * grid
    x1, y1 = -(-x1 // grid) * grid, -(-y1 // grid) * grid
    h, w = sheet_shape[:2]
    return max(0, x0), max(0, y0), min(w // grid * grid, x1), min(h // grid * grid, y1)


def alpha_box(rgba: np.ndarray, box, thresh=0.004, pad_css=1):
    """Tight box around the visible pixels inside `box`, padded by pad_css CSS px."""
    x0, y0, x1, y1 = box
    a = rgba[y0:y1, x0:x1, 3] > thresh
    ys, xs = np.where(a)
    if not len(xs):
        return box
    p = pad_css * RENDER_SCALE
    return (x0 + xs.min() - p, y0 + ys.min() - p, x0 + xs.max() + 1 + p, y0 + ys.max() + 1 + p)


def to_png(rgba: np.ndarray, path: Path):
    img = Image.fromarray(np.clip(np.round(rgba * 255), 0, 255).astype(np.uint8), "RGBA")
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, optimize=True)


def optimise(paths):
    paths = [str(p) for p in paths]
    if paths:
        subprocess.run(["optipng", "-quiet", "-o2", *paths], check=False)


def export(sheet_rgba: np.ndarray, sprite: Sprite, out_dir: Path = DIST / "sprites", trim=True) -> dict:
    box = alpha_box(sheet_rgba, sprite.box) if trim else sprite.box
    box = snap(tuple(int(v) for v in box), sheet_rgba.shape)
    if sprite.shape:   # never crop into the object itself
        sx0, sy0, sx1, sy1 = snap(tuple(int(v) for v in sprite.shape), sheet_rgba.shape)
        box = (min(box[0], sx0), min(box[1], sy0), max(box[2], sx1), max(box[3], sy1))
    x0, y0, x1, y1 = box
    crop = sheet_rgba[y0:y1, x0:x1]
    files = {}
    for dpr in DPRS:
        f = RENDER_SCALE // dpr
        p = out_dir / f"{sprite.name}@{dpr}x.png"
        to_png(box_downsample(crop, f), p)
        files[dpr] = p
    entry = asdict(sprite)
    entry["box"] = box
    entry["size"] = ((x1 - x0) // RENDER_SCALE, (y1 - y0) // RENDER_SCALE)
    entry["files"] = {d: str(p.relative_to(out_dir.parent)) for d, p in files.items()}
    if sprite.shape:
        sx0, sy0, sx1, sy1 = snap(tuple(int(v) for v in sprite.shape), sheet_rgba.shape)
        R = RENDER_SCALE
        out = ((sy0 - y0) // R, (x1 - sx1) // R, (y1 - sy1) // R, (sx0 - x0) // R)
        entry["outset"] = out
        entry["shape_size"] = ((sx1 - sx0) // R, (sy1 - sy0) // R)
        if sprite.slice:
            entry["slice_px"] = tuple(a + o for a, o in zip(sprite.slice, out))
    elif sprite.slice:
        entry["slice_px"] = tuple(sprite.slice)
    return entry


# ------------------------------------------------------------------ manifest + CSS
def write_manifest(entries: list[dict], path: Path = DIST / "sprites.json"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({e["name"]: e for e in entries}, indent=1))


def css_vars(entries: list[dict]) -> str:
    """Custom properties per sprite, switched by device resolution (and theme) with @media.

    --aer-<name>          url() of the sprite at the current DPR (".dark" entries override it in dark mode)
    --aer-<name>-slice    border-image-slice in that image's raw pixels (+ fill)
    --aer-<name>-border   the slice insets in CSS px (= border-image-width for a 1:1 draw)
    --aer-<name>-outset   how far the image reaches beyond the object outline (border-image-outset)
    --aer-<name>-w / -h   outline size in CSS px (the element box the sprite is designed for)

    Plain url() + raw-pixel slices behave identically in Chrome, Firefox and Safari;
    image-set() inside border-image does not (Firefox reads the slices differently)."""
    light = [e for e in entries if not e["name"].endswith(".dark")]
    dark = [e for e in entries if e["name"].endswith(".dark")]

    def block(es, dpr):
        out = []
        for e in es:
            n = e["name"].removesuffix(".dark")
            out.append(f'  --aer-{n}: url("{e["files"][dpr]}");')
            if e.get("slice_px"):
                t, r, b, l = e["slice_px"]
                out.append(f"  --aer-{n}-slice: {t * dpr:g} {r * dpr:g} {b * dpr:g} {l * dpr:g} fill;")
        return out

    def px(v):
        return " ".join(f"{x:g}px" if x else "0" for x in v)

    base = [":root {"]
    for e in light:
        n = e["name"]
        w, h = e.get("shape_size") or e["size"]
        base.append(f"  --aer-{n}-w: {w}px; --aer-{n}-h: {h}px;")
        if e.get("slice_px"):
            base.append(f"  --aer-{n}-border: {px(e['slice_px'])};")
        base.append(f"  --aer-{n}-outset: {px(e.get('outset') or (0, 0, 0, 0))};")
    base += block(light, 1) + ["}"]
    out = base
    res = ((2, "(min-resolution: 1.5dppx)"), (3, "(min-resolution: 2.5dppx)"))
    for dpr, q in res:
        out += [f"@media {q} {{", ":root {"] + block(light, dpr) + ["}", "}"]
    if dark:
        sel_cls = ':root[data-theme="dark"], .aer-dark'
        sel_auto = ':root:not([data-theme="light"])'
        for dpr, q in ((1, None),) + res:
            body = block(dark, dpr)
            auto = "(prefers-color-scheme: dark)" + (f" and {q}" if q else "")
            out += [f"@media {auto} {{", f"{sel_auto} {{"] + body + ["}", "}"]
            if q:
                out += [f"@media {q} {{", f"{sel_cls} {{"] + body + ["}", "}"]
            else:
                out += [f"{sel_cls} {{"] + body + ["}"]
    return "\n".join(out) + "\n"
