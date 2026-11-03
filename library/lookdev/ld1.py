import sys, time; sys.path.insert(0, 'build')
import numpy as np
from studio import build_sheet
from bryce_harness import preview

AQUA = dict(diffuse='#1b7fe0', diffusion=0.75, ambient='#0a3a80', ambience=0.35, specularity=1.0, reflection=0.35)
GREEN = dict(diffuse='#3cb81e', diffusion=0.75, ambient='#155a05', ambience=0.35, specularity=1.0, reflection=0.35)
SILVER = dict(diffuse='#c8d4e0', diffusion=0.6, ambient='#506070', ambience=0.3, specularity=1.0, reflection=0.5)
GLASS = dict(diffuse='#d8f0ff', diffusion=0.12, ambient='#9fd8ff', ambience=0.08, specularity=1.0,
             transparency=0.85, transparent='#e8f8ff', reflection=0.25, refraction=1.25)

def fn(st):
    for i, m in enumerate((AQUA, GREEN, SILVER, GLASS)):
        st.capsule(16, 16 + i * 56, 160, 44, m)
        st.orb(200, 16 + i * 56, 44, m)
        st.orb(260, 26 + i * 56, 24, m)

t = time.time()
rgba, _ = build_sheet('ld1', fn, 320, 240)
print('render s', time.time() - t, rgba.shape)
preview.strip(rgba, ('aero', 'dark')).save('lookdev/ld1.png')
