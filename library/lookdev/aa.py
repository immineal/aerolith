import sys, time, threading; sys.path.insert(0, 'build')
from studio import build_sheet
from bryce_harness import preview
import export, numpy as np
from PIL import Image
GLASS = dict(diffuse='#d8f0ff', diffusion=0.12, ambient='#9fd8ff', ambience=0.08, specularity=1.0,
             transparency=0.85, transparent='#e8f8ff', reflection=0.25, refraction=1.25)
AQUA = dict(diffuse='#1466c8', diffusion=0.75, ambient='#0a3a80', ambience=0.35, specularity=1.0, reflection=0.35)
def fn(st):
    st.pill(8, 8, 160, 44, GLASS, bevel=12, thickness=20)
    st.pill(8, 68, 160, 44, AQUA, bevel=12, thickness=20)
res = {}
def run(tag, scale, aa):
    t = time.time()
    rgba, _ = build_sheet('aa_' + tag, fn, 176, 120, scale=scale, antialias=aa)
    res[tag] = (time.time() - t, rgba, scale)
ths = [threading.Thread(target=run, args=a) for a in (('s6', 6, None), ('s3n', 3, 'normal'), ('s3s', 3, 'supreme'))]
[t.start() for t in ths]; [t.join() for t in ths]
rows = []
for tag, (dt, rgba, scale) in res.items():
    print(tag, 'seconds', round(dt), rgba.shape)
    a3 = export.box_downsample(rgba, 2) if scale == 6 else rgba     # all at 3x
    rows.append(np.clip(preview.over(a3, 'aero'), 0, 1))
Image.fromarray((np.concatenate(rows, 1) * 255).astype(np.uint8)).save('lookdev/aa.png')
