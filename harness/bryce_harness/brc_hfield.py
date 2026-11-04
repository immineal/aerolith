"""Bryce 2 heightfields: terrains and symmetrical lattices (C3dHeightField, tag `3dobhfld`).

See docs/brc/heightfield.md for the record layout and how each field was verified.

    from bryce_harness import brc, brc_hfield as hf
    sb = brc.SceneBuilder()
    h = hf.rounded_rect(300, 120, radius=40, bevel=30)          # float 0..1, any size
    hf.add_heightfield(sb, h, offset=(0, 0, 0), rotate=(-90, 0, 0), size=(60, 6, 24),
                       material=dict(diffuse="#2a7fff", specularity=0.9), symmetric=True)

Geometry (verified by renders):
  * grid g[i, j] (N x N, big-endian u16) -> local point (x=j, y=g/65535*(N-1), z=i)
  * world = position + R * diag(scale) * (local - pivot), pivot = BE f64 triple at 0xe0
  * a terrain is a solid: walls run down from the edge to y=0 and the h=0 floor is a face;
    a symmetrical lattice mirrors the surface below y=0, so h=0 areas have no thickness.

This module's conventions:
  * `heights[r, c]` reads like an image. With rotate=(0,0,0) the field lies flat, heights go
    up +Y, image columns run along +X and image row 0 is the far edge (+Z). With
    rotate=(-90,0,0) it faces a camera on -Z and reads upright.
  * offset = centre of the footprint at height 0 (the mirror plane of a lattice).
  * size = (width along X, height of h=1.0 along Y, depth along Z) in Bryce units (B).
"""
from __future__ import annotations

import math
import struct

import numpy as np

from . import brc

TAG = b"3dobhfld"
CLS = "C3dHeightField"

# ---- record layout (offsets into slot A). BE = big-endian, LE = raw x86 little-endian
HF_PIVOT = 0xe0          # 3 x f64 BE  pivot in grid units (Bryce writes N/2); used by the renderer
HF_PIVOT_LE = 0x1a0      # 3 x f64 LE  cached copy of HF_PIVOT (Bryce rebuilds it on load)
HF_BBOX_MIN = 0x2f0      # 3 x f64 BE  local bounding box (terrain: 0,0,0   lattice: 0,-N,0)
HF_BBOX_MAX = 0x308      # 3 x f64 BE  (terrain: N-1 x3   lattice: N x3)
HF_CLIP_LO = 0x338       # f64 BE  clip below this normalized height (Bryce 2.1 default -0.01)
HF_CLIP_HI = 0x340       # f64 BE  clip above (default 1.01)
HF_N = 0x348             # u32 BE  grid resolution N (square grid)
HF_SYMMETRIC = 0x34c     # u8      1 = symmetrical lattice, 0 = terrain (bytes 0x34d..0x34f = 0)
HF_GRID = 0x350          # N*N u16 BE, row-major; row index i -> local z, column j -> local x
HEADER = HF_GRID         # 848 bytes; record size = 848 + 2*N*N

RESOLUTIONS = (32, 64, 128, 256, 512)   # auto-picked sizes; any N in 32..512 works (100 tested).
N_MIN, N_MAX = 32, 512                  # 16 is rejected (scene not loaded); 1024 renders but off-size
GRID_VERSION = 0x2ec     # u8 (struct +0): 1 = 16-bit samples. 0 = samples x4 (14-bit, wraps). Keep 1


def _tpl(kind: str) -> tuple[bytes, bytes]:
    a = (brc.TEMPLATES / f"C3dHeightField_{kind}.a").read_bytes()
    t = (brc.TEMPLATES / f"C3dHeightField_{kind}.tail").read_bytes()
    return a, t


# --------------------------------------------------------------------------- reading
def grid_of(rec: bytes) -> np.ndarray:
    """-> (N, N) uint16 grid exactly as stored (row i = local z, column j = local x)."""
    n = struct.unpack_from(">I", rec, HF_N)[0]
    return np.frombuffer(rec, ">u2", n * n, HF_GRID).reshape(n, n).astype(np.uint16)


