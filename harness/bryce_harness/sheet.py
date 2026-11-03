"""Sprite sheets: one Bryce scene rendered in three passes, matted into RGBA.

    K  backdrop pure black         (colour source)
    W  backdrop mid grey (GREY)    (K vs W difference gives alpha for glass / soft edges; grey, not
                                   white, so reflection + transmission never clips at 1.0)
    M  every object flat white on black, sun from the camera (crisp silhouette)

alpha = min(M, 1 - (W - K)); colour = K / alpha.  Reflections of front-facing surfaces go
toward the camera (the sky behind it), not into the backdrop, so solid glossy objects stay opaque;
glass picks up partial alpha and keeps its own tint/highlights.

Usage:
    def build(c):                         # c: Ctx; place things in Bryce units
        c.camera((0, 0, -200), look_at=(0, 0, 0), fov=30)
        c.add("sphere", offset=(0, 0, 0), material=dict(diffuse="#2a7fff", specularity=1))
        c.softbox(offset=(0, 120, -100), size=(300, 1, 200))
    passes = render_sheet("work/sheets/test", build, width=1920)
    rgba = matte(passes)                  # float HxWx4
"""
from __future__ import annotations

import concurrent.futures as cf
from pathlib import Path

import numpy as np

from . import brc, sprites

FLAT = dict(diffuse=(0, 0, 0), diffusion=0.0, ambient=(1, 0, 0), ambience=1.0, specularity=0.0,
            reflection=0.0, transparency=0.0)       # solid objects: red in the mask pass
FLAT_GLASS = dict(FLAT, ambient=(0, 1, 0))           # glass (transparency > 0): green


def _is_glass(material) -> bool:
    if isinstance(material, dict):
        if "glass" in material:
            return bool(material["glass"])
        return material.get("transparency", 0) > 0
    return False


class Ctx:
    def __init__(self, mode: str, backdrop_z: float = 400.0, backdrop_size: float = 6000.0):
        self.mode = mode
        self.sb = brc.SceneBuilder()
        self.sb.sky(haze=0.0)
        self._cam = None
        self._sun = (-0.5, 0.7, -0.6)
        self.backdrop_z = backdrop_z
        self.backdrop_size = backdrop_size
        self.doc = None                 # (w, h) document size: sets the render aspect

    def document(self, w, h):
        self.doc = (int(round(w)), int(round(h)))

    # scene description ------------------------------------------------
    def camera(self, position, look_at, fov=None, hfov=None):
        """fov = Bryce's stored FOV value; hfov = true horizontal angle (stored = hfov / 0.8, V)."""
        self._cam = (np.array(position, float), np.array(look_at, float))
        if hfov is not None:
            fov = hfov / 0.8
        self.sb.camera(position, look_at=look_at, fov=fov)

    def sun(self, toward):
        self._sun = toward

    def mat(self, material):
        """Resolve a material spec for this pass. dict = SceneBuilder fields; may contain
        'preset': 'Metallic Chrome' (+ overrides) and 'glass': bool (mask colour override).
        The mask pass replaces everything by flat red (solid) / green (glass)."""
        material = dict(material or {})
        if self.mode == "m":
            return dict(FLAT_GLASS if _is_glass(material) else FLAT)
        material.pop("glass", None)
        name = material.pop("preset", None)
        if name:
            from . import brc_material
            return brc_material.preset(self.sb, name, **material)
        return material

    def add(self, kind, offset=(0, 0, 0), rotate=(0, 0, 0), size=(20.48,) * 3, material=None):
        """A visible object (part of the sprite)."""
        return self.sb.add(kind, offset, rotate, size, self.mat(material))

    def heightfield(self, heights, offset=(0, 0, 0), rotate=(0, 0, 0), size=None, material=None,
                    symmetric=True, clip=(0.002, 1.01), **kw):
        """A heightfield / symmetrical lattice (see brc_hfield); mask pass swaps the material."""
        from . import brc_hfield
        return brc_hfield.add_heightfield(self.sb, heights, offset, rotate, size, self.mat(material),
                                          symmetric=symmetric, clip=clip, **kw)

    def softbox(self, offset, size, rotate=(0, 0, 0), color=(1, 1, 1), strength=1.0):
        """An emissive card for reflections/highlights. Lets sunlight through; skipped in the mask pass.
        Keep it out of frame."""
        if self.mode == "m":
            return None
        mat = dict(diffuse=(0, 0, 0), diffusion=0.0, ambient=color, ambience=strength, specularity=0.0,
                   transparency=1.0, transparent=(1, 1, 1))
        return self.sb.add("square", offset, rotate, size, mat)

    def ground(self, y, color=(0.85, 0.95, 1.0), strength=1.0, size=200000.0):
        """A self-lit floor far below the sprite: only reflections see it (view rays reach the
        backdrop first). Gives glossy surfaces a bright lower half instead of the dark
        below-horizon sky. Skipped in the mask pass."""
        if self.mode == "m":
            return None
        mat = dict(diffuse=(0, 0, 0), diffusion=0.0, ambient=color, ambience=strength, specularity=0.0)
        return self.sb.add("square", (0, y, 0), (0, 0, 0), (size, 1, size), mat)

    def env(self, kind, offset, rotate=(0, 0, 0), size=(1, 1, 1), material=None):
        """Environment-only object (hills, ground, props seen in reflections, never by the camera):
        added to the K/W passes, skipped in the mask pass."""
        if self.mode == "m":
            return None
        return self.sb.add(kind, offset, rotate, size, dict(material or {}))

    # finishing --------------------------------------------------------
    def finish(self):
        pos, look = self._cam
        fwd = (look - pos) / np.linalg.norm(look - pos)
        back = (0, 0, 0) if self.mode in "km" else (GREY,) * 3
        # backdrop: a big card behind the target, facing the camera
        centre = pos + fwd * (np.linalg.norm(look - pos) + self.backdrop_z)
        yaw = np.degrees(np.arctan2(fwd[0], fwd[2]))
        pitch = -np.degrees(np.arcsin(fwd[1]))
        self.sb.add("square", tuple(centre), (pitch - 90, yaw, 0), (self.backdrop_size, 1, self.backdrop_size),
                    dict(diffuse=(0, 0, 0), diffusion=0.0, ambient=back, ambience=1.0, specularity=0.0))
        self.sb.sun(toward=tuple(-fwd) if self.mode == "m" else self._sun)


