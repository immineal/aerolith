"""Aerolith Display: gel letters rendered in Bryce, for big titles only.

Each glyph is Istok Web Bold, set a touch heavier (the mask is dilated), inflated into round tubes
(inflate.py) and rendered alone like every other sprite. fontbuild.py packs the renders into colour
fonts, so titles stay real text. Reserved Font Name: the result is not called Istok."""
from __future__ import annotations

import functools
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import inflate

SRC = Path(__file__).resolve().parent / "fonts" / "IstokWeb-Bold.ttf"

CHARSET = ("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
           ".,:;!?'\"-&()/@#%+*=_[]{}<>$|~^`\\"
           "ÄÖÜäöüßéèàçñ€’‘“”–—…·×")

CELL = 112        # sprite box, CSS px (square: the lattice is square)
CAP = 0.52        # cap height / cell
BASE = 0.77       # baseline from the top / cell
GROW = 0.02       # dilation diameter / cell (heavier than Istok Bold)
RADIUS = 0.0645   # stem half-width / cell that reaches full height (measured on "I")
THICK = 16        # Bryce height of a full tube, CSS px (deeper reads as glass, shallower as plastic)
MARGIN = 6
N = 512           # lattice (256 left 1-device-px stairs on the outline at 2x)
SS = 4


@functools.lru_cache(None)
def _font(px: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(SRC), px)


def em_px(cell: float = CELL) -> float:
    """Em size in px for a sprite of `cell` px (cap height fixed at CAP * cell)."""
    from fontTools.ttLib import TTFont
    t = TTFont(str(SRC))
    return CAP * cell * t["head"].unitsPerEm / t["OS/2"].sCapHeight


def _place(ch: str, S: int):
    f = _font(int(round(em_px(S))))
    x0, _, x1, _ = f.getbbox(ch, anchor="ls")
    return f, S / 2 - (x0 + x1) / 2


def mask(ch: str, n: int = N) -> np.ndarray:
    S = n * SS
    f, x = _place(ch, S)
    im = Image.new("L", (S, S), 0)
    ImageDraw.Draw(im).text((x, BASE * S), ch, font=f, fill=255, anchor="ls")
    from scipy import ndimage                       # = PIL MaxFilter (square), bit for bit, 250x faster
    return ndimage.maximum_filter(np.asarray(im), size=int(GROW * S) | 1, mode="constant", cval=0)


@functools.lru_cache(None)
def heights(ch: str, n: int = N) -> np.ndarray:
    return inflate.inflate(mask(ch, n), SS, radius=RADIUS * n)


def glyph_offset_em(ch: str) -> float:
    """Where the sprite centre sits, in em from the glyph origin (sprites are centred on the
    glyph's ink box)."""
    big = 4096
    f = _font(big)
    x0, _, x1, _ = f.getbbox(ch, anchor="ls")
    return (x0 + x1) / 2 / big


def grow_em() -> float:
    """Dilation radius in em (added to both sidebearings, so spacing stays Istok's)."""
    return GROW * CELL / 2 / em_px()


# ------------------------------------------------------------------ exact outline for the matte
OUTLINE_N = 512   # mask px per CELL / SS for the reference outline (2048 px per cell)


@functools.lru_cache(maxsize=8)
def _sdf(ch: str) -> np.ndarray:
    """Signed distance to the grown glyph outline, in reference-mask px (> 0 outside)."""
    from scipy import ndimage
    m = mask(ch, OUTLINE_N) > 127
    return ndimage.distance_transform_edt(~m) - ndimage.distance_transform_edt(m)


def outline(ch: str, cov: np.ndarray, px_per_css: float):
    """Exact coverage of the glyph outline on a rendered sheet, registered to the rendered
    silhouette `cov` (Bryce's mask pass: binary, its edge in lattice-grid steps).

    Bryce's silhouette sits wherever the heightfield leaves the floor, so it follows the lattice in
    steps (1 device px at 2x with a 256 lattice, half that at 512). The matte swaps it for this
    analytic edge: same placement and weight as the render, no steps.
    Returns (coverage in sheet px, residual RMS of the fit in sheet px)."""
    from scipy import ndimage, optimize
    D = _sdf(ch)
    k = D.shape[0] / (CELL * px_per_css)            # reference px per sheet px
    inside = cov > 0.5
    pts = []                                        # silhouette edge: midpoints inside|outside
    for dy, dx in ((0, 1), (1, 0)):
        a, b = inside[:inside.shape[0] - dy, :inside.shape[1] - dx], inside[dy:, dx:]
        ys, xs = np.nonzero(a != b)
        pts.append(np.c_[ys + 0.5 + dy / 2, xs + 0.5 + dx / 2])
    pts = np.concatenate(pts)
    if len(pts) < 8:
        return None, float("inf")

    def dev(off):
        q = (pts - off) * k - 0.5
        return ndimage.map_coordinates(D, q.T, order=1, mode="nearest") / k

    def spread(off):
        d = dev(off)
        return np.abs(d - np.median(d)).mean()
    c0 = (np.array(cov.shape) - CELL * px_per_css) / 2
    step = px_per_css / 2
    grid = [c0 + [dy, dx] for dy in np.arange(-8, 8.1) * step for dx in np.arange(-8, 8.1) * step]
    best = min(grid, key=spread)
    off = optimize.minimize(lambda o: np.var(dev(o)), best, method="Nelder-Mead",
                            options={"xatol": 0.01, "fatol": 1e-6}).x
    d = dev(off)
    bias = float(np.median(d))                      # the render is a little heavier: keep its weight
    rms = float(np.sqrt(np.mean((d - bias) ** 2)))
    yy, xx = np.mgrid[0:cov.shape[0], 0:cov.shape[1]] + 0.5
    sd = ndimage.map_coordinates(D, [(yy - off[0]) * k - 0.5, (xx - off[1]) * k - 0.5],
                                 order=1, mode="nearest") / k
    return np.clip(0.5 - (sd - bias), 0, 1), rms
