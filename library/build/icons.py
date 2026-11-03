"""The Aerolith glyph set: vector drawings in unit coordinates (0..1, y down), embossed into
lattice height maps (see shapes.emboss). Line glyphs use round caps and a bevel of half the
stroke, so strokes become rounded tubes; filled glyphs get a softer shoulder, and cut-outs
(the "!" in warning, the hole in lock) are drawn in black over the fill."""
from __future__ import annotations

import math

from PIL import ImageFont

import shapes

W = 0.115                    # standard stroke width (fraction of the icon box)
FONT = "/usr/share/fonts/truetype/DejaVuSans-Bold.ttf"


class Pen:
    def __init__(self, dr, S, k=1.0):
        self.d, self.S, self.k = dr, S, k       # k: stroke-width factor (bolder at small sizes)

    def p(self, pts):
        return [(x * self.S, y * self.S) for x, y in pts]

    def line(self, pts, w=W, fill=255):
        """Round-capped stroke: discs stamped densely along the polyline (PIL's wide polylines
        leave gaps at sharp or many-segment joints)."""
        P = self.p(pts)
        r = w * self.k * self.S / 2
        step = max(r / 4, 0.5)
        for (x0, y0), (x1, y1) in zip(P, P[1:] or P):
            n = max(1, int(math.hypot(x1 - x0, y1 - y0) / step))
            for i in range(n + 1):
                x, y = x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n
                self.d.ellipse([x - r, y - r, x + r, y + r], fill=fill)

    def circle(self, cx, cy, r, w=None, fill=255):
        S = self.S
        box = [(cx - r) * S, (cy - r) * S, (cx + r) * S, (cy + r) * S]
        if w is None:
            self.d.ellipse(box, fill=fill)
        else:
            self.d.ellipse(box, outline=fill, width=int(round(w * self.k * S)))

    def arc(self, cx, cy, r, a0, a1, w=W, fill=255, steps=64):
        """Arc from angle a0 to a1 (degrees, 0 = +x, counter-clockwise on screen = negative y)."""
        pts = [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / steps)),
                cy - r * math.sin(math.radians(a0 + (a1 - a0) * i / steps))) for i in range(steps + 1)]
        self.line(pts, w, fill)
        return pts

    def poly(self, pts, fill=255):
        self.d.polygon(self.p(pts), fill=fill)

    def rrect(self, x0, y0, x1, y1, r, w=None, fill=255):
        S = self.S
        box = [x0 * S, y0 * S, x1 * S, y1 * S]
        if w is None:
            self.d.rounded_rectangle(box, radius=r * S, fill=fill)
        else:
            self.d.rounded_rectangle(box, radius=r * S, outline=fill, width=int(round(w * self.k * S)))

    def text(self, s, cx, cy, size, fill=0):
        f = ImageFont.truetype(FONT, int(size * self.S))
        self.d.text((cx * self.S, cy * self.S), s, font=f, fill=fill, anchor="mm")

    def arc_arrow(self, cx, cy, r, a0, a1, size=0.17, w=W):
        """Arc a0 -> a1 (degrees, y up) with an arrowhead at the a1 end, along the tangent."""
        self.arc(cx, cy, r, a0, a1, w)
        t = math.radians(a1)
        sgn = 1 if a1 > a0 else -1
        tip = (cx + r * math.cos(t), cy - r * math.sin(t))
        self.head(tip, a1 + sgn * 90, size, w)

    def head(self, tip, direction, size=0.2, w=W):
        """Open arrowhead (chevron) at `tip` pointing along `direction` (degrees)."""
        tx, ty = tip
        a = math.radians(direction)
        pts = []
        for s in (+1, -1):
            b = a + math.pi + s * math.radians(42)
            pts.append((tx + size * math.cos(b), ty - size * math.sin(b)))
        self.line([pts[0], tip, pts[1]], w)


def heart_pts(scale=1.0, cy=0.53):
    pts = []
    for i in range(240):
        t = 2 * math.pi * i / 240
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        pts.append((0.5 + x / 36 * scale, cy - y / 36 * scale))
    return pts


# ---------------------------------------------------------------- glyphs: name -> (draw(pen), kind)
# kind "line": tube strokes; "fill": solid shape with soft shoulder
def g_heart(P):
    P.poly(heart_pts(1.0))
def g_heart_outline(P):
    P.poly(heart_pts(1.0)); P.poly(heart_pts(0.62, 0.515), fill=0)
def g_close(P):
    P.line([(0.27, 0.27), (0.73, 0.73)], 0.13); P.line([(0.73, 0.27), (0.27, 0.73)], 0.13)
