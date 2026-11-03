"""Style board v2: split into three sheets rendered concurrently, composited for review."""
import sys, time; sys.path.insert(0, 'build'); sys.path.insert(0, 'lookdev')
import concurrent.futures as cf
from studio import build_sheet
import shapes
from board import AQUA, AQUA_HOVER, AQUA_PRESS, GREEN, DISABLED, GLASS, FROST, PEARL, LIQUID
from bryce_harness import preview
from PIL import Image
import numpy as np

def buttons(st):
    for i, m in enumerate((AQUA, AQUA_HOVER, AQUA_PRESS, DISABLED)):
        st.pill(12 + (i % 2) * 100, 12 + (i // 2) * 60, 84, 44, m, bevel=12, thickness=14 if m is AQUA_PRESS else 20)
    st.pill(212, 12, 84, 44, GREEN, bevel=12, thickness=20)
    st.pill(212, 72, 84, 44, GLASS, bevel=12, thickness=20)

def controls(st):
    st.pill(12, 12, 56, 32, GLASS, bevel=10, thickness=16)
    st.orb(15, 15, 26, PEARL, z=-12)
    st.pill(84, 12, 56, 32, GLASS, bevel=10, thickness=16)
    st.orb(111, 15, 26, LIQUID, z=-12)
    st.slab(160, 15, 26, 26, 7, 7, 10, GLASS)
    st.slab(200, 15, 26, 26, 7, 7, 10, GLASS)
    st.slab(202, 17, 22, 22, 0, 0, 10, LIQUID, z=-9, heights=shapes.tick())
    st.slab(240, 15, 26, 26, 13, 9, 12, GLASS)
    st.slab(280, 15, 26, 26, 13, 9, 12, GLASS)
    st.orb(287, 22, 12, PEARL, z=-8)
    st.pill(12, 72, 140, 10, GLASS, thickness=8)
    st.pill(14, 74, 80, 6, dict(AQUA, ambience=0.5), thickness=4, z=-1)
    st.orb(84, 66, 22, PEARL, z=-10)
    st.pill(170, 68, 136, 18, GLASS, thickness=16)
    st.pill(173, 71, 80, 12, LIQUID, thickness=10)
    st.slab(12, 104, 32, 32, 0, 0, 12, AQUA, heights=shapes.heart())
    st.slab(60, 104, 32, 32, 0, 0, 12, PEARL, heights=shapes.heart())
    st.slab(108, 104, 32, 32, 0, 0, 12, GLASS, heights=shapes.heart())

def panel(st):
    st.slab(12, 12, 296, 80, 14, 9, 10, FROST)

SHEETS = [('b2_buttons', buttons, 308, 128), ('b2_controls', controls, 318, 148), ('b2_panel', panel, 320, 104)]

if __name__ == '__main__':
    t = time.time()
    with cf.ThreadPoolExecutor(3) as ex:
        res = list(ex.map(lambda s: build_sheet(s[0], s[1], s[2], s[3])[0], SHEETS))
    print('render s', round(time.time() - t))
    W = max(r.shape[1] for r in res); H = sum(r.shape[0] for r in res)
    board = np.zeros((H, W, 4)); y = 0
    for r in res:
        board[y:y + r.shape[0], :r.shape[1]] = r; y += r.shape[0]
    np.save('../work/sheets/board2.npy', board)
    for bg in ('aero', 'dark'):
        im = preview.strip(board, (bg,))
        im.resize((im.width // 2, im.height // 2), Image.LANCZOS).save(f'lookdev/board2_{bg}.png')
