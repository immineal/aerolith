"""Bryce 2 materials, textures and pictures (.BRC). See docs/brc/materials.md.

Builds on brc.py (container, object store, SceneBuilder); does not change it.

    from bryce_harness import brc, brc_material as bm
    sb = brc.SceneBuilder()
    m = bm.material(sb, diffuse="#ffffff", specularity=0.8)              # every channel settable
    tex = bm.add_texture(sb, "Marble")                                    # a 3D texture from Bryce's library
    m = bm.material(sb, textures={"A": tex}, drive={"diffuse_color": "A", "bump": "A"}, bump=0.4)
    pic = bm.add_picture(sb, "logo.png")                                  # our own RGBA image
    m = bm.material(sb, textures={"A": bm.Slot(pic, mapping="parametric")},
                    drive={"diffuse_color": "A", "ambient_color": "A", "transparency": "A"})
    m = bm.preset(sb, "Metallic Chrome")                                  # a Materials-palette preset
    sb.add("sphere", material=m)
    m = bm.sprite_material(sb, "button.png")       # PNG shown exactly (self-lit, alpha = see-through)
    sb.add("square", rotate=(-90, 0, 0), size=(40, 1, 20), material=m)

Material record: C3dBaseMaterial (568 B, big-endian except `bump`). Ten channels, each driven by
its own value (mode 0) or by texture slot A..D (mode 1..4). Four 48-byte texture slots reference
C3dTexture ('brtx', procedural) or CPictTexture ('pctx', picture) objects by object id.
"""
from __future__ import annotations

import glob
import math
import struct
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import brc
from .brc import Obj, Scene, SceneBuilder

BRYCE_DIR = brc.HERE.parent.parent / "wine" / "bryce2"
SUPPORT = BRYCE_DIR / "Bryce2 Support Files"
TEXTURE_LIB = BRYCE_DIR / "Data" / "textures.dat"

# =========================================================================== material record

TAG = 0x80                # b"matrbase"
MODES = 0x8c              # 10 x i32: channel drivers, 0 = own value, 1..4 = texture A..D
FLAGS = 0xd0              # u32: bits 0-2 shading mode + option bits FLAG_*
DIFFUSE_RGB = 0xd4        # 3 x f32 (0..1)
DIFFUSION = 0xe0          # f64
AMBIENT_RGB = 0xe8
AMBIENCE = 0xf4
SPECULAR_RGB = 0xfc
SPECULARITY = 0x108
SPEC_COEF = 0x110         # 3 x f32 = 255 - dialog "Specular Coefficients" (dialog 205 -> 50.0)
TRANSP_RGB = 0x11c
TRANSPARENCY = 0x128
REFLECTION = 0x130
BUMP = 0x138              # f64 LITTLE-endian (dialog "Bump Height" / 255); brc.py writes it big-endian
REFRACTION = 0x140        # f64, dialog "Refraction Index" / 100
METALLICITY = 0x150       # f64 (dialog "Metallicity" / 100?)
SLOTS = 0x178             # 4 x 48-byte texture slots A..D
SLOT_SIZE = 48

# channel order = order of the mode words = order of the value fields
CHANNELS = ("diffuse_color", "diffusion", "ambient_color", "ambience", "specular_color", "specularity",
            "transparent_color", "transparency", "reflection", "bump")
SLOT_NAMES = "ABCD"

SHADING = {"normal": 0, "additive": 1, "fuzzy": 2, "fuzzy_additive": 3, "light": 4, "blend": 5}
FLAG_DISTANCE_FILTER = 0x08   # composer menu "Distance Filter": changes how the transparent colour filters (V: render)
FLAG_SHADOWABLE = 0x10        # composer menu "Shadowable" (name by menu order; no visible effect found)
FLAG_TEXTURED = 0x40          # set by the composer whenever a texture slot is filled

# mapping modes, in the order of the Materials Composer's per-texture menu
MAPPING = ("object", "world", "parametric", "parametric_scaled", "world_top", "spherical", "cylindrical",
           "reflection_map", "random", "object_top", "object_front")

