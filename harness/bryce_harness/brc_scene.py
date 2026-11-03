"""Scene-level parts of Bryce 2 .BRC files: object attributes, groups / booleans, lights,
sky & fog, sun, camera, document size. Field maps and their status: docs/brc/scene.md.

Builds on brc.py (container, object store, transforms, materials) without changing it:

    from bryce_harness import brc, brc_scene as bs
    sb = brc.SceneBuilder()
    bs.set_sky(sb, mode="custom", sky_dome="#2050ff", horizon="#ffffff", haze=0, shadows=80)
    cube = sb.add("cube", offset=(0, 10.24, 0))
    hole = sb.add("sphere", offset=(0, 20.48, 0), size=(24, 24, 24))
    bs.group(sb, [cube, hole], booleans=["positive", "negative"])   # cube minus sphere
    bs.add_light(sb, "sphere", offset=(0, 40, -30), color="#ffd090", intensity=60)
    bs.set_document(sb.scene, 640, 320)
    sb.write("work/x.brc")

All offsets are byte offsets into the object record (slot A, or slot B for brycedocset).
Big-endian unless noted; the transform block (brc.T_*) is little-endian.
"""
from __future__ import annotations

import math
import struct

import numpy as np

from . import brc

TEMPLATES = brc.TEMPLATES

# =========================================================================== common object header
# Every scene object (primitives, groups, lights, terrains, meshes) starts the same way:
#   0x00  name (128 B, NUL-terminated)       0x80  tag (8 B, e.g. "3dobsphr", "lghtsphr")
#   0x88  u32 editor state                   0x8c  u32 attributes
#   0x90  "base" + u32 material id (primitives, groups; lights have zeros)
#   0x1bc.. transform block (see brc.py)     0x2e0 u8 family index, 0x2e4 3 x u8 family (wireframe) colour
OBJ_STATE = 0x88
OBJ_ATTR = 0x8c
OBJ_FAMILY = 0x2e0
OBJ_FAMILY_RGB = 0x2e4

STATE_SELECTED = 0x01     # V (cleared on members when Bryce groups them; set on the new group)
STATE_LOCKED = 0x02       # V (set together with ATTR_LOCKED)
STATE_SHOW_AS_BOX = 0x08  # V

ATTR_LOCKED = 0x02        # V
ATTR_NEUTRAL_MAC = 0x04   # P: set on most neutral objects in the Mac-made sample scenes; Bryce 2.1 Win writes 0
ATTR_POSITIVE = 0x08      # V
ATTR_NEGATIVE = 0x10      # V
ATTR_INTERSECT = 0x20     # V (Win 2.1). The Mac samples use 0x20 on members of plain groups instead (P)
ATTR_IN_BOOL_GROUP = 0x40  # V: member of a boolean group (Bryce sets it when grouping)
ATTR_LIGHT = 0x80         # P: set on every light in the samples
GROUP_PLAIN_MAC = 0x10000  # P: plain group in the Mac samples (Win 2.1 writes 0)
GROUP_BOOLEAN = 0x20000   # V: group that contains positive/negative/intersect members

BOOLEAN = {None: 0, "neutral": 0, "positive": ATTR_POSITIVE, "negative": ATTR_NEGATIVE,
           "intersect": ATTR_INTERSECT}


def _u32(rec: bytes, off: int) -> int:
    return struct.unpack_from(">I", rec, off)[0]


def _put(rec: bytes, off: int, fmt: str, *vals) -> bytes:
    a = bytearray(rec)
    struct.pack_into(fmt, a, off, *vals)
    return bytes(a)


def set_name(obj: brc.Obj, name: str):
    """Object name (shown in Bryce's object list / attributes)."""
    a = bytearray(obj.a)
    a[:0x80] = name.encode("latin-1")[:127].ljust(0x80, b"\0")
    obj.a = bytes(a)


def get_attributes(obj: brc.Obj) -> dict:
    st, at = _u32(obj.a, OBJ_STATE), _u32(obj.a, OBJ_ATTR)
    boolean = next((k for k, v in BOOLEAN.items() if v and at & v), "neutral")
    return dict(boolean=boolean, locked=bool(at & ATTR_LOCKED), show_as_box=bool(st & STATE_SHOW_AS_BOX),
                selected=bool(st & STATE_SELECTED), in_boolean_group=bool(at & ATTR_IN_BOOL_GROUP),
                family=obj.a[OBJ_FAMILY], name=obj.name)


