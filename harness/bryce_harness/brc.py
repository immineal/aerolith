"""Read and write MetaTools Bryce 2 scene files (.BRC). See docs/brc-format.md.

Three layers:

1. `CompositeFile`: the "CCmF / Axiom AGP Composite File" container. A slot directory of
   numbered byte strings ("slots"); every slot is stored as a chain of blocks
   (12-byte big-endian header: allocated size incl. header, used size, offset of the next block).
2. `Scene`: Bryce's object store on top of the slots. Slot 16 is the class index
   (C3dSphere, C3dBaseMaterial, ...); each class has an instance table of (object id, slot A,
   slot B). Slot A normally holds the object record, slot B is rarely used.
3. Typed records (`Primitive`, `Material`, `Camera`, `Sky`, `DocSet`, lights): field
   accessors on top of an object record, with the offsets found by differential saves.

Writing always rebuilds the whole container (slots renumbered, blocks contiguous), so objects
can be added and removed freely. Records are templated from a Bryce-saved scene (templates/).
"""
from __future__ import annotations

import copy
import math
import struct
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
TEMPLATES = HERE / "brc_templates"

MAGIC = (b"CCmF - Universal - Axiom - AGP - Composite File Management System (Universal) - "
         b"Created by Andrea Pessino, December 1995 (vers. 5) - Copyright(c) 1995-96 by MetaTools, Inc. "
         b"- Proudly made in the USA, land of the free, home of the brave.")
SUBNAME = b"Resource Composite File"
DIR_PTR = 0x248          # (flags, directory size, directory offset)
DIR_INFO = 0x260         # (capacity in entries, used entries, grow-by)
DIR_OFF = 0x290
USED = 0x01000000        # directory flag of an allocated slot

UNIT = 10.24             # Bryce "B" units per internal unit (positions); sizes are 2*scale*UNIT


# =========================================================================== container

def _chain(d: bytes, size: int, off: int) -> bytes:
    out = bytearray()
    while off:
        _alloc, used, nxt = struct.unpack_from(">III", d, off)
        out += d[off + 12:off + 12 + used]
        off = nxt
    if len(out) != size:
        raise ValueError(f"slot chain length {len(out)} != {size}")
    return bytes(out)