def info(rec: bytes) -> dict:
    """Decoded header. extent_b = world size of the grid (x, y at h=1, z) in B before rotation;
    transform = brc.get_transform (its 'size' uses the primitive convention, not useful here)."""
    n = struct.unpack_from(">I", rec, HF_N)[0]
    sc = struct.unpack_from("<3d", rec, brc.T_SCALE)
    return dict(
        n=n, symmetric=bool(rec[HF_SYMMETRIC]), grid_version=rec[GRID_VERSION],
        pivot=struct.unpack_from(">3d", rec, HF_PIVOT),
        bbox_min=struct.unpack_from(">3d", rec, HF_BBOX_MIN),
        bbox_max=struct.unpack_from(">3d", rec, HF_BBOX_MAX),
        clip=struct.unpack_from(">2d", rec, HF_CLIP_LO),
        extent_b=tuple(s * (n - 1) * brc.UNIT for s in sc),
        transform=brc.get_transform(rec))


def fix_legacy_clip(rec: bytes) -> bytes:
    """Bryce 2.0 sample scenes store clip in 16-bit sample units (e.g. -0.0001 / 65536.0000016,
    or 1983.9999 as a floor cut). Bryce 2.1 reads clip as normalized heights, so a low clip > 1
    hides the whole object. Divide such values by 65535 (verified by render)."""
    lo, hi = struct.unpack_from(">2d", rec, HF_CLIP_LO)
    if max(abs(lo), abs(hi)) <= 2.0:
        return rec
    a = bytearray(rec)
    struct.pack_into(">2d", a, HF_CLIP_LO, lo / 65535.0, hi / 65535.0)
    return bytes(a)


def heights_of(rec: bytes) -> np.ndarray:
    """Inverse of this module's convention: float 0..1 image (row 0 = far edge, +Z)."""
    return grid_of(rec)[::-1].astype(np.float64) / 65535.0


# --------------------------------------------------------------------------- resampling
def pick_n(shape, n=None) -> int:
    if n:
        if not N_MIN <= n <= N_MAX:
            raise ValueError(f"N must be in {N_MIN}..{N_MAX}")
        return int(n)
    m = max(shape)
    for r in RESOLUTIONS:
        if r >= m:
            return r
    return RESOLUTIONS[-1]


def resample(heights: np.ndarray, n: int) -> np.ndarray:
    """Resample a float image to n x n so that its corner samples land on the corner vertices."""
    h = np.asarray(heights, np.float64)
    if h.shape == (n, n):
        return h
    from scipy import ndimage
    zy = (n - 1) / max(h.shape[0] - 1, 1)
    zx = (n - 1) / max(h.shape[1] - 1, 1)
    # order 3 spline on a corner-aligned grid; clip the spline's overshoot
    yy = np.linspace(0, h.shape[0] - 1, n)
    xx = np.linspace(0, h.shape[1] - 1, n)
    gy, gx = np.meshgrid(yy, xx, indexing="ij")
    if min(zy, zx) < 1:      # downsampling: Lanczos prefilter avoids aliasing
        from PIL import Image
        im = Image.fromarray(h.astype(np.float32), "F").resize((n, n), Image.LANCZOS)
        out = np.asarray(im, np.float64)
    else:                    # upsampling: cubic spline through the samples
        out = ndimage.map_coordinates(h, [gy, gx], order=3, mode="nearest")
    return np.clip(out, h.min(), h.max())


def to_u16(h: np.ndarray) -> np.ndarray:
    return np.clip(np.round(np.clip(h, 0.0, 1.0) * 65535.0), 0, 65535).astype(np.uint16)