def set_attributes(obj: brc.Obj, boolean: str | None = None, locked: bool | None = None,
                   show_as_box: bool | None = None, selected: bool | None = None,
                   family: int | None = None, family_rgb=None, name: str | None = None):
    """Object Attributes dialog: boolean = 'neutral' | 'positive' | 'negative' | 'intersect'.
    A boolean attribute only acts inside a group (see group()). Unspecified = unchanged."""
    st, at = _u32(obj.a, OBJ_STATE), _u32(obj.a, OBJ_ATTR)
    if boolean is not None:
        at &= ~(ATTR_NEUTRAL_MAC | ATTR_POSITIVE | ATTR_NEGATIVE | ATTR_INTERSECT)
        at |= BOOLEAN[boolean]
    for flag, val, st_bit, at_bit in ((locked, locked, STATE_LOCKED, ATTR_LOCKED),
                                      (show_as_box, show_as_box, STATE_SHOW_AS_BOX, 0),
                                      (selected, selected, STATE_SELECTED, 0)):
        if flag is None:
            continue
        st = st | st_bit if val else st & ~st_bit
        at = at | at_bit if val else at & ~at_bit
    a = bytearray(obj.a)
    struct.pack_into(">II", a, OBJ_STATE, st, at)
    if family is not None:
        a[OBJ_FAMILY] = family & 0xff
    if family_rgb is not None:
        a[OBJ_FAMILY_RGB:OBJ_FAMILY_RGB + 3] = bytes(int(round(c * 255)) for c in brc._rgb(family_rgb))
    obj.a = bytes(a)
    if name is not None:
        set_name(obj, name)


# =========================================================================== groups
# C3dGroupType record = 0x328-byte header + 12 bytes per member (V, Win 2.1 save):
#   0x88/0x8c state/attributes (0x8c = GROUP_BOOLEAN for a boolean group, else 0)
#   0x90 "base" + material id: the group gets its own default material (Bryce creates one)
#   0x1bc.. transform: identity. Members keep their world transforms.
#   0x2ec 6 x f64 BE  bounding box (min xyz, max xyz), internal units (P: Bryce recomputes it)
#   0x31c u32 group number (1, 2, ... per scene, unique)
#   0x320 u8 1, u8 1, u16 0 (constant in every sample)
#   0x324 u32 member count, then per member: tag (8 B, e.g. "3dobcube") + u32 object id
GROUP_BBOX = 0x2ec
GROUP_NUMBER = 0x31c
GROUP_COUNT = 0x324
GROUP_MEMBERS = 0x328


def members(group: brc.Obj) -> list[tuple[str, int]]:
    n = _u32(group.a, GROUP_COUNT)
    return [(group.a[GROUP_MEMBERS + 12 * i:GROUP_MEMBERS + 12 * i + 8].decode("latin-1"),
             _u32(group.a, GROUP_MEMBERS + 12 * i + 8)) for i in range(n)]


UNIT_EXTENT = {"C3dCube": 0.5, "C3dPyramid": 0.5, "C3dTorusType": 2.0}


def _bbox(scene: brc.Scene, objs) -> tuple[np.ndarray, np.ndarray]:
    lo, hi = np.full(3, np.inf), np.full(3, -np.inf)
    for o in objs:
        if o.cls == "C3dGroupType":
            b = struct.unpack_from(">6d", o.a, GROUP_BBOX)
            lo, hi = np.minimum(lo, b[:3]), np.maximum(hi, b[3:])
            continue
        m = np.array(struct.unpack_from("<9d", o.a, brc.T_MATRIX)).reshape(3, 3)
        p = np.array(struct.unpack_from("<3d", o.a, brc.T_POS))
        # half extents of the primitive's unit box after S*R^T; cube/pyramid span +-0.5 scale,
        # torus +-2 (see brc.SIZE_FACTOR), the others +-1
        ext = np.abs(m).sum(0) * UNIT_EXTENT.get(o.cls, 1.0)
        lo, hi = np.minimum(lo, p - ext), np.maximum(hi, p + ext)
    return lo, hi


