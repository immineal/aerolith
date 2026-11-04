"""Pack the Bryce-rendered display glyphs into colour fonts.

sprite(ch, dpr) -> (png path, outset (top, right, bottom, left) in CSS px) for each glyph.

Per material two files, because no single colour-font format works everywhere:
  *.svg.woff2   OpenType-SVG, each glyph an <image> with the PNG (Firefox, Safari)
  *.bmp.woff2   sbix bitmap strike (Chromium)
Both keep Istok's outlines (heavier, renamed) as the fallback and for metrics, so titles stay
real text. The CSS lists the files with tech(), and a browser downloads only the one it draws.

Font licence: derived from Istok Web (SIL OFL 1.1, Reserved Font Name "Istok"), so the result is
OFL too and must not be called Istok."""
from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import Callable

from fontTools.subset import Options, Subsetter
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables.sbixGlyph import Glyph as SbixGlyph
from fontTools.ttLib.tables.sbixStrike import Strike as SbixStrike
from PIL import Image

import typeface as T

FAMILY = "Aerolith Display"
COPYRIGHT = ("Copyright (c) 2008-2014, Andrey V. Panov (panov@canopus.iacp.dvo.ru), with Reserved Font "
             "Name Istok. Copyright (c) 2026, Immineal (Bryce-rendered colour glyphs).")


def base_font(chars: str, style: str) -> TTFont:
    """Istok Web Bold subset to `chars`, sidebearings widened by the dilation, renamed."""
    f = TTFont(str(T.SRC))
    opt = Options()
    opt.layout_features = ["kern", "liga"]
    opt.name_IDs = []
    opt.notdef_outline = True
    sub = Subsetter(opt)
    sub.populate(unicodes=[ord(c) for c in chars + " "])
    sub.subset(f)
    upm = f["head"].unitsPerEm
    g = round(T.grow_em() * upm)
    hmtx = f["hmtx"]
    glyf = f["glyf"]
    for name in f.getGlyphOrder():         # simple glyphs first: composites reference them
        gl = glyf[name]
        if gl.numberOfContours > 0:        # shift the outline right by g, so it matches the sprite
            gl.coordinates.translate((g, 0))
    for name in f.getGlyphOrder():
        adv, _ = hmtx[name]
        gl = glyf[name]
        gl.recalcBounds(glyf)
        hmtx[name] = (adv + 2 * g, getattr(gl, "xMin", 0))
    f["hhea"].advanceWidthMax += 2 * g
    full = f"{FAMILY} {style.title()}"
    ps = f"AerolithDisplay-{style.title()}"
    name = f["name"]
    name.names = []
    for nid, val in ((0, COPYRIGHT), (1, full), (2, "Regular"), (3, f"{ps};1.0"), (4, full), (5, "Version 1.000"),
                     (6, ps), (13, "This Font Software is licensed under the SIL Open Font License, Version 1.1."),
                     (14, "https://openfontlicense.org")):
        name.setName(val, nid, 3, 1, 0x409)
    return f


def small_png(path: Path) -> bytes:
    """Palette PNG at 90-100 quality: indistinguishable on the gel gradients, about 40 % of the
    size. Falls back to the original when pngquant is missing or can't reach the floor."""
    import subprocess
    raw = path.read_bytes()
    try:
        r = subprocess.run(["pngquant", "--quality=90-100", "--speed", "1", "--strip", "-"],
                           input=raw, capture_output=True, check=False)
    except FileNotFoundError:
        return raw
    return r.stdout if r.returncode == 0 and r.stdout and len(r.stdout) < len(raw) else raw


def placement(ch: str, outset, upm: int):
    """Image box in font units relative to the glyph origin (y up): left x, top y, width, height.
    The sprite's shape box is the CELL square, centred on Istok's ink box (shifted by the
    dilation), its top BASE * CELL above the baseline; `outset` (top, right, bottom, left, CSS px)
    is how far the exported image reaches beyond it (export trims transparent margins)."""
    ot, orr, ob, ol = outset
    px2u = upm / T.em_px()                              # CSS px at 1x -> font units
    cx = (T.grow_em() + T.glyph_offset_em(ch)) * upm
    left = cx - (T.CELL / 2 + ol) * px2u
    top = (T.BASE * T.CELL + ot) * px2u
    return left, top, (T.CELL + ol + orr) * px2u, (T.CELL + ot + ob) * px2u


def build(style: str, sprite: Callable[[str, int], tuple], out_dir: Path, chars: str = T.CHARSET,
          svg_dpr: int = 2, bmp_dpr: int = 2) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    sizes = {}
    # --- OpenType-SVG
    f = base_font(chars, style)
    upm = f["head"].unitsPerEm
    cmap = f.getBestCmap()
    order = f.getGlyphOrder()
    docs = []
    for ch in chars:
        gname = cmap[ord(ch)]
        gid = order.index(gname)
        path, outset = sprite(ch, svg_dpr)
        png = small_png(path)
        x, top, wu, hu = placement(ch, outset, upm)
        b64 = base64.b64encode(png).decode()
        docs.append((f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">'
                     f'<image id="glyph{gid}" x="{x:.1f}" y="{-top:.1f}" width="{wu:.1f}" height="{hu:.1f}" '
                     f'preserveAspectRatio="none" xlink:href="data:image/png;base64,{b64}" href="data:image/png;base64,{b64}"/>'
                     f'</svg>', gid, gid))
    docs.sort(key=lambda d: d[1])
    svg = newTable("SVG ")
    svg.docList = docs
    f["SVG "] = svg
    p = out_dir / f"aerolith-display-{style}.svg.woff2"
    f.flavor = "woff2"
    f.save(str(p))
    sizes["svg"] = p.stat().st_size
    # --- sbix
    f = base_font(chars, style)
    cmap = f.getBestCmap()
    sbix = newTable("sbix")
    sbix.version = 1
    sbix.flags = 1
    sbix.strikes = {}
    ppem = round(T.em_px() * bmp_dpr)
    st = SbixStrike(ppem=ppem, resolution=72)
    for ch in chars:
        gname = cmap[ord(ch)]
        path, outset = sprite(ch, bmp_dpr)
        png = small_png(path)
        w, h = Image.open(io.BytesIO(png)).size
        x, top, wu, hu = placement(ch, outset, upm)
        k = ppem / upm
        # FreeType and CoreText place the image relative to the outline's lower left corner
        # (xMin, yMin), not the glyph origin, so take that back out
        gl = f["glyf"][gname]
        xmin, ymin = getattr(gl, "xMin", 0), getattr(gl, "yMin", 0)
        st.glyphs[gname] = SbixGlyph(glyphName=gname, graphicType="png ", originOffsetX=round((x - xmin) * k),
                                     originOffsetY=round((top - hu - ymin) * k), imageData=png)
    sbix.strikes[ppem] = st
    f["sbix"] = sbix
    p = out_dir / f"aerolith-display-{style}.bmp.woff2"
    f.flavor = "woff2"
    f.save(str(p))
    sizes["bmp"] = p.stat().st_size
    return sizes
