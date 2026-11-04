"""Aerolith Text: Selawik with a kern table.

Selawik 1.01 ships without any pair kerning (its GPOS has only mark/mkmk). Two things then go wrong:
r-f and t-v almost touch, and capitals with open shapes (T, F, L, P, Y ...) leave holes. This module
measures every Latin letter pair from the outlines and corrects only the outliers:

  * open pairs are tightened toward the font's own median gap (area-based, tolerance TOL);
  * pairs whose outlines come closer than MIN_CLEAR are pushed apart (r-f, t-v, T-ï, f-ï ...);
  * diagonal capitals the area measure under-weights get the textbook values in OVERRIDES.

Ordinary lowercase spacing stays exactly as the designer drew it. The result is merged into the
existing GPOS as a `kern` feature (mark/mkmk survive) and the font is renamed "Aerolith Text",
because the OFL reserves the name "Selawik".

    python3 kern.py report [weight]     # numbers for the demo words and the biggest pairs
    python3 kern.py write  <out_dir>    # four woff2 files, aerolith-text-<weight>.woff2

Units are font units (2048 per em). Strength, tolerance and clamps are below; change them here only.
"""
import sys
import unicodedata
from pathlib import Path

import numpy as np
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.pens.basePen import BasePen
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw

FONTS = Path(__file__).resolve().parent / "fonts"
WEIGHTS = {  # style -> (source file, subfamily name)
    "light": ("selawkl.woff2", "Light"),
    "regular": ("selawk.woff2", "Regular"),
    "semibold": ("selawksb.woff2", "SemiBold"),
    "bold": ("selawkb.woff2", "Bold"),
}
FAMILY = "Aerolith Text"

STRENGTH = 0.6      # share of the excess over the median that is corrected
TOL = 45            # excess inside this band stays as the designer drew it
CLAMP = 140         # no kern is larger than this
MIN_KERN = 12       # smaller values are dropped
SNAP = 4
MIN_CLEAR = 90      # closest approach of two outlines after kerning (0.7 px at 16 px)
DEPTH = 0.35        # an open shape (r, c, F, T ...) counts only this far behind its tip, as a share of the zone height

# Textbook values for pairs the area measure under-weights (diagonal capitals, caps before a full
# stop). The stronger of measured and override wins.
OVERRIDES = {
    "AV": -90, "AW": -60, "AY": -100, "VA": -90, "WA": -60, "YA": -100,
    "Va": -60, "Ve": -60, "Vo": -60, "Wa": -40, "We": -40, "Wo": -40, "Ya": -80, "Ye": -80, "Yo": -80,
    "Ay": -40, "Av": -40, "Aw": -30,
    "T.": -60, "T,": -60, "P.": -60, "P,": -60, "F.": -50, "F,": -50, "Y.": -60, "Y,": -60,
    "V.": -50, "V,": -50, "W.": -40, "W,": -40, "r.": -20, "r,": -20, "y.": -30, "y,": -30,
}

K = 4               # one raster pixel = K font units
YMIN, YMAX = -700, 2400
ROWS = (YMAX - YMIN) // K


class _Flat(BasePen):
    """Outline -> list of polygons (curves flattened)."""

    def __init__(self, gs):
        super().__init__(gs)
        self.polys, self.cur = [], None

    def _moveTo(self, p):
        self.cur = [p]

    def _lineTo(self, p):
        self.cur.append(p)

    def _qCurveToOne(self, a, b):
        p0 = self.cur[-1]
        for t in np.linspace(0, 1, 9)[1:]:
            self.cur.append(tuple((1 - t) ** 2 * p0[i] + 2 * (1 - t) * t * a[i] + t * t * b[i] for i in (0, 1)))

    def _curveToOne(self, a, b, c):
        p0 = self.cur[-1]
        for t in np.linspace(0, 1, 13)[1:]:
            self.cur.append(tuple((1 - t) ** 3 * p0[i] + 3 * (1 - t) ** 2 * t * a[i] + 3 * (1 - t) * t * t * b[i]
                                  + t ** 3 * c[i] for i in (0, 1)))

    def _closePath(self):
        self.polys.append(self.cur)
        self.cur = None

    _endPath = _closePath


def _profiles(gs, glyph, adv):
    """Per raster row: leftmost ink x and right bearing (adv - rightmost ink x); NaN where empty."""
    pen = _Flat(gs)
    gs[glyph].draw(pen)
    if not pen.polys:
        return None
    w = (adv + 800) // K + 8
    img = np.zeros((ROWS, w), bool)
    for poly in pen.polys:     # even-odd by XOR: counters and overlapping composites are fine here
        m = Image.new("1", (w, ROWS), 0)
        ImageDraw.Draw(m).polygon([((x + 400) / K, (YMAX - y) / K) for x, y in poly], fill=1)
        img ^= np.array(m)
    left = np.full(ROWS, np.nan)
    right = np.full(ROWS, np.nan)
    for r in range(ROWS):
        xs = np.nonzero(img[r])[0]
        if len(xs):
            left[r] = xs[0] * K - 400
            right[r] = adv - ((xs[-1] + 1) * K - 400)
    return left, right