def group(sb_or_scene, objs: list, booleans: dict | None = None, name: str = "",
          material: dict | brc.Obj | None = None) -> brc.Obj:
    """Group objects (Objects > Group Objects). `booleans`: a list parallel to objs, or a dict
    {object id: kind}, with kind 'positive' / 'negative' / 'intersect' / None (= keep the member's
    own attribute, positive if it has none). A group is boolean as soon as `booleans` is given or a
    member already is negative / intersect. Returns the C3dGroupType object."""
    scene = sb_or_scene.scene if hasattr(sb_or_scene, "scene") else sb_or_scene
    if isinstance(booleans, (list, tuple)):
        booleans = {o.oid: k for o, k in zip(objs, booleans) if k}
    booleans = dict(booleans or {})
    is_bool = bool(booleans) or any(o.a[OBJ_ATTR + 3] & (ATTR_NEGATIVE | ATTR_INTERSECT) for o in objs)
    for o in objs:
        if is_bool:
            kind = booleans.get(o.oid)
            if kind is None:
                at = _u32(o.a, OBJ_ATTR)
                kind = "negative" if at & ATTR_NEGATIVE else "intersect" if at & ATTR_INTERSECT else "positive"
            set_attributes(o, boolean=kind, selected=False)
            o.a = _put(o.a, OBJ_ATTR, ">I", _u32(o.a, OBJ_ATTR) | ATTR_IN_BOOL_GROUP)
        else:
            set_attributes(o, selected=False)
    head = (TEMPLATES / "scene_C3dGroupType.a").read_bytes()
    tail = (TEMPLATES / "scene_C3dGroupType.tail").read_bytes()
    a = bytearray(head)
    struct.pack_into(">II", a, OBJ_STATE, STATE_SELECTED, GROUP_BOOLEAN if is_bool else 0)
    if isinstance(material, brc.Obj):
        mat = material
    elif hasattr(sb_or_scene, "material"):
        mat = sb_or_scene.material(**(material or {}))
    else:
        ma, mt = brc._tpl("C3dBaseMaterial")
        mat = brc.Obj("C3dBaseMaterial", scene.new_oid(), brc.set_material(ma, **(material or {})), b"", mt)
        scene.insert(mat)
    struct.pack_into(">I", a, brc.OBJ_MATERIAL_REF, mat.oid)
    lo, hi = _bbox(scene, objs)
    struct.pack_into(">6d", a, GROUP_BBOX, *lo, *hi)
    n = 1 + max([_u32(g.a, GROUP_NUMBER) for g in scene.by_class("C3dGroupType")] or [0])
    struct.pack_into(">I", a, GROUP_NUMBER, n)
    struct.pack_into(">I", a, GROUP_COUNT, len(objs))
    for o in objs:
        a += o.tag + struct.pack(">I", o.oid)
    g = brc.Obj("C3dGroupType", scene.new_oid(), bytes(a), b"", tail)
    _insert_class(scene, g)
    if name:
        set_name(g, name)
    return g


def _insert_class(scene: brc.Scene, obj: brc.Obj):
    """Insert keeping scene objects before the sun light / brycedocset, as Bryce orders them."""
    idx = [i for i, o in enumerate(scene.objs) if o.cls == obj.cls]
    if idx:
        scene.objs.insert(idx[-1] + 1, obj)
        return
    for i, o in enumerate(scene.objs):
        if o.cls in ("C3dSunLight", "brycedocset"):
            scene.objs.insert(i, obj)
            return
    scene.objs.append(obj)


# =========================================================================== document (brycedocset)
# The brycedocset object has an empty slot A; its data is the 416-byte slot B (V, differential saves
# of File > Document Setup):
#   0x00 u32 document width, 0x04 u32 document height (aspect = width:height)
#   0x08 u32 render width, 0x0c u32 render height (= document size x "Render Resolution" 1:0.25..1:4)
#   0x10 4 x u32 render rect (top=0, left=0, bottom=render height, right=render width)
#   0x20.. zeros
# Antialiasing, spatial optimisation and the render mode (mask / distance / altitude) are NOT stored
# in the scene (nor in any preference file): they are per-session menu settings, see render().
# 360-panorama render is a camera flag (C3dBaseCamera 0x8c: 0x4001 normal, 0x10001 panorama).
DOC_SIZE = 0x00
DOC_RENDER_SIZE = 0x08
DOC_RECT = 0x10


def get_document(scene: brc.Scene) -> dict:
    b = scene.by_class("brycedocset")[0].b
    w, h, rw, rh = struct.unpack_from(">4I", b, 0)
    return dict(width=w, height=h, render_width=rw, render_height=rh)


