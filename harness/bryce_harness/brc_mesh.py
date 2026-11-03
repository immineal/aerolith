"""Triangle meshes (C3dTriMeshType, tag `3dobtmsh`) for Bryce 2 scenes. See docs/brc/mesh.md.

Record layout (slot A), after the common object header and LE transform block (0x000-0x2ef,
identical to the primitives' 749-byte record except 0x2ec = 1):

    0x2f0  BE u32 vertex capacity, vertex count
    0x2f8  BE u32 normal capacity, normal count   (0, 0 until the mesh is smoothed)
    0x300  BE u32 face capacity, face count
    0x308  vertex array: vcap x 3 LE f64 (x, y, z), each axis normalised to -1024..1024
    ....   normal array: ncap x 3 LE f64, unit-ish corner normals (object space)
    ....   face array: fcap x 76-byte BE records
             +0  u32 i0, i1, i2       vertex indices
             +12 u32 n0, n1, n2       normal indices (0 when unsmoothed)
             +24 f64 nx, ny, nz       face normal = normalize(cross(v1-v0, v2-v0))
             +48 u32 f0, f1, f2, s    (1,1,1,0) flat; (0,0,0,1) after Polyhedrons > Smooth;
                                       (1,1,1,1) after Unsmooth
             +64 u32 x3               runtime pointers (+64 = face material; garbage on disk, 0 works)

Unused capacity slots are zero. Object space is -1024..1024 per axis; the scale in the transform
block maps it to world units: bbox extent in B = 2 * 1024 * scale * 10.24, i.e. add_mesh(size=...) is
the rendered bounding-box extent in B, the same convention as a C3dSphere's Size (render-verified,
work/re_mesh/t9.png). Bryce's own smoothing writes one normal per face corner (3 x faces normals).
A corner is smooth-shaded only if its flag (+48+4k) is 0 AND the face's +60 word is 1.

    sb = brc.SceneBuilder()
    add_mesh(sb, *rounded_box(4, 2, 1, 0.4, 6), offset=(0, 10, 0), size=(40, 20, 10),
             material=dict(diffuse='#2a7fff', specularity=0.9), smooth=True)
"""
from __future__ import annotations

import math
import struct

import numpy as np

from . import brc

TEMPLATE_HEAD = brc.TEMPLATES / "C3dTriMeshType.head"     # 0x2f0 bytes, from PINE.BRC id 40
TEMPLATE_TAIL = brc.TEMPLATES / "C3dTriMeshType.tail"
CLASS = "C3dTriMeshType"

M_FLAG_2EC = 0x2ec        # u8 = 1 in every mesh record (0 in primitives)
M_VERT_HDR = 0x2f0        # BE u32 capacity, count
M_AUX_HDR = 0x2f8         # BE u32 0, 0
M_FACE_HDR = 0x300        # BE u32 capacity, count
M_VERTS = 0x308
FACE_SIZE = 76
VERT_SIZE = 24
EXTENT = 1024.0           # object-space half extent per axis


# =========================================================================== record codec

def decode(rec: bytes) -> dict:
    """-> dict(vertices (N,3) object space, normals (K,3), faces (M,3), normal_idx (M,3),
    face_normals (M,3), flags (M,4), pointers (M,3), vcap, ncap, fcap)."""
    vcap, vn, ncap, nn, fcap, fn = struct.unpack_from(">6I", rec, M_VERT_HDR)
    v = np.frombuffer(rec, "<f8", vn * 3, M_VERTS).reshape(-1, 3).copy()
    no = M_VERTS + vcap * VERT_SIZE
    nrm = np.frombuffer(rec, "<f8", nn * 3, no).reshape(-1, 3).copy()
    fo = no + ncap * VERT_SIZE
    raw = np.frombuffer(rec, np.uint8, fn * FACE_SIZE, fo).reshape(fn, FACE_SIZE)
    u = raw.copy().view(">u4").reshape(fn, 19)
    fnrm = raw[:, 24:48].copy().view(">f8").reshape(fn, 3)
    return dict(vertices=v, normals=nrm, faces=u[:, 0:3].astype(int), normal_idx=u[:, 3:6].astype(int),
                face_normals=fnrm, flags=u[:, 12:16], pointers=u[:, 16:19], vcap=vcap, ncap=ncap, fcap=fcap)