# --------------------------------------------------------------------------- record
def make_record(heights: np.ndarray, offset=(0, 0, 0), rotate=(0, 0, 0), size=None,
                symmetric: bool = False, clip=None, n: int | None = None,
                pivot: str = "base", bbox: str = "full") -> bytes:
    """Build a complete C3dHeightField record (slot A) without a material reference.

    heights: float array 0..1 (image convention, see module doc), any shape; resampled to N.
    size: (x, y, z) in B; x/z = footprint, y = height of 1.0. Default: longest side 20.48 B,
          aspect from the array, height 20.48 * 0.25.
    clip: (lo, hi) normalized heights; parts outside are cut away. Default (-0.01, 1.01).
    pivot: "base" -> offset is the footprint centre at height 0 (written as pivot
           ((N-1)/2, 0, (N-1)/2)); "bryce" -> Bryce's own N/2 pivot (offset = centre of the
           N-cube, half a cell off the footprint centre).
    bbox: "full" -> (0..N) in x/z, avoids Bryce's sawtooth along the +X/+Z edge;
          "bryce" -> exactly what Bryce writes (0..N-1, sawtooth on edge cells).
    """
    h = np.asarray(heights, np.float64)
    if h.ndim != 2:
        raise ValueError("heights must be 2-D")
    H, W = h.shape
    N = pick_n(h.shape, n)
    g = to_u16(resample(h, N))[::-1]          # image row 0 -> far edge (+Z) = grid row N-1
    if size is None:
        k = 20.48 / max(H, W)
        size = (W * k, 20.48 * 0.25, H * k)
    sx, sy, sz = (float(v) for v in size)

    a = bytearray(_tpl("lattice" if symmetric else "terrain")[0])
    a[0x88:0x90] = bytes(8)                   # object flags (selection etc.): cleared
    if pivot == "base":
        c = ((N - 1) / 2, 0.0, (N - 1) / 2)
    elif pivot == "bryce":
        c = (N / 2,) * 3
    else:
        c = tuple(float(v) for v in pivot)
    struct.pack_into(">3d", a, HF_PIVOT, *c)
    struct.pack_into("<3d", a, HF_PIVOT_LE, *c)
    if bbox == "bryce":
        lo, hi = ((0, -N, 0), (N, N, N)) if symmetric else ((0, 0, 0), (N - 1,) * 3)
    else:
        lo, hi = ((0, -N, 0) if symmetric else (0, 0, 0)), (N, N, N)
    struct.pack_into(">3d", a, HF_BBOX_MIN, *lo)
    struct.pack_into(">3d", a, HF_BBOX_MAX, *hi)
    struct.pack_into(">2d", a, HF_CLIP_LO, *(clip if clip is not None else (-0.01, 1.01)))
    struct.pack_into(">I", a, HF_N, N)
    a[HF_SYMMETRIC:HF_SYMMETRIC + 4] = bytes([1 if symmetric else 0, 0, 0, 0])

    # transform: scale maps grid units to internal units (1 internal = 10.24 B)
    sc = (sx / brc.UNIT / (N - 1), sy / brc.UNIT / (N - 1), sz / brc.UNIT / (N - 1))
    rad = [math.radians(v) for v in rotate]
    pos = [v / brc.UNIT for v in offset]
    struct.pack_into("<3d", a, brc.T_SCALE, *sc)
    struct.pack_into("<3d", a, brc.T_ROT, *rad)
    struct.pack_into("<3d", a, brc.T_POS, *pos)
    m = np.diag(sc) @ brc._rot(*rad).T
    struct.pack_into("<9d", a, brc.T_MATRIX, *m.ravel())
    struct.pack_into("<3d", a, brc.T_TRANS, *pos)
    return bytes(a) + g.astype(">u2").tobytes()


def add_heightfield(sb: "brc.SceneBuilder", heights: np.ndarray, offset=(0, 0, 0), rotate=(0, 0, 0),
                    size=None, material: dict | brc.Obj | None = None, symmetric: bool = False,
                    clip=None, n: int | None = None, **kw) -> brc.Obj:
    """Add a terrain (or symmetrical lattice) to a SceneBuilder. See make_record for arguments."""
    rec = bytearray(make_record(heights, offset, rotate, size, symmetric, clip, n, **kw))
    mat = material if isinstance(material, brc.Obj) else sb.material(**(material or {}))
    struct.pack_into(">I", rec, brc.OBJ_MATERIAL_REF, mat.oid)
    tail = _tpl("lattice" if symmetric else "terrain")[1]
    o = brc.Obj(CLS, sb.scene.new_oid(), bytes(rec), b"", tail)
    sb.scene.insert(o)
    return o


