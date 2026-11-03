"""Pressed-state variants for the primary button, rendered with the production pipeline."""
import sys
from pathlib import Path
LIB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LIB / 'build'))
import build, catalog, export as EX
import materials as M
from bryce_harness import sheet as SH
from pathlib import Path

h, bevel, thick = catalog.SIZES["m"]; w = round(h * 2.5)
def item(name, mat, th=thick, dish=0.0):
    def draw(st, x, y):
        st.pill(x, y, w, h, mat, bevel=bevel, thickness=th, dish=dish)
    return catalog.Item(name, w, h, draw, slice=(0, h / 2, 0, h / 2))

PRESS = dict(M.AQUA, ambient="#1f6fd8", ambience=0.45)
items = [item("t-normal", M.AQUA), item("t-press", PRESS, thick * 0.85, dish=0.35)]
knob = catalog.Item("t-knob", 26, 26, lambda st, x, y: st.orb(x, y, 26, M.PEARL), margin=6)
knob2 = catalog.Item("t-knob-on", 26, 26, lambda st, x, y: st.orb(x, y, 26, M.LIQUID), margin=6)
def gl(st, x, y): st.pill(x, y, w, h, M.CLEAR, bevel=bevel, thickness=thick)
items += [knob, knob2, catalog.Item("t-glass", w, h, gl, slice=(0, h / 2, 0, h / 2), glass=True),
          item("t-green", M.GREEN)]
sheets = build.isolated([catalog.Sheet("press", items)])
jobs = []
for sh in sheets:
    for m, sc in build.write(sh).items():
        wpx = int(round(sh.width * EX.RENDER_SCALE))
        if not build.fresh(sc, wpx):
            jobs.append((sc, sc.with_suffix(".bmp"), wpx))
asp = {f"{sh.name}_{m}.brc": sh.height / sh.width for sh in sheets for m in "kwm"}
import concurrent.futures as cf
def one(j):
    build.render_checked(j, asp[j[0].name]); build.stamp(j[0], j[2])
with cf.ThreadPoolExecutor(7) as ex: list(ex.map(one, jobs))
out = LIB / 'work' / 'press'; out.mkdir(parents=True, exist_ok=True)
for sh in sheets: build.export_sheet(sh, out)