def _unit(n):
    ln = np.linalg.norm(n, axis=-1, keepdims=True)
    return np.where(ln > 0, n / np.where(ln > 0, ln, 1), 0.0)


def corner_normals(vo, f, crease_deg: float = 60.0):
    """Per-corner normals (M,3,3): angle-weighted average of the face normals around each
    vertex, using only faces whose normal is within crease_deg of the corner's own face."""
    fn = _unit(np.cross(vo[f[:, 1]] - vo[f[:, 0]], vo[f[:, 2]] - vo[f[:, 0]]))
    ang = np.zeros(f.shape)
    for k in range(3):
        a = vo[f[:, (k + 1) % 3]] - vo[f[:, k]]
        b = vo[f[:, (k + 2) % 3]] - vo[f[:, k]]
        ang[:, k] = np.arctan2(np.linalg.norm(np.cross(a, b), axis=1), (a * b).sum(1))
    # faces around each vertex
    order = np.argsort(f.ravel(), kind="stable")
    verts_sorted = f.ravel()[order]
    starts = np.searchsorted(verts_sorted, np.arange(len(vo) + 1))
    cos_t = math.cos(math.radians(crease_deg))
    out = np.zeros((len(f), 3, 3))
    for vi in range(len(vo)):
        corners = order[starts[vi]:starts[vi + 1]]          # flat corner ids = face*3 + k
        if len(corners) == 0:
            continue
        fi, ki = corners // 3, corners % 3
        nrm, w = fn[fi], ang[fi, ki]
        sim = nrm @ nrm.T >= cos_t                         # (c, c) which neighbours to blend
        acc = sim.astype(float) @ (nrm * w[:, None])
        out[fi, ki] = _unit(acc)
    bad = np.linalg.norm(out, axis=2) == 0
    out[bad] = np.repeat(fn[:, None, :], 3, axis=1)[bad]
    return out


def encode(vertices, faces, smooth: bool = True, crease_deg: float = 60.0,
           corner_nrm=None) -> tuple[bytes, np.ndarray, np.ndarray]:
    """Mesh part of the record (from 0x2f0). Vertices are normalised per axis to +-1024.
    smooth: write per-corner normals like Bryce's Polyhedrons > Smooth (edges sharper than
    crease_deg stay hard). corner_nrm: optional (M,3,3) normals in the caller's space.
    Returns (bytes, centre, half_extent) of the input vertices so the caller can place it."""
    v = np.asarray(vertices, float)
    f = np.asarray(faces, np.int64)
    if v.ndim != 2 or v.shape[1] != 3 or f.ndim != 2 or f.shape[1] != 3:
        raise ValueError("vertices must be (N,3), faces (M,3)")
    if f.min() < 0 or f.max() >= len(v):
        raise ValueError("face index out of range")
    lo, hi = v.min(0), v.max(0)
    centre = (lo + hi) / 2
    half = (hi - lo) / 2
    half_safe = np.where(half > 1e-12, half, 1.0)
    vo = (v - centre) / half_safe * EXTENT
    vo = vo.astype(np.float32).astype(np.float64)        # Bryce stores float32-precision values
    fnrm = _unit(np.cross(vo[f[:, 1]] - vo[f[:, 0]], vo[f[:, 2]] - vo[f[:, 0]]))
    nv, nf = len(v), len(f)
    if smooth:
        if corner_nrm is not None:     # normals transform with the inverse-transpose of the scaling
            cn = _unit(np.asarray(corner_nrm, float).reshape(nf, 3, 3) * (half_safe / EXTENT))
        else:
            cn = corner_normals(vo, f, crease_deg)
        nn = 3 * nf
    else:
        nn = 0
    out = bytearray(struct.pack(">6I", nv, nv, nn, nn, nf, nf))
    out += vo.astype("<f8").tobytes()
    if nn:
        out += cn.reshape(-1, 3).astype("<f8").tobytes()
    rec = np.zeros((nf, FACE_SIZE), np.uint8)
    u = np.zeros((nf, 19), ">u4")
    u[:, 0:3] = f
    if smooth:
        u[:, 3:6] = np.arange(3 * nf).reshape(nf, 3)
        u[:, 15] = 1
    else:
        u[:, 12:15] = 1
    rec[:] = u.view(np.uint8).reshape(nf, FACE_SIZE)
    rec[:, 24:48] = fnrm.astype(">f8").view(np.uint8).reshape(nf, 24)
    out += rec.tobytes()
    return bytes(out), centre, half