_SCALARS = {"diffusion": DIFFUSION, "ambience": AMBIENCE, "specularity": SPECULARITY,
            "transparency": TRANSPARENCY, "reflection": REFLECTION, "refraction": REFRACTION,
            "metallicity": METALLICITY}
_COLOURS = {"diffuse": DIFFUSE_RGB, "ambient": AMBIENT_RGB, "specular": SPECULAR_RGB,
            "transparent": TRANSP_RGB}


def _rgb(v):
    return brc._rgb(v)


@dataclass
class Slot:
    """One texture slot (A..D) of a material.
    obj: a C3dTexture or CPictTexture Obj (or an object id + kind).
    frequency: the composer's per-slot frequency (default 0.505 = slider middle).
    mapping: name from MAPPING or its index. tiling: 'Symmetric tiling'."""
    obj: Obj | int | None
    frequency: float = 0.505
    mapping: str | int = "world"
    tiling: bool = False
    kind: str | None = None          # 'brtx' / 'pctx'; taken from obj when it is an Obj

    def pack(self) -> bytes:
        if self.obj is None:
            return struct.pack(">4sId", b"\0" * 4, 0, 0.5) + bytes(24) + struct.pack(">ii", 1, 0)
        if isinstance(self.obj, Obj):
            oid = self.obj.oid
            kind = "pctx" if self.obj.cls == "CPictTexture" else "brtx"
        else:
            oid, kind = int(self.obj), self.kind or "brtx"
        m = MAPPING.index(self.mapping) if isinstance(self.mapping, str) else int(self.mapping)
        return struct.pack(">4sId", kind.encode(), oid, float(self.frequency)) + bytes(24) + \
            struct.pack(">ii", m, int(bool(self.tiling)))


def get_slot(rec: bytes, k: int) -> dict:
    off = SLOTS + SLOT_SIZE * k
    kind, oid, freq = struct.unpack_from(">4sId", rec, off)
    mapping, tiling = struct.unpack_from(">ii", rec, off + 40)
    return {"kind": kind.decode("latin-1").strip("\0") or None, "oid": oid, "frequency": freq,
            "mapping": MAPPING[mapping] if 0 <= mapping < len(MAPPING) else mapping, "tiling": bool(tiling)}


def get_material(rec: bytes) -> dict:
    """Everything decoded from a C3dBaseMaterial record (dialog-scale notes in the docs)."""
    out = {}
    for k, off in _COLOURS.items():
        out[k] = struct.unpack_from(">3f", rec, off)
    for k, off in _SCALARS.items():
        out[k] = struct.unpack_from(">d", rec, off)[0]
    out["bump"] = struct.unpack_from("<d", rec, BUMP)[0]
    out["spec_coef"] = struct.unpack_from(">3f", rec, SPEC_COEF)
    modes = struct.unpack_from(">10i", rec, MODES)
    out["drive"] = {c: (SLOT_NAMES[m - 1] if 1 <= m <= 4 else m) for c, m in zip(CHANNELS, modes) if m}
    fl = struct.unpack_from(">I", rec, FLAGS)[0]
    inv = {v: k for k, v in SHADING.items()}
    out["shading"] = inv.get(fl & 7, fl & 7)
    out["flags"] = fl
    out["slots"] = {SLOT_NAMES[k]: get_slot(rec, k) for k in range(4) if rec[SLOTS + 48 * k:SLOTS + 48 * k + 4] != bytes(4)}
    return out