GREY = 0.5


def write_passes(out: str | Path, build) -> dict[str, Path]:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    files = {}
    from . import brc_scene
    for mode in "kwm":
        c = Ctx(mode)
        build(c)
        c.finish()
        if c.doc:
            brc_scene.set_document(c.sb, *c.doc)
        files[mode] = Path(brc_scene.write(c.sb, f"{out}_{mode}.brc"))
    return files


from .winebox import WINE

# Bryce instances for the main session's render pool: (X display, Wine prefix).
POOL = [(":77", WINE / "prefix"), (":78", WINE / "prefix_re"), (":79", WINE / "prefix_e"),
        (":81", WINE / "prefix_a"), (":82", WINE / "prefix_b"), (":83", WINE / "prefix_c"),
        (":84", WINE / "prefix_d")]


import queue as _queue
import threading as _threading

_FREE: "_queue.Queue | None" = None
_FREE_LOCK = _threading.Lock()


def _free_instances(pool=None) -> "_queue.Queue":
    """One process-wide queue of idle Bryce instances, so concurrent render_many calls (e.g. several
    sheets built in threads) never drive the same instance at once."""
    global _FREE
    with _FREE_LOCK:
        if _FREE is None:
            _FREE = _queue.Queue()
            for inst in (pool or POOL):
                _FREE.put(inst)
        return _FREE


def render_many(jobs, pool=None, timeout: float = 3 * 3600, retries: int = 2):
    """jobs: [(scene_path, bmp_path, width[, {antialias:..., mode:...}])]; renders them in
    parallel, one job per Bryce instance at a time (instances shared process-wide)."""
    from . import bryce
    free = _free_instances(pool)

    def run(job):
        scene, bmp, width = job[:3]
        opts = job[3] if len(job) > 3 else {}
        for attempt in range(retries + 1):
            try:
                return run_once(scene, bmp, width, opts)
            except Exception as e:              # UI automation hiccups (menu not ready, …)
                if attempt == retries:
                    raise
                print(f"render_many: {Path(str(scene)).name} attempt {attempt + 1} failed ({e}); retrying",
                      flush=True)

    def run_once(scene, bmp, width, opts):
        inst = free.get()
        try:
            bryce.render_job(str(scene), str(bmp), width, timeout=timeout, instance=(inst[0], inst[1]),
                             **opts)
            return bmp
        finally:
            # an idle Bryce under Wine spins a core at 100%: shut the instance down between jobs
            from .winebox import WineBryce
            try:
                WineBryce(display=inst[0], prefix=inst[1]).stop()
            except Exception:
                pass
            free.put(inst)

    with cf.ThreadPoolExecutor(max(1, min(len(jobs), len(pool or POOL)))) as ex:
        return list(ex.map(run, jobs))