def set_document(scene, width: int, height: int, render_scale: float = 1.0, antialias=None,
                 mode: str | None = None):
    """Document size (and aspect) as in File > Document Setup. Render to Disk keeps this aspect
    (its dialog sets the width), so width:height = the sprite's aspect saves rendering unused area.
    render_scale = the dialog's 'Render Resolution' factor (1:1 .. 1:4).

    antialias / mode are NOT part of the .brc format (Bryce keeps them per session, in the Render
    Options menu). They are remembered on the scene object and in a sidecar file written by
    `write()`, and `render()` applies them through the menu."""
    scene = scene.scene if hasattr(scene, "scene") else scene
    d = scene.by_class("brycedocset")[0]
    rw, rh = int(round(width * render_scale)), int(round(height * render_scale))
    b = bytearray(d.b or bytes(416))
    struct.pack_into(">8I", b, 0, width, height, rw, rh, 0, 0, rh, rw)
    d.b = bytes(b)
    if antialias is not None or mode is not None:
        if antialias not in ANTIALIAS or mode not in RENDER_MODE:
            raise ValueError(f"antialias={antialias!r} mode={mode!r}")
        opts = dict(getattr(scene, "render_options", {}) or {})
        if antialias is not None:
            opts["antialias"] = antialias
        if mode is not None:
            opts["mode"] = mode
        scene.render_options = opts


def _sidecar(path) -> str:
    return str(path) + ".render.json"


def write(sb_or_scene, path):
    """Write the .brc, plus `<path>.render.json` with the session render options from set_document
    (removed when there are none)."""
    import json
    import os
    scene = sb_or_scene.scene if hasattr(sb_or_scene, "scene") else sb_or_scene
    scene.write(path)
    opts = getattr(scene, "render_options", None)
    if opts:
        with open(_sidecar(path), "w") as f:
            json.dump(opts, f)
    elif os.path.exists(_sidecar(path)):
        os.remove(_sidecar(path))
    return path


# =========================================================================== rendering with session options
RENDER_OPTIONS_AT = (132, 407)      # frame-relative: Control palette "Render Options..." triangle
ANTIALIAS = {None: None, False: "AntiAliasing Off", "off": "AntiAliasing Off",
             True: "AntiAliasing (Normal", "normal": "AntiAliasing (Normal",
             "supreme": "AntiAliasing (Supreme"}
RENDER_MODE = {None: None, "perspective": "Perspective Render", "mask": "Mask Render",
               "distance": "Distance Render", "altitude": "Altitude Render"}


def render_option(vm, item: str):
    """Pick an item of the Control palette's Render Options menu (OCR on the item text)."""
    import time
    from . import bryce, screen
    from .probe import frame_box
    bryce.focus(vm)
    fb = frame_box(vm.screenshot())
    vm.click(fb[0] + RENDER_OPTIONS_AT[0], fb[1] + RENDER_OPTIONS_AT[1])
    time.sleep(1.0)
    img = vm.screenshot()
    pos = screen.find_text(img, item)
    if not pos:
        vm.key("esc")
        raise RuntimeError(f"render option {item!r} not found")
    vm.click(*pos)
    time.sleep(0.8)


def render(scene_host: str, out_host: str, width: int, antialias=None, mode: str | None = None,
           timeout: float = 6 * 3600, instance=None):
    """bryce.render_job with the per-session render options set first. scene_host is a .brc path
    (options from its `.render.json` sidecar apply unless given here) or a Scene/SceneBuilder
    (written next to out_host as .brc first).
    antialias = None (Bryce default: off) | 'off' | 'normal' | 'supreme' (True = 'normal');
    mode = None | 'perspective' | 'mask' | 'distance' | 'altitude'."""
    import json
    import os
    import time
    from . import bryce
    from .winebox import WineBryce
    if not isinstance(scene_host, (str, os.PathLike)):        # Scene / SceneBuilder: write it first
        obj, scene_host = scene_host, os.path.splitext(str(out_host))[0] + ".brc"
        write(obj, scene_host)
    if os.path.exists(_sidecar(scene_host)):
        opts = json.load(open(_sidecar(scene_host)))
        antialias = opts.get("antialias") if antialias is None else antialias
        mode = opts.get("mode") if mode is None else mode
    w = WineBryce(*instance) if instance else WineBryce()
    w.stop()
    time.sleep(1.5)
    w.start()
    bryce.open_scene(w, w.guest_path(scene_host), wait=2.0)
    for item in (ANTIALIAS[antialias], RENDER_MODE[mode]):
        if item:
            render_option(w, item)
    _render_to_disk(w, w.guest_path(out_host), width, out_host, timeout)
    return out_host


