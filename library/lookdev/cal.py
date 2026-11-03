import sys; sys.path.insert(0, 'build')
import numpy as np
from PIL import Image
from studio import Studio, ROOT
from bryce_harness import sheet, bryce
KINDS = ['sphere', 'cube', 'cylinder', 'cone', 'pyramid', 'square', 'disk', 'torus']
def build(c):
    st = Studio(c, 320, 240, 'flat')
    for i, k in enumerate(KINDS):
        x, y = 40 + (i % 4) * 80, 60 + (i // 4) * 120
        rot = (-90, 0, 0) if k in ('square', 'disk', 'torus') else (0, 0, 0)
        c.add(k, st.p(x, y, 0), rot, (40, 40, 40), dict(diffuse='#ffffff'))
c = sheet.Ctx('m'); build(c); c.finish()
p = ROOT / 'work/sheets/cal_m.brc'; c.sb.write(p)
bryce.render_job(str(p), str(p.with_suffix('.bmp')), 1920, instance=sheet.POOL[0])
r = np.asarray(Image.open(p.with_suffix('.bmp')).convert('RGB'))[..., 0] > 127
for i, k in enumerate(KINDS):
    x, y = 40 + (i % 4) * 80, 60 + (i // 4) * 120
    sub = r[(y - 50) * 6:(y + 50) * 6, (x - 38) * 6:(x + 38) * 6]
    ys, xs = np.where(sub)
    print(k, 'w', (xs.max() - xs.min() + 1) / 6 if len(xs) else 0, 'h', (ys.max() - ys.min() + 1) / 6 if len(ys) else 0)