def set_material(rec: bytes, *, drive: dict | None = None, textures: dict | None = None,
                 shading: str | int | None = None, flags: int | None = None,
                 spec_coef_dialog=None, bump=None, **kw) -> bytes:
    """Set any part of a material record.

    Colours: diffuse, ambient, specular, transparent ('#rrggbb' or 0..1 triple).
    Scalars (0..1 unless noted): diffusion, ambience, specularity, transparency, reflection,
      bump (Bump Height/255, may be negative), refraction (index/100, 1.0 = air), metallicity.
    spec_coef_dialog: the composer's "Specular Coefficients" (0..255, default 205), one value or rgb.
    spec_coef: the raw stored value (= 255 - dialog).
    drive: {channel: 'A'..'D' | 'value'} (channels in CHANNELS; 'diffuse'/'ambient'/... accepted
      as aliases of the *_color channels).
    textures: {'A': Slot | Obj | None, ...}
    shading: 'normal', 'additive', 'fuzzy', 'fuzzy_additive', 'light', 'blend' (or 0..5).
    flags: raw u32 at 0xd0 (shading bits are merged in after it)."""
    a = bytearray(rec)
    for k, v in kw.items():
        if k in _COLOURS:
            struct.pack_into(">3f", a, _COLOURS[k], *_rgb(v))
        elif k in _SCALARS:
            struct.pack_into(">d", a, _SCALARS[k], float(v))
        elif k == "spec_coef":
            v = (v,) * 3 if np.isscalar(v) else v
            struct.pack_into(">3f", a, SPEC_COEF, *map(float, v))
        else:
            raise KeyError(k)
    if bump is not None:
        struct.pack_into("<d", a, BUMP, float(bump))
    if spec_coef_dialog is not None:
        v = (spec_coef_dialog,) * 3 if np.isscalar(spec_coef_dialog) else spec_coef_dialog
        struct.pack_into(">3f", a, SPEC_COEF, *(255.0 - float(x) for x in v))
    if textures:
        for name, s in textures.items():
            k = SLOT_NAMES.index(name)
            if not isinstance(s, Slot):
                s = Slot(s)
            a[SLOTS + SLOT_SIZE * k:SLOTS + SLOT_SIZE * (k + 1)] = s.pack()
        # composer sets 0x40 whenever a texture is assigned
        if any(textures.values()):
            struct.pack_into(">I", a, FLAGS, struct.unpack_from(">I", a, FLAGS)[0] | 0x40)
    if drive:
        for ch, src in drive.items():
            ch = {"diffuse": "diffuse_color", "ambient": "ambient_color", "specular": "specular_color",
                  "transparent": "transparent_color"}.get(ch, ch)
            i = CHANNELS.index(ch)
            m = 0 if src in (None, 0, "value") else (SLOT_NAMES.index(src) + 1 if isinstance(src, str) else int(src))
            struct.pack_into(">i", a, MODES + 4 * i, m)
    if flags is not None:
        struct.pack_into(">I", a, FLAGS, flags)
    if shading is not None:
        sm = SHADING[shading] if isinstance(shading, str) else int(shading)
        fl = struct.unpack_from(">I", a, FLAGS)[0]
        struct.pack_into(">I", a, FLAGS, (fl & ~7) | sm)
    return bytes(a)


def material(sb: SceneBuilder, **kw) -> Obj:
    """New C3dBaseMaterial in the builder's scene; kw as set_material."""
    a, tail = brc._tpl("C3dBaseMaterial")
    m = Obj("C3dBaseMaterial", sb.scene.new_oid(), set_material(a, **kw), b"", tail)
    sb.scene.insert(m)
    return m


# =========================================================================== pictures (C3dCImage)
# Slot B: 80-byte header 'imge' 'iv32', u32 4 (bytes/pixel), width, rowbytes (=4*width), height,
# 8 zero bytes, Rect (top, left, bottom, right) = (0, 0, height, width) at 0x20, rest zero.
# Slot A: 'arle' + 60 zero bytes, then 4 planes A, R, G, B (each height x width, top row first),
# each run-length coded on its own: byte n < 0x80 -> n copies of the next byte; n >= 0x80 ->
# n - 0x80 literal bytes. Bryce never crosses a plane boundary, runs <= 126, literals <= 125.

