"""Style board: one of every technique, under the production rig."""
import sys, time; sys.path.insert(0, 'build')
from studio import build_sheet
import shapes
from bryce_harness import preview
from PIL import Image

AQUA = dict(diffuse='#1466c8', diffusion=0.75, ambient='#0a3a80', ambience=0.35, specularity=1.0, reflection=0.35)
AQUA_HOVER = dict(AQUA, diffuse='#2584ea', ambience=0.5)
AQUA_PRESS = dict(AQUA, diffuse='#0e4f9e', ambience=0.25, reflection=0.2)
GREEN = dict(diffuse='#1d8a35', diffusion=0.75, ambient='#0b4a18', ambience=0.35, specularity=1.0, reflection=0.35)
DISABLED = dict(diffuse='#9fb2c4', diffusion=0.7, ambient='#5d7184', ambience=0.35, specularity=0.4, reflection=0.12)
GLASS = dict(diffuse='#d8f0ff', diffusion=0.12, ambient='#9fd8ff', ambience=0.08, specularity=1.0,
             transparency=0.85, transparent='#e8f8ff', reflection=0.25, refraction=1.25)
FROST = dict(diffuse='#f2f9ff', diffusion=0.35, ambient='#d8ecff', ambience=0.2, specularity=0.8,
             transparency=0.62, transparent='#f4fbff', reflection=0.15, refraction=1.05)
PEARL = dict(diffuse='#f4f8fb', diffusion=0.8, ambient='#c8d6e4', ambience=0.3, specularity=1.0, reflection=0.3)
LIQUID = dict(diffuse='#2fbf3f', diffusion=0.7, ambient='#127a20', ambience=0.45, specularity=1.0, reflection=0.3)
CHROME = {'preset': 'Metallic Chrome'}

def fn(st):
    # buttons, M size, flat face (text-friendly)
    for i, m in enumerate((AQUA, AQUA_HOVER, AQUA_PRESS, DISABLED)):
        th = 14 if m is AQUA_PRESS else 20
        st.pill(12 + i * 92, 12, 80, 44, m, bevel=12, thickness=th)
    st.pill(12, 72, 80, 44, GREEN, bevel=12, thickness=20)
    st.pill(104, 72, 80, 44, GLASS, bevel=12, thickness=20)
    # toggle off / on
    st.pill(200, 78, 56, 32, GLASS, bevel=10, thickness=16)
    st.orb(203, 81, 26, PEARL, z=-12)
    st.pill(270, 78, 56, 32, GLASS, bevel=10, thickness=16)
    st.orb(297, 81, 26, LIQUID, z=-12)
    # checkbox off / on, radio off / on
    st.slab(14, 136, 26, 26, 7, 7, 10, GLASS)
    st.slab(58, 136, 26, 26, 7, 7, 10, GLASS)
    st.slab(60, 138, 22, 22, 0, 0, 10, LIQUID, z=-9, heights=shapes.tick())
    st.slab(102, 136, 26, 26, 13, 9, 12, GLASS)
    st.slab(146, 136, 26, 26, 13, 9, 12, GLASS)
    st.orb(153, 143, 12, PEARL, z=-8)
    # slider: tube + liquid fill + thumb
    st.pill(190, 142, 140, 10, GLASS, thickness=8)
    st.pill(192, 144, 80, 6, dict(AQUA, ambience=0.5), thickness=4, z=-1)
    st.orb(262, 136, 22, PEARL, z=-10)
    # progress tube with liquid inside
    st.pill(12, 184, 200, 18, GLASS, thickness=16)
    st.pill(15, 187, 120, 12, LIQUID, thickness=10)
    # embossed chrome heart icon
    st.slab(232, 178, 32, 32, 0, 0, 10, CHROME, heights=shapes.heart())
    # frosted panel slab
    st.slab(12, 222, 330, 70, 14, 9, 10, FROST)

if __name__ == '__main__':
    t = time.time()
    rgba, _ = build_sheet('board1', fn, 356, 304)
    print('render s', round(time.time() - t))
    for bg in ('aero', 'dark'):
        im = preview.strip(rgba, (bg,))
        im.resize((im.width // 2, im.height // 2), Image.LANCZOS).save(f'lookdev/board1_{bg}.png')