def _find_in_view(vm, text: str):
    """OCR for a dialog label. bryce.render_to_disk OCRs the whole view, which fails on wide
    documents (mostly black view); retry on crops around the screen centre, where Bryce
    centres its dialogs."""
    from . import bryce, screen
    from .probe import frame_box
    img = vm.screenshot()
    x0, y0, x1, y1 = bryce.view_box(frame_box(img))
    cx, cy = img.width // 2, img.height // 2
    for hw, hh in ((10000, 10000), (200, 180), (140, 130)):
        box = (max(x0, cx - hw), max(y0, cy - hh), min(x1, cx + hw), min(y1, cy + hh))
        pos = screen.find_text(img, text, box=box)
        if pos:
            return pos
    return None


def _render_to_disk(vm, guest_out: str, width: int, wait_file: str, timeout: float):
    """bryce.render_to_disk with a more robust dialog search (same waiting strategy)."""
    import os
    import time
    from . import bryce, screen
    if os.path.exists(wait_file):
        os.unlink(wait_file)
    bryce.menu(vm, "File", "Render to Disk")
    time.sleep(1.0)
    pos = _find_in_view(vm, "Output Size in Pixels")
    if not pos:
        raise RuntimeError("Render to Disk dialog not found")
    vm.click(pos[0] + 104, pos[1] - 3, double=True)
    vm.key("ctrl-a"); vm.type(str(width)); vm.key("tab")
    time.sleep(0.4)
    vm.key("ret")
    time.sleep(1.5)
    bryce._file_dialog(vm, guest_out, settle=0.5)
    time.sleep(1.0)
    img = vm.screenshot()
    if screen.find_text(img, "replace") or screen.find_text(img, "already exists"):
        vm.key("y")
    t0, seen_open = time.time(), False
    while time.time() - t0 < timeout:
        if os.path.exists(wait_file):
            if vm.holds_open(wait_file):
                seen_open = True
            elif seen_open or time.time() - os.path.getmtime(wait_file) > 10:
                time.sleep(0.5)
                return wait_file
        if not vm.running():
            raise RuntimeError("Bryce exited during Render to Disk")
        time.sleep(1.0)
    raise TimeoutError("render to disk did not finish")


# =========================================================================== lights
# Edit Lights dialog (Objects > Edit Object on a light). Records: C3dSphereLight 785 B ("radial"
# light), C3dConeLight 792 B (spotlight), C3dCubeLight 792 B (square light: no parameters stored,
# see docs). Common object header + transform block as primitives, then (BE):
#   0x8c  attributes: 0x80 light (P), 0x200 Visible Light (V), 0x800 Disable Cast Shadows (V),
#         0x2000 Infinite Light = no distance falloff (V)
#   0x2e8 u32 0 (P: gel reference slot; applying a gel crashed Bryce under Wine)
#   0x2ec 3 x f32 colour (V)
#   0x2f8 f64 intensity = dialog value / 2 (V; dialog 0..100+)
#   0x300 f64 1.0 in every sample (?)
#   0x310 f64 (cone light) edge softness = dialog value / 20 (V)
LIGHT_CLASSES = {"sphere": "C3dSphereLight", "radial": "C3dSphereLight", "spot": "C3dConeLight",
                 "cone": "C3dConeLight", "cube": "C3dCubeLight", "square": "C3dCubeLight"}
L_VISIBLE = 0x200
L_NO_SHADOWS = 0x800
L_INFINITE = 0x2000
L_COLOR = 0x2ec
L_INTENSITY = 0x2f8
L_UNKNOWN_300 = 0x300
L_SOFTNESS = 0x310


def set_light(obj: brc.Obj, color=None, intensity=None, softness=None, visible=None,
              shadows=None, falloff=None):
    """Dialog units: intensity as shown in Edit Lights (default 20), softness 0..100 (spotlights).
    visible = Visible Light (volumetric glow); shadows=False = Disable Cast Shadows;
    falloff=False = Infinite Light."""
    a = bytearray(obj.a)
    at = _u32(a, OBJ_ATTR)
    for val, bit, on_means_set in ((visible, L_VISIBLE, True), (shadows, L_NO_SHADOWS, False),
                                   (falloff, L_INFINITE, False)):
        if val is not None:
            at = at | bit if bool(val) == on_means_set else at & ~bit
    struct.pack_into(">I", a, OBJ_ATTR, at)
    if color is not None:
        struct.pack_into(">3f", a, L_COLOR, *brc._rgb(color))
    if intensity is not None:
        struct.pack_into(">d", a, L_INTENSITY, intensity / 2.0)
    if softness is not None:
        if len(a) < L_SOFTNESS + 8:
            raise ValueError("softness applies to spotlights (C3dConeLight)")
        struct.pack_into(">d", a, L_SOFTNESS, softness / 20.0)
    obj.a = bytes(a)