def g_menu(P):
    for y in (0.3, 0.5, 0.7):
        P.line([(0.24, y), (0.76, y)])
def g_arrow_left(P):
    P.line([(0.78, 0.5), (0.25, 0.5)]); P.head((0.24, 0.5), 180, 0.24)
def g_arrow_right(P):
    P.line([(0.22, 0.5), (0.75, 0.5)]); P.head((0.76, 0.5), 0, 0.24)
def g_chevron_down(P):
    P.line([(0.28, 0.4), (0.5, 0.62), (0.72, 0.4)], 0.13)
def g_swap(P):
    P.line([(0.22, 0.36), (0.74, 0.36)], 0.1); P.head((0.76, 0.36), 0, 0.16, 0.1)
    P.line([(0.78, 0.64), (0.26, 0.64)], 0.1); P.head((0.24, 0.64), 180, 0.16, 0.1)
def g_play(P):
    P.poly([(0.33, 0.22), (0.33, 0.78), (0.8, 0.5)])
def g_help(P):
    P.circle(0.5, 0.5, 0.4); P.text("?", 0.5, 0.52, 0.55)
def g_info(P):
    P.circle(0.5, 0.5, 0.4); P.text("i", 0.5, 0.52, 0.55)
def g_error(P):
    P.circle(0.5, 0.5, 0.4)
    P.line([(0.37, 0.37), (0.63, 0.63)], 0.1, fill=0); P.line([(0.63, 0.37), (0.37, 0.63)], 0.1, fill=0)
def g_warning(P):
    P.poly([(0.5, 0.12), (0.9, 0.84), (0.1, 0.84)]); P.text("!", 0.5, 0.6, 0.48)
def g_gear(P):
    pts, teeth = [], 8
    for i in range(teeth * 4):
        a = 2 * math.pi * i / (teeth * 4) + math.pi / (teeth * 4)
        r = 0.42 if (i % 4) in (0, 1) else 0.31
        pts.append((0.5 + r * math.cos(a), 0.5 + r * math.sin(a)))
    P.poly(pts); P.circle(0.5, 0.5, 0.13, fill=0)
def g_undo(P):
    P.arc_arrow(0.5, 0.54, 0.26, -40, 170)
def g_redo(P):
    P.arc_arrow(0.5, 0.54, 0.26, 220, 10)
def g_plus(P):
    P.line([(0.24, 0.5), (0.76, 0.5)], 0.13); P.line([(0.5, 0.24), (0.5, 0.76)], 0.13)
def g_minus(P):
    P.line([(0.24, 0.5), (0.76, 0.5)], 0.13)
def g_fit(P):
    for sx, sy in ((0, 0), (1, 0), (0, 1), (1, 1)):
        x = 0.22 if sx == 0 else 0.78
        y = 0.22 if sy == 0 else 0.78
        dx = 0.18 if sx == 0 else -0.18
        dy = 0.18 if sy == 0 else -0.18
        P.line([(x + dx, y), (x, y), (x, y + dy)], 0.1)
def g_search(P):
    P.circle(0.43, 0.43, 0.2, w=0.1); P.line([(0.59, 0.59), (0.79, 0.79)], 0.14)
def g_download(P):
    P.line([(0.5, 0.18), (0.5, 0.6)]); P.head((0.5, 0.62), -90, 0.2); P.line([(0.22, 0.82), (0.78, 0.82)])
def g_upload(P):
    P.line([(0.5, 0.64), (0.5, 0.22)]); P.head((0.5, 0.2), 90, 0.2); P.line([(0.22, 0.82), (0.78, 0.82)])
def g_copy(P):
    P.rrect(0.32, 0.3, 0.8, 0.84, 0.07, w=0.09)
    P.line([(0.2, 0.66), (0.2, 0.2), (0.62, 0.2)], 0.09)
def g_check(P):
    P.line([(0.2, 0.52), (0.42, 0.74), (0.8, 0.28)], 0.14)
def _page(P):
    P.poly([(0.22, 0.12), (0.6, 0.12), (0.8, 0.32), (0.8, 0.88), (0.22, 0.88)])
def g_file(P):
    _page(P); P.line([(0.6, 0.14), (0.6, 0.32), (0.78, 0.32)], 0.05, fill=0)
def g_pdf(P):
    _page(P); P.text("PDF", 0.51, 0.62, 0.26)
def g_text(P):
    for y, x1 in ((0.28, 0.78), (0.44, 0.78), (0.6, 0.78), (0.76, 0.56)):
        P.line([(0.22, y), (x1, y)], 0.1)