def arle_decode(data: bytes, w: int, h: int) -> np.ndarray:
    """-> uint8 array (4, h, w): planes alpha, red, green, blue."""
    d = data[64:]
    out = bytearray()
    i = 0
    n_d = len(d)
    while i < n_d:
        b = d[i]
        i += 1
        if b >= 0x80:
            n = b - 0x80
            out += d[i:i + n]
            i += n
        else:
            out += bytes((d[i],)) * b
            i += 1
    return np.frombuffer(bytes(out[:4 * w * h]), np.uint8).reshape(4, h, w)


def _arle_plane(p: bytes) -> bytes:
    out = bytearray()
    lit = bytearray()
    n = len(p)
    i = 0

    def flush():
        nonlocal lit
        while lit:
            chunk = lit[:125]
            out.append(0x80 + len(chunk))
            out.extend(chunk)
            lit = lit[125:]

    while i < n:
        j = i
        while j < n and j - i < 126 and p[j] == p[i]:
            j += 1
        if j - i >= 3:
            flush()
            out.append(j - i)
            out.append(p[i])
            i = j
        else:
            lit.append(p[i])
            i += 1
            if len(lit) == 125:
                flush()
    flush()
    return bytes(out)


def arle_encode(planes: np.ndarray) -> bytes:
    """planes: uint8 (4, h, w) alpha, red, green, blue."""
    out = bytearray(b"arle" + bytes(60))
    for p in np.asarray(planes, np.uint8):
        out += _arle_plane(p.tobytes())
    return bytes(out)


def image_header(w: int, h: int) -> bytes:
    b = bytearray(80)
    b[0:8] = b"imgeiv32"
    struct.pack_into(">IIII", b, 8, 4, w, 4 * w, h)
    struct.pack_into(">IIII", b, 0x20, 0, 0, h, w)
    return bytes(b)


def decode_image(obj: Obj) -> np.ndarray:
    """C3dCImage / matprevcimage / ImageIV32ARGB object -> RGBA uint8 (h, w, 4)."""
    _bpp, w, _rb, h = struct.unpack_from(">IIII", obj.b, 8)
    p = arle_decode(obj.a, w, h)
    return np.dstack([p[1], p[2], p[3], p[0]])


def encode_image(rgba) -> tuple[bytes, bytes]:
    """RGBA (h, w, 4) uint8 array or PIL image -> (slot A, slot B) of a C3dCImage."""
    from PIL import Image
    if isinstance(rgba, Image.Image):
        rgba = np.asarray(rgba.convert("RGBA"))
    rgba = np.asarray(rgba, np.uint8)
    h, w = rgba.shape[:2]
    planes = np.stack([rgba[..., 3], rgba[..., 0], rgba[..., 1], rgba[..., 2]])
    return arle_encode(planes), image_header(w, h)


def add_picture(sb: SceneBuilder, image, name: str = "picture", size: int | None = None,
                alpha=None, premultiply: bool = True) -> Obj:
    """Add a picture texture (CPictTexture + its C3dCImage, same object id) from a PNG path,
    PIL image or RGBA array. `alpha` (optional path/array) replaces the alpha plane
    (255 = opaque). size: resample to size x size (Bryce's own pictures are <= 512 px).
    premultiply: store RGB * alpha. Bryce adds the (ambient/diffuse) colour on top of what shows
    through a transparent pixel, so straight alpha leaks colour into transparent areas;
    premultiplied RGB + transparency driven by the picture gives exact "over" compositing
    (V: alpha ramp within 1-3 levels). Returns the CPictTexture Obj, which goes into a slot."""
    from PIL import Image
    im = Image.open(image) if isinstance(image, (str, Path)) else image
    if not isinstance(im, Image.Image):
        im = Image.fromarray(np.asarray(im, np.uint8))
    im = im.convert("RGBA")
    if size:
        im = im.resize((size, size), Image.LANCZOS)
    rgba = np.array(im)
    if alpha is not None:
        am = Image.open(alpha) if isinstance(alpha, (str, Path)) else Image.fromarray(np.asarray(alpha, np.uint8))
        rgba[..., 3] = np.asarray(am.convert("L").resize(im.size))
    if premultiply:
        rgba[..., :3] = (rgba[..., :3].astype(np.uint16) * rgba[..., 3:4] + 127) // 255
    a, b = encode_image(rgba)
    oid = sb.scene.new_oid()
    rec = bytearray(136)
    nm = name.encode("latin-1")[:127]
    rec[:len(nm)] = nm
    rec[0x80:0x88] = b"txtrpctx"
    pt = Obj("CPictTexture", oid, bytes(rec), b"", bytes(48))
    img = Obj("C3dCImage", oid, a, b, bytes(48))
    sb.scene.insert(img)
    sb.scene.insert(pt)
    return pt