def _clamped(arr, rows, depth):
    sel = arr[rows]
    if np.all(np.isnan(sel)):
        return None
    ext = np.nanmin(sel)
    return np.where(np.isnan(sel), ext + depth, np.minimum(sel, ext + depth))


def base(ch):
    return unicodedata.normalize("NFD", ch)[0]


def charset(font):
    """Glyphs to kern: ASCII letters and digits with their accented forms, as {char: glyphname}."""
    out = {}
    for cp, g in font.getBestCmap().items():
        ch = chr(cp)
        b = base(ch)
        if cp < 0x250 and b.isascii() and (b.isalpha() or b.isdigit()):
            out[ch] = g
    return out


def kind(ch):
    b = base(ch)
    return "d" if b.isdigit() else ("u" if b.isupper() else "l")


def compute(font):
    """({(left char, right char): kern}, {kind pair: target gap}) for every pair with a non-zero kern."""
    gs, hm, cm = font.getGlyphSet(), font["hmtx"], font.getBestCmap()
    os2 = font["OS/2"]
    xh, cap = os2.sxHeight, os2.sCapHeight
    names = dict(charset(font))
    for c in {ch for pair in OVERRIDES for ch in pair}:
        names.setdefault(c, cm[ord(c)])
    prof = {}
    for ch, g in names.items():
        p = _profiles(gs, g, hm[g][0])
        if p:
            prof[ch] = p
    chars = [c for c in charset(font) if c in prof]
    ys = YMAX - np.arange(ROWS) * K            # y of each raster row
    zones = {"x": (np.nonzero((ys >= 0) & (ys <= xh))[0], DEPTH * xh),
             "c": (np.nonzero((ys >= 0) & (ys <= cap))[0], DEPTH * cap)}
    cl, cr = {}, {}                            # clamped profiles per zone
    for z, (rows, depth) in zones.items():
        for ch in chars:
            a, b = _clamped(prof[ch][0], rows, depth), _clamped(prof[ch][1], rows, depth)
            if a is not None and b is not None:
                cl[z, ch], cr[z, ch] = a, b
    kinds = {c: kind(c) for c in chars}

    def gap(a, b):
        z = "x" if kinds[a] == "l" and kinds[b] == "l" else "c"
        if (z, a) not in cl or (z, b) not in cl:
            return None
        return float(np.mean(cr[z, a] + cl[z, b]))

    def clearance(a, b):
        both = ~np.isnan(prof[a][1]) & ~np.isnan(prof[b][0])
        return float(np.min((prof[a][1] + prof[b][0])[both])) if both.any() else 1e9

    # target per kind combination = median of the plain ASCII pairs of that combination
    ascii_ = [c for c in chars if c.isascii()]
    target = {}
    for ka in "lud":
        for kb in "lud":
            if (ka == "d") != (kb == "d"):
                continue                       # no digit/letter kerning
            vals = [g for a in ascii_ for b in ascii_
                    if kinds[a] == ka and kinds[b] == kb and (g := gap(a, b)) is not None]
            if vals:
                target[ka, kb] = float(np.median(vals))
    out = {}
    for a in chars:
        for b in chars:
            t = target.get((kinds[a], kinds[b]))
            g = gap(a, b)
            if t is None or g is None:
                continue
            dev = g - t
            # area correction only where it is meaningful: not lower-then-capital (camelCase) and not J,
            # whose descender distorts the window; tighten open pairs, never loosen by area
            area_ok = not (kinds[a] == "l" and kinds[b] == "u") and "J" not in (base(a), base(b))
            k = -STRENGTH * (dev - TOL) if dev > TOL and area_ok else 0.0
            c = clearance(a, b)
            if c + k < MIN_CLEAR:
                k = MIN_CLEAR - c                                   # but keep the outlines apart
            k = int(round(max(-CLAMP, min(CLAMP, k)) / SNAP) * SNAP)
            if abs(k) >= MIN_KERN:
                out[a, b] = k
    for pair, k in OVERRIDES.items():
        a, b = pair
        if a in prof and b in prof:
            out[a, b] = min(out.get((a, b), 0), k)
    return out, target


def _ref(c, members):
    """feature-file reference for a character: its base-letter class, or the bare glyph (punctuation)."""
    return f"@K_{ord(c):04x}" if c in members else None