def g_image(P):
    P.rrect(0.14, 0.2, 0.86, 0.8, 0.08)
    P.rrect(0.22, 0.28, 0.78, 0.72, 0.04, fill=0)
    P.poly([(0.24, 0.7), (0.44, 0.44), (0.58, 0.6), (0.66, 0.5), (0.76, 0.7)])
    P.circle(0.66, 0.38, 0.06)
def g_code(P):
    P.line([(0.32, 0.3), (0.14, 0.5), (0.32, 0.7)], 0.1)
    P.line([(0.68, 0.3), (0.86, 0.5), (0.68, 0.7)], 0.1)
    P.line([(0.56, 0.22), (0.44, 0.78)], 0.09)
def g_clock(P):
    P.circle(0.5, 0.5, 0.36, w=0.1); P.line([(0.5, 0.3), (0.5, 0.52), (0.65, 0.6)], 0.09)
def g_colour(P):
    pts = [(0.5, 0.12)]
    for i in range(0, 181):
        a = math.radians(-10 + i * (200 / 180))
        pts.append((0.5 + 0.27 * math.cos(a), 0.6 + 0.27 * math.sin(a)))
    P.poly(pts)
def g_pin(P):
    pts = []
    for i in range(0, 181):
        a = math.radians(-58 + i * (296 / 180))
        pts.append((0.5 + 0.28 * math.cos(a), 0.4 - 0.28 * math.sin(a)))
    pts.append((0.5, 0.9))
    P.poly(pts); P.circle(0.5, 0.4, 0.1, fill=0)
def g_lock(P):
    P.arc(0.5, 0.42, 0.17, 0, 180, 0.1)
    P.line([(0.33, 0.42), (0.33, 0.5)], 0.1); P.line([(0.67, 0.42), (0.67, 0.5)], 0.1)
    P.rrect(0.22, 0.46, 0.78, 0.86, 0.07)
    P.circle(0.5, 0.62, 0.06, fill=0); P.line([(0.5, 0.64), (0.5, 0.74)], 0.06, fill=0)
def g_sun(P):
    P.circle(0.5, 0.5, 0.18)
    for i in range(8):
        a = math.radians(i * 45)
        P.line([(0.5 + 0.28 * math.cos(a), 0.5 + 0.28 * math.sin(a)),
                (0.5 + 0.38 * math.cos(a), 0.5 + 0.38 * math.sin(a))], 0.08)
def g_moon(P):
    P.circle(0.5, 0.5, 0.34); P.circle(0.66, 0.38, 0.28, fill=0)


GLYPHS = {
    "heart": (g_heart, "fill"), "heart-outline": (g_heart_outline, "fill"), "close": (g_close, "line"),
    "menu": (g_menu, "line"), "arrow-left": (g_arrow_left, "line"), "arrow-right": (g_arrow_right, "line"),
    "chevron-down": (g_chevron_down, "line"), "swap": (g_swap, "line"), "play": (g_play, "fill"),
    "help": (g_help, "fill"), "info": (g_info, "fill"), "error": (g_error, "fill"),
    "warning": (g_warning, "fill"), "gear": (g_gear, "fill"), "undo": (g_undo, "line"),
    "redo": (g_redo, "line"), "plus": (g_plus, "line"), "minus": (g_minus, "line"), "fit": (g_fit, "line"),
    "search": (g_search, "line"), "download": (g_download, "line"), "upload": (g_upload, "line"),
    "copy": (g_copy, "line"), "check": (g_check, "line"), "file": (g_file, "fill"), "pdf": (g_pdf, "fill"),
    "text": (g_text, "line"), "image": (g_image, "fill"), "code": (g_code, "line"), "clock": (g_clock, "line"),
    "colour": (g_colour, "fill"), "pin": (g_pin, "fill"), "lock": (g_lock, "fill"), "sun": (g_sun, "fill"),
    "moon": (g_moon, "fill"),
}


def heights(name, n=256, k=1.0):
    fn, kind = GLYPHS[name]
    bevel = W * k / 2 * 0.95 if kind == "line" else 0.06
    return shapes.emboss(lambda dr, S: fn(Pen(dr, S, k)), bevel=bevel,
                         profile="pillow" if kind == "line" else "ease", n=n)


def mask_preview(path, n=96):
    """Flat contact sheet of all masks (fast check of the drawings, before any rendering)."""
    from PIL import Image, ImageDraw
    names = list(GLYPHS)
    cols = 9
    sheet = Image.new("L", (cols * (n + 8), ((len(names) + cols - 1) // cols) * (n + 8)), 40)
    for i, nm in enumerate(names):
        h = heights(nm, n)
        im = Image.fromarray((h * 255).astype("uint8"))
        sheet.paste(im, ((i % cols) * (n + 8) + 4, (i // cols) * (n + 8) + 4))
    sheet.save(path)