def sprite_material(sb: SceneBuilder, picture, *, lit: bool = False, repeats: int = 1, mapping="parametric",
                    tiling: bool = False, alpha: bool = True, **kw) -> Obj:
    """Material that shows a picture exactly (V): the colour drives diffuse + ambient colour,
    alpha drives transparency, parametric mapping shows the whole image once per face, stretched
    to the face, upright for a square rotated x=-90 and seen from -Z (V).
    picture: CPictTexture Obj or anything add_picture accepts. lit=False: self-lit, unshaded
    (diffusion 0, ambience 1 -> rendered RGB = picture RGB); lit=True: diffusion 1, ambience 0.4.
    repeats: tiles per face, parametric frequency = (repeats - 1) / 20 (V for 1..21).
    kw: further set_material fields (e.g. specularity, reflection)."""
    if not isinstance(picture, Obj):
        picture = add_picture(sb, picture)
    drive = {"diffuse_color": "A", "ambient_color": "A"}
    if alpha:
        drive["transparency"] = "A"
    vals = dict(diffusion=1.0, ambience=0.4) if lit else dict(diffusion=0.0, ambience=1.0)
    vals.update(diffuse="#ffffff", ambient="#ffffff", specularity=0.0)
    vals.update(kw)
    return material(sb, textures={"A": Slot(picture, frequency=frequency_for_repeats(repeats), mapping=mapping,
                                            tiling=tiling)}, drive=drive, **vals)


def frequency_for_repeats(n: int) -> float:
    """Slot frequency for n picture repeats per face with parametric mapping: Bryce draws
    1 + round(20 * f) whole tiles (V: f = 0, .01, .02 -> 1; .05 -> 2; .1 -> 3; .2 -> 5; .3 -> 7;
    .4 -> 9; .5 -> 11; .6 -> 13; .8 -> 17; 1.0 -> 21)."""
    return max(0.0, (int(n) - 1) / 20.0)


# =========================================================================== 3D textures (C3dTexture)

_texlib: Scene | None = None


def texture_library() -> Scene:
    """Bryce's 3D texture library (Data/textures.dat): 105 named C3dTexture records."""
    global _texlib
    if _texlib is None:
        _texlib = Scene.read(TEXTURE_LIB)
    return _texlib


def texture_names() -> list[str]:
    return [o.name for o in texture_library().by_class("C3dTexture")]


# C3dTexture record (1216 B, big-endian). What is verified by render (Marble, differential):
#   0x88  i32  number of components combined (1..3); 1 -> only component 0 shows (V)
#   0xd8 + 0x110*k  component k (k = 0..2), 272 bytes:
#     +0x00 i32 type 1..7 (?; 6 -> 1 changed the look, 6 -> 2/3/7 did not)
#     +0x0c, +0x10 i32 angles in degrees (P)
#     +0x14 3 x i32 frequency multipliers x,y,z: larger = finer pattern (V)
#     +0x30 3 x i32 second triple (V: changes the pattern)
#     +0x44 f32 (V: small change)
#     +0x54 3 x u32 colours 0x00RRGGBB (V for components 0 and 1 of Marble)
#     +0x60 / +0xb8 9 x f64 cached matrices: ignored on load (V: x4 had no effect)
#   0x42c 9 x f64 cached global matrix: ignored (V); 0xa8 3 x i32 global scale: no effect seen (?)
TEX_NCOMP = 0x88
TEX_COMP = 0xd8
TEX_COMP_SIZE = 0x110


