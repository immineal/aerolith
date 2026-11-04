"""Check that browsers lay Aerolith Text out exactly as the font says, in Chromium and Firefox.

    python3 spacing_check.py            # exits 1 on any mismatch

1. Pair test: every kerned pair (plus a sample of unkerned ones, to catch kerns leaking onto
   accented forms) is set at 100 px, and its width must equal advance(a) + advance(b) + kern(a, b).
2. Label test: the demo labels at 16 px / 600 / 0.01em, glyph by glyph. Before text-rendering:
   geometricPrecision Chromium put them up to 1.7 px off by rounding each advance to a whole pixel.

WebKit is left out on purpose: Playwright's Linux WebKit rounds advances whatever the CSS says
(Safari on macOS does not).
"""
import random
import sys
from pathlib import Path

from fontTools.ttLib import TTFont
from playwright.sync_api import sync_playwright

import kern

LIB = Path(__file__).resolve().parents[1]
FONTS = LIB / "dist" / "fonts"
STYLES = {"light": 300, "regular": 400, "semibold": 600, "bold": 700}
LABELS = ["Nicht verfügbar", "Alle herunterladen", "In PDF umwandeln", "More options", "Choose files…",
          "Aerolith, a nostalgic tactile UI", "Pressed", "Cancel"]
PAIR_TOL = 0.1      # px at 100 px (0.001 em)
LABEL_TOL = 0.25    # px at 16 px. Firefox rounds the 0.16 px letter-spacing to 1/60 px (0.1667), about 0.007 px
                    # per glyph; the whole-pixel rounding this guards against was up to 1.7 px


def page(style_pairs):
    faces = "".join(
        f"@font-face{{font-family:T{w};src:url(file://{FONTS}/aerolith-text-{s}.woff2);font-weight:{w}}}"
        for s, w in STYLES.items())
    body = ""
    for s, w in STYLES.items():
        spans = "".join(f"<span>{a}{b}</span>" for a, b in style_pairs[s])
        body += f"<div class=p data-w={w} style='font-family:T{w};font-weight:{w}'>{spans}</div>"
    return (f"<!doctype html><meta charset=utf-8><style>{faces}"
            "body{margin:0}.p{font-size:100px;white-space:nowrap;text-rendering:geometricPrecision;"
            "font-synthesis:none}.p span{display:inline-block}"
            ".l{font:600 16px/1 T600;letter-spacing:.01em;text-rendering:geometricPrecision;white-space:nowrap}"
            "</style>" + body + "".join(f"<div class=l>{t}</div>" for t in LABELS))


def main():
    rnd = random.Random(1)
    fonts, kerns, chars = {}, {}, {}
    pair_sets = {}
    for s in STYLES:
        f = TTFont(str(kern.FONTS / kern.WEIGHTS[s][0]))
        kerns[s], _ = kern.compute(f)
        fonts[s] = (f.getBestCmap(), f["hmtx"])
        zero = [(a, b) for a in kern.charset(f) for b in kern.charset(f) if (a, b) not in kerns[s]]
        pair_sets[s] = sorted(kerns[s]) + rnd.sample(zero, 2500)
    html = page(pair_sets)
    tmp = Path(__file__).resolve().parent / "__pycache__" / "spacing_check.html"
    tmp.parent.mkdir(exist_ok=True)
    tmp.write_text(html)
    JS_PAIRS = "()=>[...document.querySelectorAll('.p')].map(d=>[...d.children].map(s=>s.getBoundingClientRect().width))"
    JS_LABELS = """()=>[...document.querySelectorAll('.l')].map(d=>{const n=d.firstChild,r=document.createRange(),xs=[];
      for(let i=0;i<n.length;i++){r.setStart(n,i);r.setEnd(n,i+1);xs.push(r.getBoundingClientRect().left)}
      r.setStart(n,0);r.setEnd(n,n.length);return {xs,w:r.getBoundingClientRect().width}})"""
    bad = 0
    with sync_playwright() as p:
        for eng in ("chromium", "firefox"):
            b = getattr(p, eng).launch()
            pg = b.new_page(viewport={"width": 1200, "height": 800})
            pg.goto("file://" + str(tmp))
            pg.evaluate("document.fonts.ready")
            pg.wait_for_timeout(500)
            if not pg.evaluate("document.fonts.check('600 16px T600')"):
                print(eng, "FAIL: Aerolith Text did not load")
                bad += 1
            widths = pg.evaluate(JS_PAIRS)
            worst = 0
            for (s, w), ws in zip(STYLES.items(), widths):
                cm, hm = fonts[s]
                for (a, c), got in zip(pair_sets[s], ws):
                    want = (hm[cm[ord(a)]][0] + hm[cm[ord(c)]][0] + kerns[s].get((a, c), 0)) * 100 / 2048
                    d = abs(got - want)
                    worst = max(worst, d)
                    if d > PAIR_TOL:
                        bad += 1
                        if bad < 15:
                            print(f"  {eng} {s} {a}{c}: {got:.2f} px, want {want:.2f} (kern {kerns[s].get((a, c), 0)})")
            print(f"{eng}: {sum(len(v) for v in pair_sets.values())} pairs, worst error {worst:.3f} px at 100 px")
            cm, hm = fonts["semibold"]
            for text, r in zip(LABELS, pg.evaluate(JS_LABELS)):
                x, want = 0.0, []
                for i, ch in enumerate(text):
                    want.append(x)
                    k = kerns["semibold"].get((ch, text[i + 1]), 0) if i + 1 < len(text) else 0
                    x += (hm[cm[ord(ch)]][0] + k) * 16 / 2048 + 0.16
                got = [v - r["xs"][0] for v in r["xs"]]
                d = max(abs(g - w) for g, w in zip(got, want))
                if d > LABEL_TOL:
                    bad += 1
                print(f"  {eng} label {text!r}: worst glyph error {d:.2f} px{'  <-- FAIL' if d > LABEL_TOL else ''}")
            b.close()
    print("OK" if not bad else f"{bad} problem(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