def render_sheet(out: str | Path, build, width: int, timeout: float = 3 * 3600, pool=None,
                 antialias=None) -> dict[str, Path]:
    """Write and render the three passes (in parallel on the pool); returns {mode: bmp path}."""
    scenes = write_passes(out, build)
    jobs = [(scene, scene.with_suffix(".bmp"), width, {"antialias": antialias}) for scene in scenes.values()]
    render_many(jobs, pool, timeout)
    return {mode: scene.with_suffix(".bmp") for mode, scene in scenes.items()}


def matte(bmps: dict, ss: int = 1, rim: float = 0.5, despeckle: int = 5, over: str = "light") -> np.ndarray:
    """Solid objects: alpha = silhouette coverage; their colour mixes the black- and white-backdrop
    renders (`rim` = how much of the white backdrop their grazing reflections show).
    Glass: difference matte (partial alpha), clamped to the silhouette."""
    k, w, m = (sprites.load(bmps[x]) for x in "kwm")
    cov = np.clip(m[..., 0] + m[..., 1], 0, 1)
    if despeckle:
        # Bryce's lattice intersection sparkles on steep glass rims (impulse noise, every N, with or
        # without refraction): replace outliers by the local median, inside glass only
        from scipy import ndimage
        zone = ndimage.binary_dilation(m[..., 1] > 0.02, iterations=2)
        for a in (k, w):
            med = ndimage.median_filter(a, size=(despeckle, despeckle, 1))
            bad = zone & (np.abs(a - med).max(2) > 0.06)
            a[bad] = med[bad]
    # backdrop level of the W pass, measured where nothing covers it (GREY now, 1.0 for old sheets)
    empty = cov < 1e-6
    level = float(np.median(w[empty].mean(1))) if empty.any() else 1.0
    w = k + (w - k) / max(level, 1e-3)          # what the pass would be on pure white, unclipped
    g = np.where(cov > 1e-6, m[..., 1] / np.maximum(cov, 1e-6), 0.0)[..., None]
    d = np.clip(1.0 - (w - k).mean(2), 0, 1)
    # Glass = transmission T plus additive light K (reflections, glints): out = K + T*bg. Straight
    # alpha can hold that only while K <= 1 - T, so the matte is tuned to the page it will sit on:
    #   over="light": alpha = 1 - T (bg weight exact; overflow clips toward white, which is what
    #                 the glint looks like on a light page anyway)
    #   over="dark":  alpha raised to K's brightest channel (exact over black; no grey haze)
    a_glass = np.minimum(cov, d if over == "light" else np.maximum(d, k.max(2)))
    pre_solid = (1 - rim) * k + rim * w - rim * (1 - cov)[..., None]
    alpha = (1 - g[..., 0]) * cov + g[..., 0] * a_glass
    pre = np.clip((1 - g) * pre_solid + g * k, 0, None)
    rgb = np.clip(pre / np.maximum(alpha, 1e-6)[..., None], 0, 1)
    rgba = np.dstack([rgb, alpha])
    rgba[alpha <= 1e-6] = 0
    return sprites.downsample(rgba, ss)


def crop(rgba: np.ndarray, box, out_path, pad: int = 2) -> dict:
    """Cut one sprite out of a matted sheet (box in sheet pixels), trim to its alpha, save PNG."""
    x0, y0, x1, y1 = box
    img = sprites.to_image(rgba[y0:y1, x0:x1])
    img, tb = sprites.trim(img, pad)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, optimize=True)
    return {"file": str(out_path), "size": img.size, "box": (x0 + tb[0], y0 + tb[1], x0 + tb[2], y0 + tb[3])}


def components(rgba: np.ndarray, thresh: float = 0.02, min_px: int = 50):
    """Bounding boxes of separate sprites on a sheet (connected alpha regions)."""
    from scipy import ndimage
    lab, n = ndimage.label(rgba[..., 3] > thresh)
    boxes = []
    for i, sl in enumerate(ndimage.find_objects(lab), 1):
        if sl is None:
            continue
        ys, xs = sl
        if (lab[sl] == i).sum() >= min_px:
            boxes.append((xs.start, ys.start, xs.stop, ys.stop))
    return sorted(boxes, key=lambda b: (b[1] // 50, b[0]))