def mesh_record(vertices, faces, smooth=True, crease_deg=60.0, head: bytes | None = None,
                corner_nrm=None):
    """Whole record (header from the template) -> (bytes, centre, half_extent)."""
    head = bytearray(head if head is not None else TEMPLATE_HEAD.read_bytes())[:M_VERT_HDR]
    head[M_FLAG_2EC] = 1
    body, c, h = encode(vertices, faces, smooth, crease_deg, corner_nrm)
    return bytes(head) + body, c, h


# =========================================================================== scene API

def set_mesh_transform(rec: bytes, offset, rotate, size) -> bytes:
    """offset in B (centre of the bounding box), rotate in degrees, size = full bbox extent in B."""
    s_prim = [sz / EXTENT for sz in size]   # bbox extent in B = 2 * 1024 * scale * UNIT
    return brc.set_transform(rec, offset=tuple(offset), rotate=tuple(rotate), size=tuple(s_prim))


def add_mesh(sb: "brc.SceneBuilder", vertices, faces, offset=None, rotate=(0, 0, 0), size=None,
             material: dict | brc.Obj | None = None, smooth: bool = True, crease_deg: float = 60.0,
             normals=None, name: str = "") -> brc.Obj:
    """Add a triangle mesh. Vertices are in Bryce units (B); faces index them, wound so that
    cross(v1-v0, v2-v0) points outward. offset/size default to the vertices' own bounding box
    (offset = bbox centre, size = bbox extent in B); give them to place/stretch the mesh.
    smooth=True writes per-corner normals (Phong shading); edges whose faces meet at more than
    crease_deg stay sharp. normals: optional exact normals in the vertices' space, either per
    vertex (N,3) or per face corner (M,3,3), e.g. capsule_normals(); they replace the averaged ones."""
    cn = None
    if normals is not None:
        nrm = np.asarray(normals, float)
        cn = nrm[np.asarray(faces)] if nrm.shape == np.asarray(vertices).shape else nrm
    rec, centre, half = mesh_record(vertices, faces, smooth, crease_deg, corner_nrm=cn)
    off = tuple(centre) if offset is None else tuple(offset)
    sz = tuple(np.maximum(2 * half, 1e-6)) if size is None else tuple(size)
    rec = bytearray(set_mesh_transform(rec, off, rotate, sz))
    if name:
        rec[:0x80] = name.encode("latin-1")[:127].ljust(0x80, b"\0")
    mat = material if isinstance(material, brc.Obj) else sb.material(**(material or {}))
    struct.pack_into(">I", rec, brc.OBJ_MATERIAL_REF, mat.oid)
    o = brc.Obj(CLASS, sb.scene.new_oid(), bytes(rec), b"", TEMPLATE_TAIL.read_bytes())
    sb.scene.insert(o)
    return o


# =========================================================================== generators
# All return (vertices (N,3) float, faces (M,3) int), outward-facing (cross(v1-v0, v2-v0) out).

def _orient_outward(v, f):
    """Flip faces whose normal points toward the centroid (fine for star-shaped solids)."""
    c = v.mean(0)
    n = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
    m = (v[f[:, 0]] + v[f[:, 1]] + v[f[:, 2]]) / 3
    bad = (n * (m - c)).sum(1) < 0
    f = f.copy()
    f[bad] = f[bad][:, [0, 2, 1]]
    return f


def _grid_faces(rows, cols, wrap_u=True):
    """Quads over a (rows x cols) vertex grid -> triangles. wrap_u closes the u direction."""
    faces = []
    cu = cols if wrap_u else cols - 1
    for i in range(rows - 1):
        for j in range(cu):
            a = i * cols + j
            b = i * cols + (j + 1) % cols
            c = (i + 1) * cols + (j + 1) % cols
            d = (i + 1) * cols + j
            faces += [(a, b, c), (a, c, d)]
    return np.array(faces, np.int64)