def get_light(obj: brc.Obj) -> dict:
    at = _u32(obj.a, OBJ_ATTR)
    out = dict(color=struct.unpack_from(">3f", obj.a, L_COLOR),
               intensity=2 * struct.unpack_from(">d", obj.a, L_INTENSITY)[0],
               visible=bool(at & L_VISIBLE), shadows=not at & L_NO_SHADOWS, falloff=not at & L_INFINITE)
    if len(obj.a) >= L_SOFTNESS + 8 and obj.cls == "C3dConeLight":
        out["softness"] = 20 * struct.unpack_from(">d", obj.a, L_SOFTNESS)[0]
    return out


def add_light(sb, kind: str = "sphere", offset=(0, 40, 0), rotate=(0, 0, 0), size=(20.48,) * 3,
              color=(1, 1, 1), intensity: float = 20, softness: float | None = None,
              visible: bool = False, shadows: bool = True, falloff: bool = True, name: str = "") -> brc.Obj:
    """Add a light. kind: 'sphere'/'radial' (point light), 'spot'/'cone' (spotlight; points down its
    local -Y axis, aim it with rotate), 'cube'/'square'. Units as SceneBuilder.add (B, degrees)."""
    cls = LIGHT_CLASSES[kind]
    scene = sb.scene if hasattr(sb, "scene") else sb
    a = (TEMPLATES / f"scene_{cls}.a").read_bytes()
    tail = (TEMPLATES / f"scene_{cls}.tail").read_bytes()
    a = brc.set_transform(a, offset=tuple(offset), rotate=tuple(rotate), size=tuple(size))
    o = brc.Obj(cls, scene.new_oid(), a, b"", tail)
    if cls != "C3dCubeLight":
        set_light(o, color=color, intensity=intensity, visible=visible, shadows=shadows, falloff=falloff,
                  softness=softness if cls == "C3dConeLight" else None)
    else:
        set_light(o, visible=visible, shadows=shadows, falloff=falloff)
    _insert_class(scene, o)
    if name:
        set_name(o, name)
    return o


# =========================================================================== sun
# C3dSunLight (832 B), BE:
#   0x8c  0x280 (Win default), 0x500 in some samples (?)
#   0x2ec 3 x f32 sun colour (V: Sky&Fog "Sun Color" swatch writes 0x2ec and 0x310)
#   0x2f8 f64 1.0, 0x300 f64 1.0 (?)
#   0x310 3 x f32 copy of the sun colour (V)
#   0x31c 3 x f32 Custom Sky colour #1 (V: first swatch of the Custom Sky mode lives in the sun)
#   0x328 3 x f64 unit vector toward the sun (V). Edit Sky&Fog shows it x100 as "Sun x y z".
SUN_COLOR = 0x2ec
SUN_COLOR2 = 0x310
SUN_CUSTOM1 = 0x31c
SUN_DIR = 0x328


def set_sun(sb, toward=None, color=None, custom1=None):
    scene = sb.scene if hasattr(sb, "scene") else sb
    o = scene.by_class("C3dSunLight")[0]
    a = bytearray(o.a)
    if toward is not None:
        v = np.array(toward, float)
        struct.pack_into(">3d", a, SUN_DIR, *(v / np.linalg.norm(v)))
    if color is not None:
        struct.pack_into(">3f", a, SUN_COLOR, *brc._rgb(color))
        struct.pack_into(">3f", a, SUN_COLOR2, *brc._rgb(color))
    if custom1 is not None:
        struct.pack_into(">3f", a, SUN_CUSTOM1, *brc._rgb(custom1))
    o.a = bytes(a)
    return o


