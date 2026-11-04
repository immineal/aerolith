"""Gel inflation of a 2D mask: round cross-sections without the medial-axis crease that a
distance-transform bevel leaves (which reads as chiselled once it catches a highlight).

Solve  laplace(u) = -1  inside the mask, u = 0 outside. For a straight stroke of width w this gives
u = x (w - x) / 2, so sqrt(2u) is a semicircle of radius w/2: every stroke becomes a round tube, and
junctions blend smoothly because u is smooth everywhere inside."""
from __future__ import annotations

import numpy as np
from PIL import Image
from scipy import ndimage, sparse
from scipy.sparse.linalg import spsolve


def poisson(inside: np.ndarray) -> np.ndarray:
    """u with laplace(u) = -1 on `inside` (bool), 0 elsewhere; grid spacing 1."""
    idx = -np.ones(inside.shape, dtype=np.int64)
    ys, xs = np.nonzero(inside)
    idx[ys, xs] = np.arange(len(ys))
    n = len(ys)
    rows, cols, vals = [np.arange(n)], [np.arange(n)], [np.full(n, 4.0)]
    H, W = inside.shape
    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        y2, x2 = ys + dy, xs + dx
        ok = (y2 >= 0) & (y2 < H) & (x2 >= 0) & (x2 < W)
        j = np.full(n, -1)
        j[ok] = idx[y2[ok], x2[ok]]
        m = j >= 0
        rows.append(np.arange(n)[m]); cols.append(j[m]); vals.append(np.full(m.sum(), -1.0))
    A = sparse.csr_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(n, n))
    u = np.zeros(inside.shape)
    u[ys, xs] = spsolve(A, np.ones(n))
    return u


def inflate(mask: np.ndarray, ss: int, radius: float, soft: float = 0.35) -> np.ndarray:
    """mask: supersampled (ss x) uint8/float, white = inside. radius: stroke half-width (output px)
    that reaches full height 1. Wider areas are soft-clipped (no flat plateaus, no runaway domes).
    Returns float 0..1 of size mask.shape // ss."""
    m = np.asarray(mask, dtype=np.float64) / 255.0
    n0, n1 = m.shape[0] // ss, m.shape[1] // ss
    cover = m[:n0 * ss, :n1 * ss].reshape(n0, ss, n1, ss).mean(axis=(1, 3))   # area coverage
    # solve on a 2x grid for smoother interiors (at least 1024 cells across), then average down
    k = 2 if max(n0, n1) < 512 else 1
    big = np.asarray(Image.fromarray((m * 255).astype(np.uint8)).resize((n1 * k, n0 * k), Image.BOX)) / 255.0
    u = poisson(big > 0.5) * 1.0 / (k * k)          # back to output-pixel units (u scales with length^2)
    r = np.sqrt(2 * np.maximum(u, 0))                # semicircle height in output px
    r = r.reshape(n0, k, n1, k).mean(axis=(1, 3))
    h = r / radius
    h = h / (1 + soft * np.maximum(h - 1, 0) ** 1) if soft else h          # gentle above 1
    h = np.where(h > 1, 1 + (1 - np.exp(-(h - 1) * 2)) * 0.15, h)           # soft cap ~1.15
    h = h / 1.15
    # subpixel silhouette: fade the outermost pixel by coverage so edges stay antialiased
    edge = ndimage.binary_erosion(cover > 0.5) ^ (cover > 0.5)
    h = np.where(edge, h * np.clip(cover * 1.5, 0, 1), h)
    h = ndimage.gaussian_filter(h, 0.6) * (cover > 0.02)
    return np.clip(h, 0, 1)


def shade(h: np.ndarray, scale: float = 30.0) -> Image.Image:
    """Quick preview: Lambert + a sharp specular from the upper left, on grey."""
    gy, gx = np.gradient(h * scale)
    nz = 1 / np.sqrt(gx ** 2 + gy ** 2 + 1)
    nx, ny = -gx * nz, -gy * nz
    L = np.array([-0.4, -0.6, 0.7]); L /= np.linalg.norm(L)
    lam = np.clip(nx * L[0] + ny * L[1] + nz * L[2], 0, 1)
    Hh = L + np.array([0, 0, 1]); Hh /= np.linalg.norm(Hh)
    spec = np.clip(nx * Hh[0] + ny * Hh[1] + nz * Hh[2], 0, 1) ** 60
    base = np.dstack([0.1 + 0.25 * lam, 0.35 + 0.4 * lam, 0.75 + 0.25 * lam]) + spec[..., None]
    a = (h > 0.01)[..., None]
    out = np.where(a, base, 0.85)
    return Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8))
