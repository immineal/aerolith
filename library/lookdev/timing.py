"""What makes a sheet slow? One element per scene, K pass only, timed in parallel."""
import sys, time; sys.path.insert(0, 'build')
import studio
from studio import Studio
from bryce_harness import sheet
import concurrent.futures as cf
from pathlib import Path
sys.path.insert(0, 'lookdev')
from board import AQUA, GLASS, FROST  # noqa (board.py guarded by __main__)

W, H = 120, 70
def variant(name, mat, n=512, size=(80, 44), thick=20):
    def build(c):
        st = Studio(c, W, H)
        x, y = (W - size[0]) / 2, (H - size[1]) / 2
        st.slab(x, y, size[0], size[1], size[1] / 2, 12, thick, mat, n=n)
    return name, build

V = [variant('glass512', GLASS), variant('glass256', GLASS, n=256), variant('glass128', GLASS, n=128),
     variant('aqua512', AQUA), variant('glass512_norefr', dict(GLASS, refraction=1.0)),
     variant('glass512_norefl', dict(GLASS, reflection=0.0)), variant('frost512', FROST)]
out = Path('../work/sheets/timing'); out.mkdir(parents=True, exist_ok=True)
jobs = []
for name, build in V:
    c = sheet.Ctx('k'); build(c); c.finish()
    from bryce_harness import brc_scene
    brc_scene.set_document(c.sb, *c.doc)
    p = Path(brc_scene.write(c.sb, str(out / f'{name}.brc')))
    jobs.append((name, p))

def one(j):
    name, p = j
    t = time.time()
    sheet.render_many([(p, p.with_suffix('.bmp'), W * 6)], timeout=1800)
    return name, round(time.time() - t)

with cf.ThreadPoolExecutor(7) as ex:
    for name, s in ex.map(one, jobs):
        print(name, s, 's', flush=True)