# =========================================================================== sky & fog
# C3dBaseSky (376 B), BE. Dialog = Sky&Fog palette / Sky&Fog Options > Edit Sky&Fog. All V by
# differential saves unless noted.
SKY_FLAGS = 0x88          # u32, see SKY_MODE and SKY_* bits
SKY_CLOUD_HEIGHT = 0x8c   # f64 internal units = (50 + 16 * dialog Height) / 10.24
SKY_CUMULUS_RGB = 0x94    # 3 x f32 "Cumulus Color"
SKY_A0_RGB = 0xa0         # 3 x f32 (1,1,1), meaning unknown (?)
SKY_CLOUD_COVER = 0xbc    # f64 = dialog Clouds / 40
SKY_AMPLITUDE = 0xc4      # f64 = dialog Amplitude / 100
SKY_FREQUENCY = 0xcc      # f64 = dialog Scale (Frequency) / 100 (min 1e-7)
SKY_CUSTOM2_RGB = 0xec    # 3 x f32 Custom Sky swatch 2 (default 0.2, 0.2, 1)
SKY_CUSTOM3_RGB = 0xf8    # 3 x f32 Custom Sky swatch 3 (default white)
SKY_104_RGB = 0x104       # 3 x f32 (0 in Win default; varies in samples) (?)
SKY_BACKGROUND_RGB = 0x110  # 3 x f32 "Atmosphere Off" background colour (default 0.2, 0.2, 1)
SKY_SHADOWS = 0x11c       # f64 = 1 - dialog Shadow / 100 (default dialog 90)
SKY_AMBIENT_RGB = 0x124   # 3 x f32 "Ambient Color" (swatch under Shadows)
SKY_130 = 0x130           # f64 1.0 in every sample (?)
SKY_HAZE_RGB = 0x138      # 3 x f32 "Haze Color"
SKY_HAZE = 0x144          # f64 = dialog Haze / 20 (default dialog 8)
SKY_FOG_RGB = 0x14c       # 3 x f32 "Fog Color"
SKY_FOG = 0x158           # f64 = dialog Fog^2 / 2000
SKY_FOG_HEIGHT = 0x160    # f64 = dialog Fog Height / 100
SKY_TEXTURES = 0x168      # "xtrb" "xtrb" + 2 x u32 LITTLE-endian ids of the cloud C3dTextures (P)

SKY_MODE = {"off": 0x0, "soft": 0x3, "darker": 0x5, "custom": 0x9}   # low 4 bits of SKY_FLAGS
SKY_CLOUDS = 0x10         # set whenever stratus or cumulus is on
SKY_STRATUS = 0x20
SKY_CUMULUS = 0x40
SKY_80 = 0x80             # set in Win default (?)
SKY_LINK_SUN = 0x200      # "Link Sun to View"


def get_sky(scene) -> dict:
    scene = scene.scene if hasattr(scene, "scene") else scene
    a = scene.by_class("C3dBaseSky")[0].a
    d = lambda off: struct.unpack_from(">d", a, off)[0]
    c = lambda off: struct.unpack_from(">3f", a, off)
    fl = _u32(a, SKY_FLAGS)
    return dict(mode=next((k for k, v in SKY_MODE.items() if v == fl & 0xf), hex(fl & 0xf)),
                stratus=bool(fl & SKY_STRATUS), cumulus=bool(fl & SKY_CUMULUS),
                link_sun=bool(fl & SKY_LINK_SUN),
                shadows=100 * (1 - d(SKY_SHADOWS)), fog=math.sqrt(max(0.0, d(SKY_FOG)) * 2000),
                fog_height=100 * d(SKY_FOG_HEIGHT), haze=20 * d(SKY_HAZE),
                cloud_cover=40 * d(SKY_CLOUD_COVER), cloud_height=(d(SKY_CLOUD_HEIGHT) * 10.24 - 50) / 16,
                frequency=100 * d(SKY_FREQUENCY), amplitude=100 * d(SKY_AMPLITUDE),
                ambient=c(SKY_AMBIENT_RGB), haze_color=c(SKY_HAZE_RGB), fog_color=c(SKY_FOG_RGB),
                cumulus_color=c(SKY_CUMULUS_RGB), custom2=c(SKY_CUSTOM2_RGB), custom3=c(SKY_CUSTOM3_RGB),
                background=c(SKY_BACKGROUND_RGB))


