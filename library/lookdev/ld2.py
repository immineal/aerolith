import sys, time; sys.path.insert(0, 'build')
from studio import build_sheet
from bryce_harness import preview
from PIL import Image

AQUA = dict(diffuse='#1466c8', diffusion=0.75, ambient='#0a3a80', ambience=0.35, specularity=1.0, reflection=0.35)
GLASS = dict(diffuse='#d8f0ff', diffusion=0.12, ambient='#9fd8ff', ambience=0.08, specularity=1.0,
             transparency=0.85, transparent='#e8f8ff', reflection=0.25, refraction=1.25)

def fn(st):
    # row 1: dome pills (round cross-section)
    st.pill(16, 16, 160, 44, GLASS)
    st.pill(196, 16, 108, 44, AQUA)
    # row 2: flat-face buttons (bevel 12px), text-friendly
    st.pill(16, 76, 160, 44, GLASS, bevel=12, thickness=20)
    st.pill(196, 76, 108, 44, AQUA, bevel=12, thickness=20)
    # row 3: rounded-rect panel slab (glass), small radius
    st.slab(16, 136, 288, 88, 14, 10, 12, GLASS)

t = time.time()
rgba, _ = build_sheet('ld2', fn, 320, 240)
print('render s', round(time.time() - t))
im = preview.strip(rgba, ('aero', 'dark'))
im.resize((im.width // 2, im.height // 2), Image.LANCZOS).save('lookdev/ld2.png')