def weld(v, f, tol=1e-9):
    """Merge duplicate vertices and drop degenerate faces (needed for smooth shading)."""
    v = np.asarray(v, float)
    key = np.round(v / max(tol, 1e-12)).astype(np.int64)
    _, idx, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    inv = inv.ravel()
    nf = inv[np.asarray(f)]
    ok = (nf[:, 0] != nf[:, 1]) & (nf[:, 1] != nf[:, 2]) & (nf[:, 0] != nf[:, 2])
    return v[idx], nf[ok]


def capsule(w=4.0, h=1.0, depth=None, segments=32, cap_segments=None):
    """Horizontal pill along x: total length w, height h, depth (z, default h). A cylinder body
    with semi-ellipsoidal end caps (hemispheres when depth == h), one closed welded surface.
    segments = vertices around the body; cap_segments = rings per cap (default segments // 4)."""
    depth = h if depth is None else depth
    r = h / 2
    body = max(0.0, w / 2 - r)
    nc = cap_segments or max(2, segments // 4)
    ring_t = np.linspace(0, 2 * math.pi, segments, endpoint=False)
    cy, cz = np.cos(ring_t) * h / 2, np.sin(ring_t) * depth / 2
    rings = []          # (x, scale) from the -x pole to the +x pole, poles excluded
    for k in range(1, nc + 1):
        a = math.pi / 2 * k / nc                          # 0 at the pole, 90 deg at the body
        rings.append((-body - r * math.cos(a), math.sin(a)))
    for k in range(nc, 0, -1):
        a = math.pi / 2 * k / nc
        rings.append((body + r * math.cos(a), math.sin(a)))
    verts = [(-body - r, 0.0, 0.0)]
    for x, sc in rings:
        verts += [(x, y * sc, z * sc) for y, z in zip(cy, cz)]
    verts.append((body + r, 0.0, 0.0))
    v = np.array(verts)
    n = segments
    faces = []
    last = len(v) - 1
    for j in range(n):
        faces.append((0, 1 + j, 1 + (j + 1) % n))
    for i in range(len(rings) - 1):
        a0, b0 = 1 + i * n, 1 + (i + 1) * n
        for j in range(n):
            j1 = (j + 1) % n
            faces += [(a0 + j, b0 + j, b0 + j1), (a0 + j, b0 + j1, a0 + j1)]
    a0 = 1 + (len(rings) - 1) * n
    for j in range(n):
        faces.append((last, a0 + (j + 1) % n, a0 + j))
    v, f = weld(v, np.array(faces, np.int64), tol=1e-9 * max(w, h, depth))
    return v, _orient_outward(v, f)


def capsule_normals(v, w=4.0, h=1.0, depth=None):
    """Exact outward normals of capsule(w, h, depth) at its vertices: the gradient of
    (dx/r)^2 + (y/(h/2))^2 + (z/(depth/2))^2 with dx = distance past the cylinder body, r = h/2."""
    depth = h if depth is None else depth
    v = np.asarray(v, float)
    r = h / 2
    body = max(0.0, w / 2 - r)
    dx = v[:, 0] - np.clip(v[:, 0], -body, body)
    g = np.c_[dx / r ** 2, v[:, 1] / r ** 2, v[:, 2] / (depth / 2) ** 2]
    return _unit(g)


def rounded_box_normals(v, w=2.0, h=2.0, d=2.0, r=0.3):
    """Exact outward normals of rounded_box(w, h, d, r) at its vertices."""
    r = max(1e-9, min(r, w / 2, h / 2, d / 2))
    inner = np.array([w / 2 - r, h / 2 - r, d / 2 - r])
    v = np.asarray(v, float)
    return _unit(v - np.clip(v, -inner, inner))


def superellipsoid(rx=1.0, ry=1.0, rz=1.0, e1=0.3, e2=0.3, nu=48, nv=24):
    """Superellipsoid |x|^(2/e2)... with exponents e1 (latitude) and e2 (longitude).
    e=1: ellipsoid; e->0: box; ~0.2-0.35: a rounded box. Poles are single vertices."""
    def spow(x, p):
        return np.sign(x) * np.abs(x) ** p
    verts = [(0.0, ry, 0.0)]
    for i in range(1, nv):
        eta = math.pi / 2 - math.pi * i / nv
        ce, se = math.cos(eta), math.sin(eta)
        for j in range(nu):
            w = -math.pi + 2 * math.pi * j / nu
            cw, sw = math.cos(w), math.sin(w)
            verts.append((rx * spow(ce, e1) * spow(cw, e2), ry * spow(se, e1), rz * spow(ce, e1) * spow(sw, e2)))
    verts.append((0.0, -ry, 0.0))
    v = np.array(verts, float)
    faces = []
    top, bot = 0, len(v) - 1
    ring = lambda i: 1 + (i - 1) * nu       # first vertex of latitude ring i (1..nv-1)
    for j in range(nu):
        faces.append((top, ring(1) + (j + 1) % nu, ring(1) + j))
    for i in range(1, nv - 1):
        for j in range(nu):
            a, b = ring(i) + j, ring(i) + (j + 1) % nu
            c, d = ring(i + 1) + (j + 1) % nu, ring(i + 1) + j
            faces += [(a, b, c), (a, c, d)]
    for j in range(nu):
        faces.append((bot, ring(nv - 1) + j, ring(nv - 1) + (j + 1) % nu))
    f = np.array(faces, np.int64)
    return v, _orient_outward(v, f)


def rounded_box(w=2.0, h=2.0, d=2.0, r=0.3, segments=8):
    """Box w x h x d (centred at 0) with every edge and corner rounded by radius r.
    Built as a subdivided cube whose points are pushed onto the rounded surface
    (p = clamp(q, inner box) + r * normalize(q - clamp(q))), so flat faces stay flat (2 triangles
    per flat span) and the arcs get `segments` steps per 90 degrees. Vertices are welded."""
    r = max(1e-9, min(r, w / 2, h / 2, d / 2))
    inner = np.array([w / 2 - r, h / 2 - r, d / 2 - r])
    n2 = max(1, int(round(segments / 2)))
    th = np.radians(45.0 * np.arange(1, n2 + 1) / n2)

    def coords(hh):
        arc = hh + r * np.tan(th)
        return np.concatenate([-arc[::-1], [-hh, hh], arc])

    verts, faces = [], []
    for ax in range(3):
        ua, va = [a for a in range(3) if a != ax]
        cu, cv = coords(inner[ua]), coords(inner[va])
        for sgn in (1, -1):
            base = len(verts)
            for x in cu:
                for y in cv:
                    q = np.zeros(3)
                    q[ax], q[ua], q[va] = sgn * (inner[ax] + r), x, y
                    c = np.clip(q, -inner, inner)
                    dv = q - c
                    verts.append(c + r * dv / np.linalg.norm(dv))
            m = len(cv)
            for i in range(len(cu) - 1):
                for j in range(m - 1):
                    a0, b0 = base + i * m + j, base + (i + 1) * m + j
                    faces += [(a0, b0, b0 + 1), (a0, b0 + 1, a0 + 1)]
    v, f = weld(np.array(verts), np.array(faces, np.int64), tol=1e-7 * max(w, h, d))
    return v, _orient_outward(v, f)


def _poly_area(p):
    x, y = p[:, 0], p[:, 1]
    return 0.5 * (x * np.roll(y, -1) - np.roll(x, -1) * y).sum()


def _ear_clip(poly):
    """Triangulate a simple polygon (CCW, (N,2)) -> list of index triples."""
    idx = list(range(len(poly)))
    tris = []

    def inside(p, a, b, c):
        def s(p1, p2, p3):
            return (p1[0] - p3[0]) * (p2[1] - p3[1]) - (p2[0] - p3[0]) * (p1[1] - p3[1])
        d1, d2, d3 = s(p, a, b), s(p, b, c), s(p, c, a)
        return not ((d1 < 0 or d2 < 0 or d3 < 0) and (d1 > 0 or d2 > 0 or d3 > 0))

    guard = 0
    while len(idx) > 3 and guard < 10000:
        guard += 1
        for k in range(len(idx)):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            a, b, c = poly[i0], poly[i1], poly[i2]
            if (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]) <= 1e-12:
                continue
            if any(inside(poly[j], a, b, c) for j in idx if j not in (i0, i1, i2)):
                continue
            tris.append((i0, i1, i2))
            idx.pop(k)
            break
        else:
            break
    if len(idx) == 3:
        tris.append(tuple(idx))
    return tris