def set_texture(rec: bytes, *, colours: dict | None = None, scale: dict | None = None,
                scale2: dict | None = None, components: int | None = None, name: str | None = None) -> bytes:
    """Edit a C3dTexture record.
    colours: {k: (c0, c1, c2)} per component k (0..2), each '#rrggbb' or 0..1 triple.
    scale: {k: (x, y, z)} component frequency multipliers (ints, larger = finer), or a float
      factor applied to the current values. scale2: the same for the +0x30 triple.
    components: how many components are combined (1..3)."""
    a = bytearray(rec)
    if name is not None:
        a[:0x80] = name.encode("latin-1")[:127].ljust(0x80, b"\0")
    for k, cs in (colours or {}).items():
        for i, c in enumerate(cs):
            r, g, b = (int(round(255 * x)) for x in _rgb(c))
            struct.pack_into(">I", a, TEX_COMP + TEX_COMP_SIZE * k + 0x54 + 4 * i, (r << 16) | (g << 8) | b)
    for off, d in ((0x14, scale), (0x30, scale2)):
        for k, v in (d or {}).items():
            o = TEX_COMP + TEX_COMP_SIZE * k + off
            cur = struct.unpack_from(">3i", a, o)
            v = [max(1, int(round(c * v))) for c in cur] if np.isscalar(v) else [int(x) for x in v]
            struct.pack_into(">3i", a, o, *v)
    if components is not None:
        struct.pack_into(">i", a, TEX_NCOMP, int(components))
    return bytes(a)


def get_texture(rec: bytes) -> dict:
    out = {"name": rec[:0x80].split(b"\0")[0].decode("latin-1"),
           "components": struct.unpack_from(">i", rec, TEX_NCOMP)[0], "comp": []}
    for k in range(3):
        o = TEX_COMP + TEX_COMP_SIZE * k
        out["comp"].append({"type": struct.unpack_from(">i", rec, o)[0],
                            "angles": struct.unpack_from(">2i", rec, o + 0x0c),
                            "scale": struct.unpack_from(">3i", rec, o + 0x14),
                            "scale2": struct.unpack_from(">3i", rec, o + 0x30),
                            "colours": ["#%06x" % (x & 0xffffff) for x in struct.unpack_from(">3I", rec, o + 0x54)]})
    return out


def add_texture(sb: SceneBuilder, src: str | Obj | bytes, name: str | None = None, **params) -> Obj:
    """Copy a 3D texture into the scene: a library name ('Marble', see texture_names()), an Obj
    or a raw 1216-byte record. params: see set_texture (colours, scale, scale2, components)."""
    if isinstance(src, str):
        cands = [o for o in texture_library().by_class("C3dTexture") if o.name == src]
        if not cands:
            raise KeyError(f"no 3D texture {src!r} in textures.dat")
        rec, tail = cands[0].a, cands[0].tail
    elif isinstance(src, Obj):
        rec, tail = src.a, src.tail
    else:
        rec, tail = bytes(src), bytes(48)
    rec = set_texture(rec, name=name, **params)
    t = Obj("C3dTexture", sb.scene.new_oid(), rec, b"", tail)
    sb.scene.insert(t)
    return t


# =========================================================================== presets & transplant

@dataclass
class Preset:
    library: str            # file stem, e.g. "simple4" / "Waters&Liquids"
    name: str
    description: str
    scene: Scene            # the library file's object store
    material: Obj

    def preview(self) -> np.ndarray | None:
        p = [o for o in self.scene.by_class("matprevcimage") if o.oid == self.material.oid]
        return decode_image(p[0]) if p else None


_presets: list[Preset] | None = None


def _descr(o: Obj) -> tuple[str, str]:
    # name: NUL-terminated, space padded, in the first 0x40 bytes; description text from 0x40
    name = o.a[:0x40].split(b"\0")[0].decode("latin-1").strip()
    descr = o.a[0x40:].split(b"\0")[0].decode("latin-1").strip()
    return name, descr


