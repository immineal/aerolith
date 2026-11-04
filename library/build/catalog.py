"""What gets rendered: sheets of items, laid out automatically.

An Item is one sprite: its outline size in CSS px, a draw(st, x, y) that places the Bryce objects
with the outline's top-left at (x, y), the 3/9-slice insets measured from that outline, and whether
it contains glass (then a ".dark" matte variant is exported too).

Sheets are kept small (a handful of items): the passes of all sheets render concurrently on the
Bryce pool, and glass refracts whatever is near it, so items sit `gap` px apart."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import materials as M
import shapes


@dataclass
class Item:
    name: str
    w: float
    h: float
    draw: Callable
    slice: tuple | None = None
    glass: bool = False
    margin: float = 8            # crop room around the outline (glints, glow)
    label: tuple | None = None   # text box relative to the outline, CSS px
    text: str | None = None
    hit: tuple | None = None
    pos: tuple = (0, 0)          # filled in by layout()


@dataclass
class Sheet:
    name: str
    items: list
    max_width: float = 360
    gap: float = 28
    width: float = 0
    height: float = 0

    def layout(self):
        x = y = self.gap
        row_h = 0
        width = 0
        for it in self.items:
            if x + it.w + self.gap > self.max_width and x > self.gap:
                x, y = self.gap, y + row_h + self.gap
                row_h = 0
            it.pos = (x, y)
            x += it.w + self.gap
            row_h = max(row_h, it.h)
            width = max(width, x)
        self.width = int(width + 0.5)
        self.height = int(y + row_h + self.gap + 0.5)
        return self

    def build(self, st):
        for it in self.items:
            it.draw(st, *it.pos)

    @property
    def has_glass(self):
        return any(it.glass for it in self.items)


# ------------------------------------------------------------------ families
SIZES = {"s": (32, 9, 15), "m": (44, 12, 20), "l": (56, 15, 25)}     # height, bevel, thickness
BUTTON_COLOURS = {
    "primary": (M.AQUA, M.AQUA_HOVER, M.AQUA_ACTIVE),
    "secondary": (M.GREEN, M.GREEN_HOVER, M.GREEN_ACTIVE),
}


PRESS_DISH = 0.35       # pressed buttons: face sinks into a bowl (highlight flips to the bottom)


def pill_item(name, w, h, mat, bevel, thick, glass=False, z=0.0, label=None, text=None, dish=0.0):
    def draw(st, x, y):
        st.pill(x, y, w, h, mat, bevel=bevel, thickness=thick, z=z, dish=dish)
    return Item(name, w, h, draw, slice=(0, h / 2, 0, h / 2), glass=glass, label=label, text=text,
                hit=(w, h))


def buttons(size):
    h, bevel, thick = SIZES[size]
    w = round(h * 2.5)
    lab = (h * 0.45, h * 0.22, w - h * 0.45, h * 0.78)      # flat face, where the label sits
    items = []
    for colour, (n, hv, ac) in BUTTON_COLOURS.items():
        for state, mat, th, dish in (("", n, thick, 0), ("-hover", hv, thick, 0),
                                     ("-active", ac, thick * 0.85, PRESS_DISH)):
            items.append(pill_item(f"btn-{colour}-{size}{state}", w, h, mat, bevel, th,
                                   label=lab, text="#ffffff", dish=dish))
    items.append(pill_item(f"btn-disabled-{size}", w, h, M.DISABLED, bevel, thick * 0.85,
                           label=lab, text="#f4f8fb"))
    return Sheet(f"btn-solid-{size}", items, max_width=w * 3 + 4 * 28)


def glass_buttons(size):
    h, bevel, thick = SIZES[size]
    w = round(h * 2.5)
    lab = (h * 0.45, h * 0.22, w - h * 0.45, h * 0.78)
    items = []
    for state, mat, th, dish in (("", M.CLEAR, thick, 0),
                                 ("-hover", dict(M.CLEAR, ambience=0.18, reflection=0.35), thick, 0),
                                 ("-active", dict(M.CLEAR, ambience=0.2), thick * 0.85, PRESS_DISH)):
        items.append(pill_item(f"btn-glass-{size}{state}", w, h, mat, bevel, th, glass=True,
                               label=lab, text="#0d2236", dish=dish))
    return Sheet(f"btn-glass-{size}", items, max_width=w * 2 + 3 * 36, gap=36)


def toggles():
    W, H = 56, 32

    def track(name, mat):
        return pill_item(name, W, H, mat, 10, 16, glass=True)

    def knob(name, mat, d=26):
        return Item(name, d, d, lambda st, x, y: st.orb(x, y, d, mat), margin=6)

    return Sheet("toggle", [track("toggle-track", M.TINT), track("toggle-track-on", M.TINT_GREEN),
                            knob("toggle-knob", M.PEARL), knob("toggle-knob-on", M.LIQUID)],
                 max_width=56 * 2 + 3 * 36, gap=36)


def checks():
    S = 26

    def box(name, inner=None, radius=7, bevel=7, thick=10):
        def draw(st, x, y):
            st.slab(x, y, S, S, radius, bevel, thick, M.TINT)
            if inner:
                inner(st, x, y)
        return Item(name, S, S, draw, glass=True, margin=6, hit=(S, S))

    def tick(st, x, y):
        st.slab(x + 2, y + 2, S - 4, S - 4, 0, 0, 10, M.LIQUID, z=-9, heights=shapes.tick())

    def dash(st, x, y):
        st.pill(x + 6, y + S / 2 - 3, S - 12, 6, M.LIQUID, thickness=6, z=-8)

    def dot(st, x, y):
        st.orb(x + 7, y + 7, 12, M.LIQUID_AQUA, z=-8)

    return Sheet("check", [box("check"), box("check-on", tick), box("check-mixed", dash),
                           box("radio", radius=13, bevel=9, thick=12),
                           box("radio-on", dot, radius=13, bevel=9, thick=12)],
                 max_width=5 * 26 + 6 * 34, gap=34)


def fields():
    W, H, R = 120, 44, 10

    def well(name, mat, glass=False):
        def draw(st, x, y):
            st.slab(x, y, W, H, R, 5, 12, mat, well=(0.45, 4))
        # 9-slice: corners hold radius + rim; the floor in between stretches cleanly
        return Item(name, W, H, draw, slice=(16, 16, 16, 16), glass=glass, hit=(W, H))

    return Sheet("field", [well("field", M.FIELD), well("field-focus", M.FIELD_FOCUS),
                           well("field.dark", M.FIELD_DARK), well("field-focus.dark", M.FIELD_DARK_FOCUS)])


def panels():
    W, H, R = 160, 120, 16

    def panel(name, mat, radius=R):
        def draw(st, x, y):
            st.slab(x, y, W, H, radius, 9, 10, mat)
        return Item(name, W, H, draw, slice=(radius + 10,) * 4, glass=True, margin=10)

    return Sheet("panel", [panel("panel", M.FROST), panel("panel.dark", M.SMOKE),
                           panel("card", M.FROST, 12), panel("card.dark", M.SMOKE, 12),
                           panel("card-hover", dict(M.FROST, ambience=0.32, reflection=0.22), 12),
                           panel("card-hover.dark", dict(M.SMOKE, ambience=0.4, reflection=0.28), 12)])


def tubes():
    def tube(name, w, h, mat, thick, glass):
        return pill_item(name, w, h, mat, h / 2, thick, glass=glass)

    return Sheet("tube", [tube("progress-tube", 160, 18, M.TINT, 16, True),
                          tube("progress-fill", 160, 12, M.LIQUID, 10, False),
                          tube("slider-rail", 160, 10, M.TINT, 8, True),
                          tube("slider-fill", 160, 6, M.LIQUID_AQUA, 5, False),
                          Item("slider-thumb", 24, 24, lambda st, x, y: st.orb(x, y, 24, M.PEARL), margin=6)])


def gems():
    items = []
    for k, mat in M.GEM.items():
        items.append(pill_item(f"badge-{k}", 60, 22, mat, 7, 10))
        items.append(Item(f"orb-{k}", 16, 16, (lambda m: lambda st, x, y: st.orb(x, y, 16, m))(mat), margin=5))
    return Sheet("gem", items)


ICON_SIZES = {24: dict(thick=5, margin=3, k=1.0), 16: dict(thick=3.5, margin=2, k=1.2)}


def icons(glyphs=None):
    """Embossed glyphs, one isolated render each, at both native sizes and both styles. Sprites
    are named icon-<size>-<style>-<glyph>; build.py packs them into atlases (dist/icons.css)."""
    import icons as I
    items = []
    for size, o in ICON_SIZES.items():
        for glyph in glyphs or I.GLYPHS:
            hm = I.heights(glyph, 128, o["k"])
            for style, mat in M.ICON.items():
                def draw(st, x, y, hm=hm, mat=mat, size=size, t=o["thick"]):
                    st.slab(x, y, size, size, 0, 0, t, mat, heights=hm)
                items.append(Item(f"icon-{size}-{style}-{glyph}", size, size, draw, margin=o["margin"]))
    return Sheet("icon", items)


def icon_buttons():
    """Round 44 px orb buttons for a single glyph (the glyph comes from the icon atlas)."""
    D, bevel, thick = 44, 22, 20
    items = []
    for colour, (n, hv, ac) in (("glass", (M.CLEAR, dict(M.CLEAR, ambience=0.18, reflection=0.35),
                                            dict(M.CLEAR, ambience=0.2))),
                                ("primary", BUTTON_COLOURS["primary"])):
        for state, mat, th, dish in (("", n, thick, 0), ("-hover", hv, thick, 0),
                                     ("-active", ac, thick * 0.85, PRESS_DISH)):
            it = pill_item(f"iconbtn-{colour}{state}", D, D, mat, bevel, th, glass=colour == "glass", dish=dish)
            it.slice = None
            items.append(it)
    return Sheet("iconbtn", items)


def segmented():
    """Segmented control / tabs: a recessed glass tray and the raised chip of the selected segment."""
    H = 40
    tray = Item("seg-tray", 160, H, lambda st, x, y: st.slab(x, y, 160, H, H / 2, 4, 12, M.TINT, well=(0.4, 4)),
                slice=(0, H / 2, 0, H / 2), glass=True, hit=(160, H))
    # selected = aqua gloss with white label (like a primary button); hover = a pearl chip
    chip = pill_item("seg-chip", 80, 32, M.AQUA, 10, 12, label=(14, 7, 66, 25), text="#ffffff")
    chip_on = pill_item("seg-chip-hover", 80, 32, M.PEARL, 10, 12, label=(14, 7, 66, 25), text="#0d2236")
    return Sheet("seg", [tray, chip, chip_on])


def tiles():
    """Choice cards (radio/checkbox as a big frosted tile) and the drop zone basin."""
    def tile(name, mat, w=140, h=90, r=14, well=None, thick=10, sl=None, bevel=None):
        def draw(st, x, y):
            st.slab(x, y, w, h, r, bevel or (9 if not well else 6), thick, mat, well=well)
        return Item(name, w, h, draw, slice=sl or (r + 10,) * 4, glass=True, margin=10)
    return Sheet("tile", [tile("choice-on", M.CHOICE), tile("choice-on.dark", M.CHOICE_DARK),
                          tile("drop", M.TINT, 200, 120, 20, well=(0.35, 10), thick=16, sl=(32,) * 4),
                          tile("drop-over", dict(M.TINT_GREEN, ambience=0.3), 200, 120, 20, well=(0.35, 10),
                               thick=16, sl=(32,) * 4),
                          tile("drop.dark", dict(M.CHOICE_DARK, ambience=0.22, transparency=0.55), 200, 120, 20,
                               well=(0.35, 10), thick=16, sl=(32,) * 4),
                          tile("drop-over.dark", M.DROP_DARK, 200, 120, 20, well=(0.35, 10), thick=16, sl=(32,) * 4),
                          tile("lens", M.CLEAR, 160, 120, 24, thick=18, sl=(36,) * 4, bevel=14)])


def rails():
    """Callout rail: a slim vertical gem bar per status colour (3-slice, vertical)."""
    W, H = 10, 64
    items = []
    for k, mat in M.GEM.items():
        def draw(st, x, y, mat=mat):
            st.slab(x, y, W, H, W / 2, W / 2, 8, mat)
        items.append(Item(f"rail-{k}", W, H, draw, slice=(W / 2, 0, W / 2, 0), margin=5))
    return Sheet("rail", items)


def windows():
    """Dialog window (large frosted glass, 9-slice), header bar, close and theme orbs."""
    def win(name, mat, w, h, r, thick=12, bevel=10):
        def draw(st, x, y):
            st.slab(x, y, w, h, r, bevel, thick, mat)
        return Item(name, w, h, draw, slice=(r + 12,) * 4, glass=True, margin=12)
    orb = lambda name, d, mat, m=5: Item(name, d, d, lambda st, x, y: st.orb(x, y, d, mat), margin=m, hit=(d, d))
    return [Sheet("win", [win("dialog", M.FROST, 320, 220, 20), win("dialog.dark", M.SMOKE, 320, 220, 20),
                          win("bar", M.FROST, 240, 56, 14, 10, 8), win("bar.dark", M.SMOKE, 240, 56, 14, 10, 8)]),
            Sheet("orbs", [orb("close", 24, M.RED), orb("close-hover", 24, dict(M.RED, ambience=0.55)),
                           orb("toggle-knob-sun", 26, M.SUN, 6), orb("toggle-knob-moon", 26, M.MOON, 6),
                           orb("compare-grip", 36, M.PEARL, 6)])]


def brand():
    """The logo mark: an "air stone", a flattened aqua pebble tilted a little, 36 px."""
    def pebble(name, mat, glass=False):
        def draw(st, x, y):
            st.c.add("sphere", st.p(x + 18, y + 18, 0), (0, 0, -18), (34, 24, 20), mat)
        return Item(name, 36, 36, draw, glass=glass, margin=6, hit=(36, 36))
    return Sheet("logo", [pebble("logo-aqua", M.AQUA), pebble("logo-liquid", M.LIQUID_AQUA)])


SPIN_FRAMES = 8


def spinner():
    """8 frames of a ring of 8 orbs: one lit aqua orb with a fading trail travels round. Every
    frame is a separate render, so the lighting stays fixed (rotating one image would spin the
    highlights)."""
    D, n, ro, d = 32, 8, 11.0, 6.5
    import math
    items = []
    for f in range(SPIN_FRAMES):
        def draw(st, x, y, f=f):
            for i in range(n):
                a = 2 * math.pi * i / n - math.pi / 2
                age = (f - i) % n
                mat = M.LIQUID_AQUA if age == 0 else M.AQUA_MID if age == 1 else M.DIM
                st.orb(x + D / 2 + ro * math.cos(a) - d / 2, y + D / 2 + ro * math.sin(a) - d / 2, d, mat)
        items.append(Item(f"spin-{f}", D, D, draw, margin=3))
    return Sheet("spin", items)


def display(chars=None, thick=None, tag="", n=None):
    """Aerolith Display: one isolated gel letter per sprite, per material (typeface.py).
    Named type-<material>-<codepoint hex>; fontbuild.py packs them into colour fonts."""
    import typeface as T
    import concurrent.futures as cf
    chars = chars or T.CHARSET
    with cf.ProcessPoolExecutor(6) as ex:           # ~11 s per glyph at N=512
        hms = dict(zip(chars, ex.map(T.heights, chars, [n or T.N] * len(chars))))
    items = []
    for ch in chars:
        hm = hms[ch]
        for mat_name, mat in M.TYPE.items():
            def draw(st, x, y, hm=hm, mat=mat, t=thick or T.THICK):
                st.slab(x, y, T.CELL, T.CELL, 0, 0, t, mat, heights=hm)
            items.append(Item(f"type{tag}-{mat_name}-{ord(ch):04x}", T.CELL, T.CELL, draw,
                              margin=T.MARGIN, glass=mat_name == "glass"))
    return Sheet("type" + tag, items)


def sheets():
    return [s.layout() for s in (buttons("s"), buttons("m"), buttons("l"), glass_buttons("s"), glass_buttons("m"),
                                       glass_buttons("l"), toggles(), checks(),
                                       fields(), panels(), tubes(), gems(), icons(),
                                       icon_buttons(), segmented(), tiles(), rails(), *windows(), spinner(), brand(), display())]