class CompositeFile:
    """slots: {index: bytes}; an allocated empty slot is b''. Missing index = free entry."""

    def __init__(self, slots: dict[int, bytes] | None = None):
        self.slots: dict[int, bytes] = dict(slots or {})

    @classmethod
    def read(cls, path) -> "CompositeFile":
        d = Path(path).read_bytes()
        if not d.startswith(b"CCmF"):
            raise ValueError("not a CCmF composite file")
        _f, dsz, doff = struct.unpack_from(">III", d, DIR_PTR)
        dr = _chain(d, dsz, doff)
        slots = {}
        for i in range(dsz // 12):
            f, s, off = struct.unpack_from(">III", dr, 12 * i)
            if s:
                slots[i] = _chain(d, s, off)
            elif f:
                slots[i] = b""
        return cls(slots)

    def to_bytes(self) -> bytes:
        n_used = max(self.slots) + 1 if self.slots else 0
        cap = max(0x80, -(-n_used // 0x80) * 0x80)
        dsz = cap * 12
        head = bytearray(DIR_OFF)
        head[:len(MAGIC)] = MAGIC
        head[0x200:0x200 + len(SUBNAME)] = SUBNAME
        struct.pack_into(">III", head, DIR_PTR, USED, dsz, DIR_OFF)
        struct.pack_into(">III", head, DIR_PTR + 12, USED, 0, 0)
        struct.pack_into(">III", head, DIR_INFO, cap, n_used, 0x80)
        directory = bytearray(dsz)
        body = bytearray()
        pos = DIR_OFF + 12 + dsz
        for i in range(n_used):
            if i not in self.slots:
                continue
            data = self.slots[i]
            if not data:
                struct.pack_into(">III", directory, 12 * i, USED, 0, 0)
                continue
            struct.pack_into(">III", directory, 12 * i, USED, len(data), pos)
            body += struct.pack(">III", len(data) + 12, len(data), 0) + data
            pos += 12 + len(data)
        return bytes(head) + struct.pack(">III", dsz + 12, dsz, 0) + bytes(directory) + bytes(body)

    def write(self, path):
        Path(path).write_bytes(self.to_bytes())


def _array_header(item: int, count: int, grow: int) -> bytes:
    cap = max(grow, -(-count // grow) * grow)
    return struct.pack(">8I", item, cap, grow, count, 0, 0, 0, 0)


# =========================================================================== object store

@dataclass
class Obj:
    cls: str            # C++ class name, e.g. "C3dSphere"
    oid: int            # object id; references between objects use it
    a: bytes = b""      # main record
    b: bytes = b""      # secondary record (C3dCImage info, brycedocset data)
    tail: bytes = bytes(48)   # rest of the 60-byte table row (looks like uninitialised memory)

    @property
    def tag(self) -> bytes:
        return self.a[0x80:0x88] if len(self.a) > 0x88 else b""

    @property
    def name(self) -> str:
        return self.a[:0x80].split(b"\0")[0].decode("latin-1") if len(self.a) >= 0x80 else ""


ROW = 60
CLASS_ROW = 32


class Scene:
    """Ordered classes -> instances. `objs` keeps Bryce's class order (class index order)
    and instance order within a class."""

    def __init__(self, objs: list[Obj] | None = None):
        self.objs: list[Obj] = list(objs or [])

    # ------------------------------------------------------------- io
    @classmethod
    def read(cls, path) -> "Scene":
        return cls.from_composite(CompositeFile.read(path))

    @classmethod
    def from_composite(cls, cf: CompositeFile) -> "Scene":
        s = cf.slots
        index, hdr = s[16], s[17]
        n_cls = struct.unpack_from(">I", hdr, 12)[0]
        objs = []
        for k in range(n_cls):
            row = index[CLASS_ROW * k:CLASS_ROW * (k + 1)]
            name = row[:16].split(b"\0")[0].decode("latin-1")
            tab, th = struct.unpack_from(">II", row, 16)
            n = struct.unpack_from(">I", s[th], 12)[0]
            for j in range(n):
                r = s[tab][ROW * j:ROW * (j + 1)]
                oid, sa, sb = struct.unpack_from(">III", r)
                objs.append(Obj(name, oid, s.get(sa, b""), s.get(sb, b""), bytes(r[12:])))
        return cls(objs)

    def to_composite(self) -> CompositeFile:
        slots: dict[int, bytes] = {i: b"" for i in range(16)}
        classes: list[str] = []
        for o in self.objs:
            if o.cls not in classes:
                classes.append(o.cls)
        nxt = 18
        index = bytearray()
        for c in classes:
            inst = [o for o in self.objs if o.cls == c]
            tab, th = nxt, nxt + 1
            nxt += 2
            rows = bytearray()
            for o in inst:
                sa, sb = nxt, nxt + 1
                nxt += 2
                slots[sa], slots[sb] = o.a, o.b
                rows += struct.pack(">III", o.oid, sa, sb) + o.tail[:48].ljust(48, b"\0")
            hdr = _array_header(ROW, len(inst), 0x20)
            cap = struct.unpack_from(">I", hdr, 4)[0]
            slots[tab] = bytes(rows.ljust(ROW * cap, b"\0"))
            slots[th] = hdr
            index += c.encode()[:15].ljust(16, b"\0") + struct.pack(">IIII", tab, th, 0, 0)
        ihdr = _array_header(CLASS_ROW, len(classes), 0x10)
        cap = struct.unpack_from(">I", ihdr, 4)[0]
        slots[16] = bytes(index.ljust(CLASS_ROW * cap, b"\0"))
        slots[17] = ihdr
        return CompositeFile(slots)

    def write(self, path):
        self.to_composite().write(path)

    # ------------------------------------------------------------- queries
    def by_class(self, cls: str) -> list[Obj]:
        return [o for o in self.objs if o.cls == cls]

    def get(self, oid: int, cls: str | None = None) -> Obj:
        for o in self.objs:
            if o.oid == oid and (cls is None or o.cls == cls):
                return o
        raise KeyError(oid)

    def new_oid(self) -> int:
        return max(o.oid for o in self.objs) + 1

    def insert(self, obj: Obj):
        """Add after the last object of the same class (or at the end)."""
        idx = [i for i, o in enumerate(self.objs) if o.cls == obj.cls]
        self.objs.insert(idx[-1] + 1 if idx else len(self.objs), obj)

    def remove(self, oid: int, cls: str | None = None):
        self.objs.remove(self.get(oid, cls))

    def summary(self) -> str:
        lines = []
        for o in self.objs:
            lines.append(f"{o.cls:16s} id={o.oid:<4d} {o.tag.decode('latin-1', 'replace'):8s} "
                         f"{len(o.a):6d}B {o.name!r}")
        return "\n".join(lines)


# =========================================================================== typed records
# Object records (slot A) start with a 128-byte name, then an 8-char tag at 0x80.
# Primitives, lights and cameras share a little-endian transform block (raw x86 doubles):

T_SCALE = 0x1bc      # 3 x f64 LE, internal units (Bryce "Size" = 2 * scale * UNIT)
T_ROT = 0x1ec        # 3 x f64 LE, radians; applied X, then Y, then Z
T_POS = 0x204        # 3 x f64 LE, internal units (Bryce "Offset" = pos * UNIT)
T_MATRIX = 0x27c     # 3x3 f64 LE row-major = S @ R.T (cached; Bryce recomputes it from the above)
T_TRANS = 0x2c4      # 3 x f64 LE, copy of T_POS (cached)


def _rot(rx, ry, rz):
    def Rx(a): c, s = math.cos(a), math.sin(a); return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])
    def Ry(a): c, s = math.cos(a), math.sin(a); return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
    def Rz(a): c, s = math.cos(a), math.sin(a); return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
    return Rz(rz) @ Ry(ry) @ Rx(rx)


def get_transform(rec: bytes):
    """-> (offset_B, rotate_deg, size_B) exactly as Bryce's Object Attributes dialog shows them."""
    sc = struct.unpack_from("<3d", rec, T_SCALE)
    rot = struct.unpack_from("<3d", rec, T_ROT)
    pos = struct.unpack_from("<3d", rec, T_POS)
    return (tuple(p * UNIT for p in pos), tuple(math.degrees(r) for r in rot),
            tuple(2 * s * UNIT for s in sc))


def set_transform(rec: bytes, offset=None, rotate=None, size=None) -> bytes:
    """Set transform in Bryce dialog units: offset in B, rotate in degrees, size in B
    (a default primitive is 20.48 B). Unspecified parts keep their values. Also refreshes
    the cached matrix so the record stays self-consistent."""
    a = bytearray(rec)
    o, r, s = get_transform(rec)
    o = offset if offset is not None else o
    r = rotate if rotate is not None else r
    s = size if size is not None else s
    sc = [v / (2 * UNIT) for v in s]
    rad = [math.radians(v) for v in r]
    pos = [v / UNIT for v in o]
    struct.pack_into("<3d", a, T_SCALE, *sc)
    struct.pack_into("<3d", a, T_ROT, *rad)
    struct.pack_into("<3d", a, T_POS, *pos)
    m = np.diag(sc) @ _rot(*rad).T
    struct.pack_into("<9d", a, T_MATRIX, *m.ravel())
    struct.pack_into("<3d", a, T_TRANS, *pos)
    return bytes(a)


# --------------------------------------------------------------------------- materials
# C3dBaseMaterial record (568 B), big-endian; verified by differential saves in the
# Materials Composer (values in the dialog are 0..255, stored as 0..1).
M_DIFFUSE_RGB = 0xd4      # 3 x f32
M_DIFFUSION = 0xe0        # f64
M_AMBIENT_RGB = 0xe8      # 3 x f32
M_AMBIENCE = 0xf4         # f64
M_SPECULAR_RGB = 0xfc     # 3 x f32
M_SPECULARITY = 0x108     # f64
M_SPEC_COEF = 0x110       # 3 x f32 (default 50.0; dialog shows 205 - not verified)
M_TRANSP_RGB = 0x11c      # 3 x f32
M_TRANSPARENCY = 0x128    # f64
M_REFLECTION = 0x130      # f64
M_BUMP = 0x138            # f64 LITTLE-endian (verified by brc_material agent)
M_REFRACTION = 0x140      # f64, dialog "Refraction Index" 100 = 1.0
OBJ_MATERIAL_REF = 0x94   # u32 BE in primitive records ("base" + material object id)

_MAT_FIELDS = {
    "diffuse": (M_DIFFUSE_RGB, "rgb"), "diffusion": (M_DIFFUSION, "d"),
    "ambient": (M_AMBIENT_RGB, "rgb"), "ambience": (M_AMBIENCE, "d"),
    "specular": (M_SPECULAR_RGB, "rgb"), "specularity": (M_SPECULARITY, "d"),
    "spec_coef": (M_SPEC_COEF, "rgb"),
    "transparent": (M_TRANSP_RGB, "rgb"), "transparency": (M_TRANSPARENCY, "d"),
    "reflection": (M_REFLECTION, "d"), "bump": (M_BUMP, "dle"), "refraction": (M_REFRACTION, "d"),
}


def get_material(rec: bytes) -> dict:
    out = {}
    for k, (off, kind) in _MAT_FIELDS.items():
        out[k] = (struct.unpack_from(">3f", rec, off) if kind == "rgb" else
                  struct.unpack_from("<d" if kind == "dle" else ">d", rec, off)[0])
    return out


def _rgb(v) -> tuple[float, float, float]:
    if isinstance(v, str):
        return tuple(int(v.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return tuple(float(x) for x in v)


def set_material(rec: bytes, **kw) -> bytes:
    """Colours as (r, g, b) in 0..1 or '#rrggbb'; scalars in 0..1 (refraction: 1.0 = index 100).
    e.g. set_material(m, diffuse='#3aa0ff', specularity=0.9, reflection=0.3, transparency=0.6,
    refraction=1.33)"""
    a = bytearray(rec)
    for k, v in kw.items():
        off, kind = _MAT_FIELDS[k]
        if kind == "rgb":
            struct.pack_into(">3f", a, off, *_rgb(v))
        else:
            struct.pack_into("<d" if kind == "dle" else ">d", a, off, float(v))
    return bytes(a)


def material_of(scene: "Scene", obj: Obj) -> Obj:
    mid = struct.unpack_from(">I", obj.a, OBJ_MATERIAL_REF)[0]
    return scene.get(mid, "C3dBaseMaterial")


# --------------------------------------------------------------------------- camera
CAM_FORWARD = 0x2ec       # 3 x f64 BE, unit view direction (Bryce aims the camera with this)
CAM_UP = 0x304            # 3 x f64 BE, unit up vector
CAM_FOV = 0x33c           # f64 BE, radians (default 60 deg) - unverified


def set_camera(rec: bytes, position_b, look_at_b=None, forward=None, up=(0.0, 1.0, 0.0),
               fov_deg: float | None = None) -> bytes:
    """Position in Bryce units (B). Aim with look_at_b (a point) or forward (a vector).
    Updates both the transform block (position, yaw/pitch) and the BE aim vectors."""
    p = np.array(position_b, float)
    f = np.array(forward if forward is not None else np.array(look_at_b, float) - p, float)
    f /= np.linalg.norm(f)
    yaw = math.atan2(f[0], f[2])
    pitch = -math.asin(max(-1.0, min(1.0, f[1])))
    rec = set_transform(rec, offset=tuple(p), rotate=(math.degrees(pitch), math.degrees(yaw), 0.0))
    u = np.array(up, float)
    u = u - f * np.dot(u, f)
    u /= np.linalg.norm(u)
    a = bytearray(rec)
    struct.pack_into(">3d", a, CAM_FORWARD, *f)
    struct.pack_into(">3d", a, CAM_UP, *u)
    if fov_deg is not None:
        struct.pack_into(">d", a, CAM_FOV, math.radians(fov_deg))
    return bytes(a)


# --------------------------------------------------------------------------- sun
SUN_COLOR = 0x2ec         # 3 x f32 BE (1,1,1 default) - unverified
SUN_DIR = 0x328           # 3 x f64 BE, unit vector pointing TOWARD the sun (verified via shadow direction)


def set_sun(rec: bytes, toward=None, color=None) -> bytes:
    a = bytearray(rec)
    if toward is not None:
        v = np.array(toward, float)
        struct.pack_into(">3d", a, SUN_DIR, *(v / np.linalg.norm(v)))
    if color is not None:
        struct.pack_into(">3f", a, SUN_COLOR, *_rgb(color))
    return bytes(a)


# --------------------------------------------------------------------------- sky
SKY_HAZE = 0x144          # f64 BE, default 0.4; 0 = no haze (backdrops render exactly their colour)
SKY_UNKNOWN_8C = 0x8c     # f64 BE, default 9.77; 0 removes a faint tint near the top of the frame


def set_sky(rec: bytes, haze=None) -> bytes:
    a = bytearray(rec)
    if haze is not None:
        struct.pack_into(">d", a, SKY_HAZE, float(haze))
    return bytes(a)


# --------------------------------------------------------------------------- builder
PRIMITIVES = {"sphere": "C3dSphere", "cube": "C3dCube", "cylinder": "C3dCylinder", "cone": "C3dCone",
              "torus": "C3dTorusType", "pyramid": "C3dPyramid", "square": "C3dSquare", "disk": "C3dCircle"}


# The transform's scale means different things per class (object space differs). Measured on a
# calibrated sheet (1 B = 6 px): requesting Size 40 gave sphere/cylinder/cone/square/disk 40,
# cube and pyramid 20, torus ~80 (outer diameter). SceneBuilder.add multiplies by these factors
# so that `size` is always the rendered extent in B.
SIZE_FACTOR = {"C3dCube": 2.0, "C3dPyramid": 2.0, "C3dTorusType": 0.5}


def _tpl(cls: str) -> tuple[bytes, bytes]:
    return (TEMPLATES / f"{cls}.a").read_bytes(), (TEMPLATES / f"{cls}.tail").read_bytes()


class SceneBuilder:
    """Build a scene from the base template (default sky + sun, perspective camera, no ground).

        sb = SceneBuilder()
        sb.camera((0, 10.24, -60), look_at=(0, 10.24, 0))
        sb.add("sphere", offset=(0, 10.24, 0), size=(20.48,)*3,
               material=dict(diffuse="#2a7fff", specularity=0.9, reflection=0.25))
        sb.write("work/x.brc")

    Units are Bryce's dialog units (B): a default primitive is 20.48 B across.
    Squares/disks are flat in the XZ plane (rotate x=-90 to face the camera on -Z).
    """

    def __init__(self, base=TEMPLATES / "base_scene.brc"):
        self.scene = Scene.read(base)
        for o in list(self.scene.objs):           # drop the template's sphere and its material
            if o.cls in PRIMITIVES.values() or o.cls == "C3dPlane":
                mat = material_of(self.scene, o)
                self.scene.remove(o.oid, o.cls)
                self.scene.remove(mat.oid, "C3dBaseMaterial")

    def camera(self, position, look_at=None, forward=None, fov=None, name="perspective"):
        cam = next(o for o in self.scene.by_class("C3dBaseCamera") if o.name == name)
        cam.a = set_camera(cam.a, position, look_at, forward, fov_deg=fov)
        return cam

    def sky(self, haze=None):
        o = self.scene.by_class("C3dBaseSky")[0]
        o.a = set_sky(o.a, haze)
        return o

    def sun(self, toward=None, color=None):
        o = self.scene.by_class("C3dSunLight")[0]
        o.a = set_sun(o.a, toward, color)
        return o

    def material(self, **kw) -> Obj:
        a, tail = _tpl("C3dBaseMaterial")
        m = Obj("C3dBaseMaterial", self.scene.new_oid(), set_material(a, **kw), b"", tail)
        self.scene.insert(m)
        return m

    def add(self, kind: str, offset=(0, 0, 0), rotate=(0, 0, 0), size=(20.48, 20.48, 20.48),
            material: dict | Obj | None = None) -> Obj:
        cls = PRIMITIVES.get(kind, kind)
        a, tail = _tpl(cls)
        mat = material if isinstance(material, Obj) else self.material(**(material or {}))
        f = SIZE_FACTOR.get(cls, 1.0)
        a = bytearray(set_transform(a, offset=tuple(offset), rotate=tuple(rotate),
                                    size=tuple(v * f for v in size)))
        struct.pack_into(">I", a, OBJ_MATERIAL_REF, mat.oid)
        o = Obj(cls, self.scene.new_oid(), bytes(a), b"", tail)
        self.scene.insert(o)
        return o

    def write(self, path):
        self.scene.write(path)
        return path