# --------------------------------------------------------------------------- shape helpers
PROFILES = ("ease", "quartic", "pillow", "round", "linear")


def shape_profile(t: np.ndarray, profile: str = "ease") -> np.ndarray:
    """Edge profile over t = 0 (outline) .. 1 (inner end of the bevel).
    ease:   1-(1-t)^3, finite slope at the outline, flat top. Clean silhouettes (recommended).
    pillow: cosine, zero slope at both ends: softest, dome-like.
    round:  quarter circle. Vertical at the outline, which Bryce's grid shows as ripples and
            jagged clip contours unless N is high and the bevel wide.
    linear: chamfer.
    quartic: 1-(1-t)^4, like ease but its curvature fades to zero at the inner end, so the edge runs
            into the flat face with no visible shoulder (glass lens)."""
    if profile == "ease":
        return 1 - (1 - t) ** 3
    if profile == "quartic":
        return 1 - (1 - t) ** 4
    if profile == "pillow":
        return 0.5 - 0.5 * np.cos(np.pi * t)
    if profile == "round":
        return np.sqrt(1 - (1 - t) ** 2)
    if profile == "linear":
        return t
    raise ValueError(f"profile must be one of {PROFILES}")


def rounded_rect(w: int, h: int, radius: float, bevel: float, profile: str = "ease",
                 pad: int = 2) -> np.ndarray:
    """Pillow/button height map (float 0..1), w x h pixels including `pad` zero pixels.
    radius: corner radius of the outline (px). bevel: width of the rising edge (px).
    profile: see shape_profile."""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    cx, cy = (w - 1) / 2, (h - 1) / 2
    hx, hy = w / 2 - pad, h / 2 - pad
    r = min(radius, hx, hy)
    qx = np.abs(xx - cx) - (hx - r)
    qy = np.abs(yy - cy) - (hy - r)
    outside = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - r
    d = np.clip(-outside, 0, None)            # distance inside the outline (px)
    return shape_profile(np.clip(d / max(bevel, 1e-6), 0, 1), profile)


def signed_distance(mask: np.ndarray, ss: int = 1, blur: float = 0.7) -> np.ndarray:
    """Signed distance to the edge of a mask (>0 inside), in output pixels.
    Draw the mask `ss` times larger than the output (e.g. 2048 px for a 512 grid, ss=4): the
    distance is computed at full size and box-averaged down, which removes the staircase of an
    aliased edge. `blur` (output px) smooths what is left; without these two, a steep bevel
    shows ripple bands along curves in Bryce's render."""
    from scipy import ndimage
    m = np.asarray(mask, np.float64)
    if m.max() > 1:
        m = m / 255.0
    inside = m >= 0.5
    sd = np.where(inside, ndimage.distance_transform_edt(inside) - 0.5,
                  -(ndimage.distance_transform_edt(~inside) - 0.5))
    if ss > 1:
        H, W = (sd.shape[0] // ss) * ss, (sd.shape[1] // ss) * ss
        sd = sd[:H, :W].reshape(H // ss, ss, W // ss, ss).mean((1, 3)) / ss
    if blur:
        sd = ndimage.gaussian_filter(sd, blur)
    return sd


def from_mask(mask: np.ndarray, bevel: float, profile: str = "ease", ss: int = 1,
              blur: float = 0.7) -> np.ndarray:
    """Emboss a mask (e.g. a glyph drawn with PIL; white = raised): the height rises over
    `bevel` output px from the mask edge, so strokes get rounded shoulders. Returns float 0..1
    of size mask.shape // ss. See signed_distance for ss/blur."""
    sd = signed_distance(mask, ss, blur)
    return shape_profile(np.clip(sd / max(bevel, 1e-6), 0, 1), profile)