def _offset_polygon(p, dist):
    """Miter-offset a CCW polygon outward by dist (negative = inward)."""
    n = len(p)
    out = np.zeros_like(p)
    for i in range(n):
        a, b, c = p[i - 1], p[i], p[(i + 1) % n]
        e1, e2 = b - a, c - b
        n1 = np.array([e1[1], -e1[0]]) / np.linalg.norm(e1)
        n2 = np.array([e2[1], -e2[0]]) / np.linalg.norm(e2)
        m = n1 + n2
        lm = np.linalg.norm(m)
        if lm < 1e-9:
            out[i] = b + n1 * dist
            continue
        m /= lm
        cos_half = max(np.dot(m, n1), 0.2)       # limit spikes at sharp corners
        out[i] = b + m * dist / cos_half
    return out


def extrude(polygon_2d, depth=1.0, bevel=0.0, bevel_segments=3):
    """Extrude a simple 2-D polygon (x, y) along z from -depth/2 to +depth/2, with an optional
    rounded bevel of width `bevel` on both caps (the outline is inset by `bevel` on the cap
    faces and bulges out to the full outline at the sides). Holes are not supported.
    Returns (vertices, faces); the front cap faces -z (toward a camera on -z)."""
    p = np.asarray(polygon_2d, float)
    if np.allclose(p[0], p[-1]):
        p = p[:-1]
    if _poly_area(p) < 0:
        p = p[::-1]
    tris = _ear_clip(p)
    n = len(p)
    hz = depth / 2
    bevel = min(bevel, hz)
    rings = []          # (2-D outline, z) from back cap to front cap
    if bevel > 0:
        ks = bevel_segments
        for side, zsign in ((0, 1), (1, -1)):
            seq = range(ks + 1) if side == 0 else range(ks, -1, -1)
            for k in seq:
                a = (math.pi / 2) * k / ks          # 0 = cap edge, pi/2 = full outline
                inset = bevel * (1 - math.sin(a))
                z = zsign * (hz - bevel + bevel * math.cos(a))
                rings.append((_offset_polygon(p, -inset), z))
    else:
        rings = [(p, hz), (p, -hz)]
    verts = []
    for ring, z in rings:
        verts += [(x, y, z) for x, y in ring]
    faces = []
    nr = len(rings)
    for r in range(nr - 1):
        for i in range(n):
            a, b = r * n + i, r * n + (i + 1) % n
            c, d = (r + 1) * n + (i + 1) % n, (r + 1) * n + i
            faces += [(a, c, b), (a, d, c)]
    back = 0
    front = (nr - 1) * n
    for (i, j, k) in tris:
        faces.append((back + i, back + j, back + k))     # z = +hz cap, CCW seen from +z
        faces.append((front + i, front + k, front + j))  # z = -hz cap, faces -z
    v = np.array(verts, float)
    f = np.array(faces, np.int64)
    return weld(v, f, tol=1e-9 * max(1.0, np.abs(v).max()))


def rounded_rect_outline(w, h, r, segments=8):
    """CCW outline of a w x h rectangle (centred) with corner radius r."""
    r = min(r, w / 2, h / 2)
    pts = []
    for cx, cy, a0 in ((w / 2 - r, h / 2 - r, 0), (-w / 2 + r, h / 2 - r, 90),
                       (-w / 2 + r, -h / 2 + r, 180), (w / 2 - r, -h / 2 + r, 270)):
        for k in range(segments + 1):
            a = math.radians(a0 + 90 * k / segments)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    p = np.array(pts)
    keep = np.r_[True, np.linalg.norm(np.diff(p, axis=0), axis=1) > 1e-12]
    p = p[keep]
    if np.linalg.norm(p[0] - p[-1]) < 1e-12:
        p = p[:-1]
    return p


def star_outline(n=5, r_out=1.0, r_in=0.45):
    pts = []
    for k in range(2 * n):
        a = math.pi / 2 + math.pi * k / n
        r = r_out if k % 2 == 0 else r_in
        pts.append((r * math.cos(a), r * math.sin(a)))
    return np.array(pts)
