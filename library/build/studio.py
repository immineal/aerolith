"""The shared studio every component sheet is rendered in.

Coordinates are CSS px (x right, y down) on the z=0 plane; 1 Bryce unit = 1 CSS px. The camera
sits far away on -Z with a long lens (Bryce's FOV field is the *diagonal* angle), so the sheet is
near-orthographic and a point (x, y) lands at render pixel (6x, 6y). Depth (z) is toward the
backdrop: negative z comes toward the camera.

The lighting rig is fixed, so all components look like one family:
  sun        upper-left, slightly from the front (highlights top-left, shadows fall away)
  key box    big white softbox above, between camera and sheet: the band highlight on tops
  sky        Bryce's default sky behind the camera: blue reflections in the lower half
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "harness"))

from bryce_harness import sheet  # noqa: E402

from export import RENDER_SCALE  # noqa: E402

D = 4000.0        # camera distance (B = CSS px)


class Studio:
    def __init__(self, ctx: "sheet.Ctx", width: float = 320, height: float = 240, rig: str = "meadow"):
        self.c = ctx
        self.w, self.h = width, height
        hfov = math.degrees(2 * math.atan(width / 2 / D))      # Bryce: horizontal FOV = 0.8 x stored (V)
        ctx.camera((0, 0, -D), look_at=(0, 0, 0), hfov=hfov)
        k = 640 / width                                         # document = sheet aspect, ~640 wide
        ctx.document(width * k, height * k)
        ctx.backdrop_z = 3 * D
        ctx.backdrop_size = 40 * D
        self.rig(rig)

    @property
    def render_width(self) -> int:
        return int(self.w * RENDER_SCALE)

    # coordinates ---------------------------------------------------------
    def p(self, x, y, z=0.0):
        """CSS px (sheet coords, y down) -> Bryce position."""
        return (x - self.w / 2, self.h / 2 - y, z)

    # lighting ------------------------------------------------------------
    def rig(self, name: str):
        c = self.c
        if name == "aero":
            from bryce_harness import brc_scene
            c.sun((-0.45, 0.75, -0.5))
            # reflection environment: Aero sky (custom mode: main colour + white horizon), no haze
            brc_scene.set_sky(c.sb, mode="custom", custom2="#3f9ee8", custom3="#f2fbff", haze=0)
            # key softbox: above the sheet, tilted toward it, out of frame -> top highlight band
            c.softbox(offset=(0, 900, -900), size=(5000, 1, 1400), rotate=(-30, 0, 0), strength=1.0)
            # floor bounce: dim cyan card below, toward the camera -> soft glow on lower edges
            c.softbox(offset=(0, -900, -700), size=(5000, 1, 1400), rotate=(30, 0, 0),
                      color=(0.75, 0.95, 1.0), strength=0.55)
            # bright floor far below (reflections only): the lower half of every gloss/orb shows
            # a pale cyan floor under a crisp horizon instead of the dark below-horizon sky
            c.ground(-max(1500.0, 8 * self.h), color=(0.62, 0.8, 0.95))
        elif name == "meadow":
            from bryce_harness import brc_scene
            c.sun((-0.45, 0.75, -0.5))
            # sky: deep blue overhead, paler at the horizon; no clouds (flat faces reflect the horizon
            # straight back, and Bryce clouds streak there), no haze
            brc_scene.set_sky(c.sb, mode="custom", custom2="#2f86e0", custom3="#9fd0f8", haze=0,
                              cumulus=False, stratus=False)
            # key softbox: the signature highlight band across the top of every gloss surface
            c.softbox(offset=(0, 900, -900), size=(5000, 1, 1400), rotate=(-30, 0, 0), strength=1.0)
            # meadow (reflections only; the camera sees just the matte backdrop). Front faces
            # reflect what is behind the camera (-z). The land falls away TILT degrees behind the
            # camera (the sprite is "held up to the sky"): flat faces mirror blue sky just above
            # the horizon, curved lower bevels and orbs catch the grass and the hills.
            tilt = math.radians(8.0)
            gy = -max(1500.0, 8 * self.h)
            grass = lambda col, amb=0.95: dict(diffuse=col, diffusion=0.25, ambient=col, ambience=amb,
                                               specularity=0.0)
            L = 200000.0
            c.env("square", (0, gy - L * math.sin(tilt), -L * math.cos(tilt)),
                  (-math.degrees(tilt), 0, 0), (2 * L, 1, 2 * L), grass("#3f9a1e", 0.85))
            # hills: (x, distance behind, width, depth, top in degrees relative to eye level, colour)
            for hx, hz, hw, hd, top, col in ((-9000, 32000, 70000, 26000, -1.5, "#6cc22e"),
                                             (26000, 38000, 60000, 22000, -3.5, "#55b026")):
                base = gy - hz * math.tan(tilt)
                ty = -hz * math.tan(math.radians(-top)) if top < 0 else hz * math.tan(math.radians(top))
                c.env("sphere", (hx, base, -hz), (0, 0, 0), (hw, 2 * (ty - base), hd), grass(col))
        elif name == "flat":
            c.sun((0, 0.3, -1))
        else:
            raise ValueError(name)

    # geometry helpers (CSS px) ----------------------------------------------
    def capsule(self, x, y, w, h, mat, z=0.0, depth=None):
        """Horizontal pill, top-left corner at (x, y), w x h CSS px. depth = front-to-back size."""
        d = depth or h
        r = h / 2
        cx, cy = x + w / 2, y + h / 2
        L = max(w - h, 0.0)
        c = self.c
        if L > 0:
            c.add("cylinder", self.p(cx, cy, z), (0, 0, 90), (h, L, d), mat)
        c.add("sphere", self.p(x + r, cy, z), (0, 0, 0), (h, h, d), mat)
        c.add("sphere", self.p(x + w - r, cy, z), (0, 0, 0), (h, h, d), mat)

    def slab(self, x, y, w, h, radius, bevel, thickness, mat, z=0.0, profile="ease", n=None,
             heights=None, dish=0.0, well=None):
        """Single-surface rounded slab (symmetrical lattice), outline w x h CSS px with corner
        `radius`, edge rising over `bevel` px, total front-to-back `thickness`. Facing the camera.
        heights: optional custom 0..1 map (rows = y down) instead of the rounded rectangle.
        dish: sink the face into a smooth bowl, as a fraction of the half-thickness (pressed keys:
        the face then catches the overhead light on its lower edge, the highlight flips)."""
        if n is None:
            n = lattice_n(w, h)
        if heights is None:
            heights = rounded_rect_aniso(w, h, radius, bevel, n, profile, dish, well)
        cx, cy = x + w / 2, y + h / 2
        self.c.heightfield(heights, offset=self.p(cx, cy, z), rotate=(-90, 0, 0),
                           size=(w, thickness / 2, h), material=mat)

    def pill(self, x, y, w, h, mat, bevel=None, thickness=None, z=0.0, profile="ease", dish=0.0):
        """Seamless pill: a slab with fully round ends."""
        self.slab(x, y, w, h, h / 2, bevel if bevel is not None else h / 2,
                  thickness if thickness is not None else h * 0.8, mat, z, profile, dish=dish)

    def orb(self, x, y, size, mat, z=0.0):
        self.c.add("sphere", self.p(x + size / 2, y + size / 2, z), (0, 0, 0), (size, size, size), mat)

    def box(self, x, y, w, h, d, mat, z=0.0, rotate=(0, 0, 0)):
        self.c.add("cube", self.p(x + w / 2, y + h / 2, z), rotate, (w, h, d), mat)


def lattice_n(w, h, scale=RENDER_SCALE):
    """Grid size for a lattice spanning w x h CSS px: ~1 cell per 2 render px on the long side
    (N=256 is indistinguishable from 512 on an 80 px pill; 128 shows facets; cost ~ N)."""
    px = max(w, h) * scale / 2
    return int(min(512, max(128, 32 * math.ceil(px / 32))))


def rounded_rect_aniso(w, h, radius, bevel, n=512, profile="ease", dish=0.0, well=None):
    """Height map (n x n, rows = y down) of a w x h CSS-px rounded rectangle: each grid cell is
    (w/n) x (h/n) px, so distances are computed in CSS px and the bevel stays uniform."""
    import numpy as np
    from bryce_harness.brc_hfield import shape_profile
    pad = 1.5
    xs = (np.arange(n) + 0.5) / n * w - w / 2
    ys = (np.arange(n) + 0.5) / n * h - h / 2
    X, Y = np.meshgrid(xs, ys)
    hx, hy = w / 2 - pad * w / n, h / 2 - pad * h / n
    r = min(radius, hx, hy)
    qx, qy = np.abs(X) - (hx - r), np.abs(Y) - (hy - r)
    outside = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - r
    d = np.clip(-outside, 0, None)
    hgt = shape_profile(np.clip(d / max(bevel, 1e-6), 0, 1), profile)
    if dish:
        # smooth bowl: the face mask blurred (in CSS px, per axis) -> no crease along the medial
        # axis, and uniform along a pill's length (3-slice safe); peak depth = dish
        from scipy import ndimage
        face = (d >= bevel).astype(float)
        sig = max(min(w, h) / 2 - bevel, 1.0) * 0.6
        bowl = ndimage.gaussian_filter(face, (sig * n / h, sig * n / w), mode="constant")
        bowl = np.clip(bowl / max(bowl.max(), 1e-6), 0, 1) * face
        hgt = hgt - dish * bowl
    if well:
        # recessed well (text fields, basins): rim rises over `bevel`, then the surface drops
        # over `lip` CSS px to a flat floor at `floor` (fraction of full height; > 0 so the
        # symmetrical lattice never opens a hole)
        floor, lip = well
        t = np.clip((d - bevel) / max(lip, 1e-6), 0, 1)
        hgt = hgt - (1 - floor) * t * t * (3 - 2 * t)
    return hgt


def build_sheet(name: str, fn, width=320, height=240, rig="meadow", scale=RENDER_SCALE, antialias=None):
    """Render a sheet: fn(studio) places things. Returns (rgba at `scale` px per CSS px, paths)."""
    out = ROOT / "work" / "sheets" / name

    def build(ctx):
        st = Studio(ctx, width, height, rig)
        fn(st)

    bmps = sheet.render_sheet(out, build, int(round(width * scale)), antialias=antialias)
    rgba = sheet.matte(bmps)
    return rgba, bmps