def fea(font, pairs):
    """Feature code: one class per base letter (accented forms inherit), glyph pairs for exceptions."""
    cm = font.getBestCmap()
    allc = charset(font)
    members = {}
    for ch, g in allc.items():
        members.setdefault(base(ch), []).append(g)
    classes = {p: k for p, k in pairs.items() if p[0] in members and p[1] in members
               and base(p[0]) == p[0] and base(p[1]) == p[1]}
    others = {p: k for p, k in pairs.items() if p not in classes}   # accented pairs, punctuation
    lines = [f"@K_{ord(b):04x} = [{' '.join(gl)}];" for b, gl in sorted(members.items())]

    def ref(c):
        return f"@K_{ord(c):04x}" if c in members and base(c) == c else cm[ord(c)]

    exc = {}
    for (a, b), k in others.items():
        if a in allc and b in allc and classes.get((base(a), base(b)), 0) == k:
            continue
        exc[a, b] = k
    # an accented pair without its own kern must not inherit its base letter's: list an explicit zero
    for (a, b), k in classes.items():
        for ca in (c for c in allc if base(c) == a):
            for cb in (c for c in allc if base(c) == b):
                if (ca, cb) != (a, b) and (ca, cb) not in pairs:
                    exc[ca, cb] = 0
    lines.append("feature kern {")
    for (a, b), k in sorted(exc.items()):
        ga = allc.get(a) or cm[ord(a)]
        gb = allc.get(b) or cm[ord(b)]
        lines.append(f"  pos {ga} {gb} {k};")
    for (a, b), k in sorted(classes.items()):
        lines.append(f"  pos {ref(a)} {ref(b)} {k};")
    lines.append("} kern;")
    return "\n".join(lines)


def add_kern(font, pairs):
    """Build the kern lookups with feaLib on a scratch font, then graft them onto the real GPOS."""
    tmp = TTFont()
    tmp.setGlyphOrder(font.getGlyphOrder())
    addOpenTypeFeaturesFromString(tmp, fea(font, pairs), tables=["GPOS"])
    new = tmp["GPOS"].table
    og = font["GPOS"].table
    first = len(og.LookupList.Lookup)
    og.LookupList.Lookup.extend(new.LookupList.Lookup)
    og.LookupList.LookupCount = len(og.LookupList.Lookup)
    kern_fr = [fr for fr in new.FeatureList.FeatureRecord if fr.FeatureTag == "kern"][0]
    kern_fr.Feature.LookupListIndex = [i + first for i in kern_fr.Feature.LookupListIndex]
    og.FeatureList.FeatureRecord.insert(0, kern_fr)    # 'kern' sorts before 'mark'
    og.FeatureList.FeatureCount = len(og.FeatureList.FeatureRecord)
    for sr in og.ScriptList.ScriptRecord:
        langs = [sr.Script.DefaultLangSys] if sr.Script.DefaultLangSys else []
        langs += [ls.LangSys for ls in sr.Script.LangSysRecord]
        for ls in langs:
            ls.FeatureIndex = [0] + [i + 1 for i in ls.FeatureIndex]
            ls.FeatureCount = len(ls.FeatureIndex)


def rename(font, style):
    sub = WEIGHTS[style][1]
    ribbi = sub in ("Regular", "Bold")
    full = f"{FAMILY} {sub}"
    ps = f"{FAMILY.replace(' ', '')}-{sub}"
    n = font["name"]
    for rec in list(n.names):
        if rec.nameID in (1, 2, 3, 4, 5, 6, 10, 16, 17, 21, 22):
            n.removeNames(nameID=rec.nameID)
    for pid, eid, lid in ((3, 1, 0x409), (1, 0, 0)):
        n.setName(FAMILY if ribbi else full, 1, pid, eid, lid)
        n.setName(sub if ribbi else "Regular", 2, pid, eid, lid)
        n.setName(f"1.01;Aerolith;{ps}", 3, pid, eid, lid)
        n.setName(full, 4, pid, eid, lid)
        n.setName("Version 1.01; kerned by Aerolith", 5, pid, eid, lid)
        n.setName(ps, 6, pid, eid, lid)
        n.setName("Derived from Selawik by Microsoft (SIL OFL 1.1): kern table added and renamed, as the OFL "
                  "reserves the original name.", 10, pid, eid, lid)
        if not ribbi:
            n.setName(FAMILY, 16, 3, 1, 0x409)
            n.setName(sub, 17, 3, 1, 0x409)


def make(style, out_path):
    src = WEIGHTS[style][0]
    font = TTFont(str(FONTS / src))
    pairs, _ = compute(font)
    add_kern(font, pairs)
    rename(font, style)
    font.flavor = "woff2"
    font.save(str(out_path))
    return pairs


def report(style="semibold"):
    font = TTFont(str(FONTS / WEIGHTS[style][0]))
    pairs, target = compute(font)
    print(style, "targets:", {a + b: round(v) for (a, b), v in target.items()}, "| pairs:", len(pairs))
    for word in ["Nicht verfügbar", "Alle herunterladen", "In PDF umwandeln", "More options", "Choose files",
                 "Aerolith, a nostalgic tactile UI", "Tactile", "Water", "AVATAR", "Typography", "Fußball"]:
        got = [f"{a}{b}:{pairs[a, b]:+d}" for a, b in zip(word, word[1:]) if (a, b) in pairs]
        print(f"  {word}: {' '.join(got) or '-'}")
    big = sorted(pairs.items(), key=lambda kv: -abs(kv[1]))[:30]
    print("  largest:", " ".join(f"{a}{b}:{k:+d}" for (a, b), k in big))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    if cmd == "report":
        report(*(sys.argv[2:3] or ["semibold"]))
    elif cmd == "write":
        out = Path(sys.argv[2])
        out.mkdir(parents=True, exist_ok=True)
        for st in WEIGHTS:
            print(st, len(make(st, out / f"aerolith-text-{st}.woff2")), "pairs")
