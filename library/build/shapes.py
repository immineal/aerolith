"""2D masks / height maps for UI shapes (drawn supersampled, returned as 0..1 heights)."""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "harness"))
from bryce_harness.brc_hfield import from_mask  # noqa: E402

N = 512        # heightfield grid
SS = 4         # mask supersampling


def _canvas(n=N):
    return Image.new("L", (n * SS, n * SS), 0)


def emboss(draw_fn, bevel=0.08, profile="ease", n=N):
    """draw_fn(draw, S) draws white on a S x S canvas (S = n*SS) in unit coords * S.
    bevel = fraction of the grid width. Returns n x n heights."""
    im = _canvas(n)
    draw_fn(ImageDraw.Draw(im), n * SS)
    return from_mask(np.asarray(im), bevel * n, profile=profile, ss=SS, blur=0.7)


def tick(width=0.16):
    def d(dr, S):
        pts = [(0.18 * S, 0.52 * S), (0.42 * S, 0.76 * S), (0.84 * S, 0.24 * S)]
        w = int(width * S)
        dr.line(pts, fill=255, width=w, joint="curve")
        for x, y in (pts[0], pts[-1]):
            dr.ellipse([x - w / 2, y - w / 2, x + w / 2, y + w / 2], fill=255)
    return emboss(d, bevel=0.07)


def heart():
    def d(dr, S):
        pts = []
        for i in range(400):
            t = 2 * math.pi * i / 400
            x = 16 * math.sin(t) ** 3
            y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
            pts.append((S / 2 + x * S / 36, S * 0.47 - y * S / 36))
        dr.polygon(pts, fill=255)
    return emboss(d, bevel=0.12)


def disc():
    def d(dr, S):
        dr.ellipse([0.02 * S, 0.02 * S, 0.98 * S, 0.98 * S], fill=255)
    return emboss(d, bevel=0.3, profile="pillow")