def presets(reload: bool = False) -> list[Preset]:
    """All material presets of the Materials palette libraries (Bryce2 Support Files/*.shd in the
    CCmF format; Basics/Simple&Fast/User.shd use the old Bryce 1 stream and are skipped -
    simple4.shd is the converted Simple&Fast). One per material, named by its CPresetDescr."""
    global _presets
    if _presets is not None and not reload:
        return _presets
    out = []
    for f in sorted(glob.glob(str(SUPPORT / "*.shd"))):
        if Path(f).read_bytes()[:4] != b"CCmF":
            continue
        try:
            s = Scene.read(f)
        except ValueError:          # Simple&Fast.shd has broken block chains (simple4.shd is its clean copy)
            continue
        d = {o.oid: _descr(o) for o in s.by_class("CPresetDescr")}
        for m in s.by_class("C3dBaseMaterial"):
            nm, ds = d.get(m.oid, ("", ""))
            out.append(Preset(Path(f).stem, nm, ds, s, m))
    _presets = out
    return out


def preset_names(library: str | None = None) -> list[str]:
    return [f"{p.library}/{p.name}" for p in presets() if library in (None, p.library)]


def find_preset(name: str) -> Preset:
    """'Metallic Chrome' or 'simple4/Metallic Chrome' (case-insensitive), or 'Complex fx/@14' for
    the 15th preset of a library (the unnamed 'Untitled Preset' entries are real materials)."""
    lib, _, nm = name.rpartition("/")
    if nm.startswith("@") and nm[1:].isdigit():
        return [p for p in presets() if p.library.lower() == lib.lower()][int(nm[1:])]
    hits = [p for p in presets() if p.name.lower() == nm.lower() and (not lib or p.library.lower() == lib.lower())]
    if not hits:
        raise KeyError(name)
    return hits[0]


def transplant_material(src: Scene, oid: int, sb: SceneBuilder | Scene, name: str | None = None) -> Obj:
    """Copy material `oid` of scene `src` with every texture / picture it references into the
    destination scene, with fresh object ids. Returns the new material Obj."""
    dst = sb.scene if isinstance(sb, SceneBuilder) else sb
    m = src.get(oid, "C3dBaseMaterial")
    rec = bytearray(m.a)
    nxt = dst.new_oid()
    remap = {}
    for k in range(4):
        off = SLOTS + SLOT_SIZE * k
        kind, toid = struct.unpack_from(">4sI", rec, off)
        if kind not in (b"brtx", b"pctx"):
            continue
        if (kind, toid) not in remap:
            new = nxt
            nxt += 1
            if kind == b"brtx":
                t = src.get(toid, "C3dTexture")
                dst.insert(Obj("C3dTexture", new, t.a, t.b, t.tail))
            else:
                pt = src.get(toid, "CPictTexture")
                imgs = [o for o in src.objs if o.oid == toid and o.cls in ("C3dCImage", "ImageIV32ARGB")]
                for im in imgs:
                    dst.insert(Obj("C3dCImage", new, im.a, im.b, im.tail))
                dst.insert(Obj("CPictTexture", new, pt.a, pt.b, pt.tail))
            remap[(kind, toid)] = new
        struct.pack_into(">I", rec, off + 4, remap[(kind, toid)])
    if name is not None:
        rec[:0x80] = name.encode("latin-1")[:127].ljust(0x80, b"\0")
    out = Obj("C3dBaseMaterial", nxt, bytes(rec), m.b, m.tail)
    dst.insert(out)
    return out


def preset(sb: SceneBuilder, name: str, **overrides) -> Obj:
    """Transplant a Materials-palette preset into the builder; overrides as set_material."""
    p = find_preset(name)
    m = transplant_material(p.scene, p.material.oid, sb)
    if overrides:
        m.a = set_material(m.a, **overrides)
    return m