def set_sky(sb, mode: str | None = None, shadows=None, ambient=None, fog=None, fog_height=None,
            fog_color=None, haze=None, haze_color=None, cloud_cover=None, cloud_height=None,
            frequency=None, amplitude=None, cumulus_color=None, stratus=None, cumulus=None,
            link_sun=None, background=None, custom1=None, custom2=None, custom3=None,
            sun=None, sun_color=None):
    """Sky & Fog in the dialog's own units (Edit Sky&Fog / palette thumbnails):
    mode 'soft' | 'darker' | 'custom' | 'off'; shadows 0..100 (default 90); fog 0..100,
    fog_height 0..100; haze 0..100 (default 8; 0 = backdrops render exactly their colour);
    cloud_cover 0..100 (20), cloud_height (3), frequency = 'Scale' (25), amplitude (100);
    stratus / cumulus switch the cloud layers; colours as '#rrggbb' or (r, g, b) 0..1.
    background = colour when mode='off'. custom1..3 = the three Custom Sky swatches.
    sun = vector toward the sun, sun_color = sun light colour."""
    scene = sb.scene if hasattr(sb, "scene") else sb
    o = scene.by_class("C3dBaseSky")[0]
    a = bytearray(o.a)
    fl = _u32(a, SKY_FLAGS)
    if mode is not None:
        fl = (fl & ~0xf) | SKY_MODE[mode]
    for val, bit in ((stratus, SKY_STRATUS), (cumulus, SKY_CUMULUS), (link_sun, SKY_LINK_SUN)):
        if val is not None:
            fl = fl | bit if val else fl & ~bit
    fl = fl | SKY_CLOUDS if fl & (SKY_STRATUS | SKY_CUMULUS) else fl & ~SKY_CLOUDS
    struct.pack_into(">I", a, SKY_FLAGS, fl)
    scal = ((shadows, SKY_SHADOWS, lambda v: 1 - v / 100), (fog, SKY_FOG, lambda v: v * v / 2000),
            (fog_height, SKY_FOG_HEIGHT, lambda v: v / 100), (haze, SKY_HAZE, lambda v: v / 20),
            (cloud_cover, SKY_CLOUD_COVER, lambda v: v / 40),
            (cloud_height, SKY_CLOUD_HEIGHT, lambda v: (50 + 16 * v) / 10.24),
            (frequency, SKY_FREQUENCY, lambda v: max(v / 100, 1e-7)), (amplitude, SKY_AMPLITUDE, lambda v: v / 100))
    for val, off, f in scal:
        if val is not None:
            struct.pack_into(">d", a, off, float(f(val)))
    cols = ((ambient, SKY_AMBIENT_RGB), (fog_color, SKY_FOG_RGB), (haze_color, SKY_HAZE_RGB),
            (cumulus_color, SKY_CUMULUS_RGB), (background, SKY_BACKGROUND_RGB),
            (custom2, SKY_CUSTOM2_RGB), (custom3, SKY_CUSTOM3_RGB))
    for val, off in cols:
        if val is not None:
            struct.pack_into(">3f", a, off, *brc._rgb(val))
    o.a = bytes(a)
    if sun is not None or sun_color is not None or custom1 is not None:
        set_sun(scene, toward=sun, color=sun_color, custom1=custom1)
    return o


# =========================================================================== camera
# C3dBaseCamera (884 B). Transform block = position + yaw/pitch; 0x2ec forward, 0x304 up (BE f64, V).
# 0x33c f64 "FOV" in radians, default 60 deg. Measured (V, renders at 640 px, 4:3 and 2:1):
# the HORIZONTAL field of view is 0.8 x this value at any document aspect
# (focal length in px = (width / 2) / tan(0.4 * fov)): 60 -> 48 deg, 30 -> 24, 90 -> 72.
# 0x8c: 0x4001 normal, 0x10001 = "360 Panorama Render" (V).
CAM_FOV = 0x33c
CAM_PANORAMA = 0x10001
CAM_NORMAL = 0x4001


def set_camera(sb, position, look_at=None, forward=None, hfov: float | None = None,
               fov: float | None = None, panorama: bool | None = None, name: str = "perspective"):
    """Like SceneBuilder.camera, plus hfov = true horizontal field of view in degrees
    (stored value = hfov / 0.8), or the raw Bryce value `fov`. panorama: 360 render."""
    if hfov is not None:
        fov = hfov / 0.8
    cam = sb.camera(position, look_at=look_at, forward=forward, fov=fov, name=name)
    if panorama is not None:
        cam.a = _put(cam.a, OBJ_ATTR, ">I", CAM_PANORAMA if panorama else CAM_NORMAL)
    return cam
