# Bryce 2 .BRC: scene-level records

Object attributes, groups and booleans, lights, sky and fog, sun, camera, and the document record.
Code: `harness/bryce_harness/brc_scene.py`, built on `brc.py`. Templates: `brc_templates/scene_*`.

Status: **V** = verified by a render or a differential save in Bryce 2.1 (Windows, under Wine) ·
**P** = plausible (corpus statistics, not verified) · **?** = unknown.
Offsets are into the object record (slot A) unless noted. BE unless noted; the transform block is LE.

How the fields were found: the "Win" values come from differential saves. Change one control, use
File > Save As, and diff the result against the save before (scratch scripts used `ui.py` and `diff()`).
Corpus = the 68 sample scenes on the CD plus the preset libraries `Presets.sky` and `SKIES.SKY`. These
libraries are CCmF files that hold the same object store, with C3dBaseSky, C3dSunLight and C3dTexture records.
The samples are Mac-made (Bryce 2.0) and a few flag bits differ from what 2.1 for Windows writes. These
cases are marked below.

Renders mentioned below are in `work/re_scene/` (BMP and PNG).

---

## 1. Common object header (all scene objects: primitives, groups, lights, terrains, meshes)

| off | type | field | status |
|---|---|---|---|
| 0x00 | char[128] | name | V |
| 0x80 | char[8] | tag (`3dobsphr`, `3dobgrou`, `lghtsphr` …) | V |
| 0x88 | u32 | editor state: 0x01 selected, 0x02 locked (set together with attr 0x02), 0x08 Show As Box | V |
| 0x8c | u32 | attributes, see below | V |
| 0x90 | "base" + u32 | material id (primitives, groups). Lights have zeros here | V |
| 0x1bc… | LE | transform block (brc.py) | V |
| 0x2e0 | u8 | family index (e.g. 6, 8, 0x0b) | P |
| 0x2e4 | 3×u8 | family (wireframe) colour, e.g. 0x555555 (default primitive), 0xffffff (lights), 0x008000 | P |

Attribute bits at 0x8c (Objects > Attributes…, Ctrl+Alt+E). The dialog has Positive, Negative, Intersect,
Locked and Show As Box. It has no "Hidden" option and no name field.

| bit | meaning | status |
|---|---|---|
| 0x02 | Locked (Ctrl+A no longer selects the object) | V |
| 0x04 | set on most neutral objects in the Mac samples. Win writes 0 for neutral | P |
| 0x08 | Positive | V |
| 0x10 | Negative | V |
| 0x20 | Intersect (Win). In the Mac samples, 0x20 also marks members of plain (0x10000) groups | V / P |
| 0x40 | member of a boolean group (Bryce sets it when grouping) | V |
| 0x80 | light | P |
| 0x200, 0x800, 0x2000 | light options, see §3 | V |
| 0x10000 | plain group (Mac samples only; Win writes 0) | P |
| 0x20000 | boolean group (Win and Mac) | V |

## 2. Groups `C3dGroupType` (0x328 + 12·n bytes) and booleans

A Bryce-saved group (Objects > Group Objects, Ctrl+G) was diffed against the save before grouping:

| off | type | field | status |
|---|---|---|---|
| 0x88 | u32 | 1 (the new group is selected) | V |
| 0x8c | u32 | 0x20000 if any member is positive/negative/intersect, else 0 | V |
| 0x90 | "base"+u32 | the group's own material. Bryce creates a new default material | V |
| 0x1bc… | LE | transform: identity. Members keep their world transforms (grouping does not touch them) | V |
| 0x2ec | 6×f64 | bounding box min xyz, max xyz in internal units (union of members; cube/pyramid count ±0.5·scale, torus ±2·scale) | V (Bryce's numbers match) |
| 0x31c | u32 | group number, 1… unique per scene | P |
| 0x320 | 4 B | 01 01 00 00, the same in all 311 sample groups | P |
| 0x324 | u32 | member count | V |
| 0x328 | n × (char[8] tag + u32 id) | members | V |

Grouping also clears the members' selected bit (0x88). For a boolean group it ORs 0x40 into each
member's 0x8c. `brc_scene.group()` writes byte-identical records: a group written by the module and
then opened and re-saved by Bryce came back unchanged.

Boolean behaviour, from renders:

- **Union of positive glass members removes the internal surfaces (V, `pill.png`).** The case is a cylinder
  (rotated z 90°) with two end spheres in glass (diffusion 0.12, transparency 0.85, refraction 1.25) on white.
  Left ungrouped, or in a neutral group, the inner sphere halves and cylinder caps show through. As a
  boolean group with all members positive, it renders as one glass solid. Only faint hairlines remain where the
  surfaces meet.
- **Negative spheres cut cleanly (V, `cubecut.png`, `pill.png`).** The holes are round and have the right size.
  The cut surface takes the negative object's material: a yellow negative sphere gives yellow cut walls.
- **Negative and intersect cubes are broken in Bryce 2.1 (V, `cubecut.png`, `hemi2-4.png`).** A negative
  cube 10 B wide in a slab cuts only a thin bar. A 20 B cube gives a speckled (noisy) hole. Cubes larger than
  the target do not cut at all (a sphere minus a cube that covers its lower half renders as a whole sphere).
  Intersect with a cube gives a sliver. Bryce writes the same records, so the problem is in Bryce's renderer,
  not in our writer. A likely cause is that its cube inside-test does not match the cube's rendered
  ±0.5·scale extent. Use spheres or cylinders as cutters (`hemi5.png`).
- **Flat-cut hemispheres work with a huge sphere as the cutter (V, `hemi5.png`).** Four variants on a
  20.48 B sphere: (1) minus a negative sphere of 1000 B centred 500 B below the cut plane, (2) minus a
  negative cylinder covering the lower half, (3) intersect with a cylinder covering the upper half,
  (4) intersect with a 1000 B sphere centred 500 B above. All four give a flat, clean cut face. The cylinder
  variants (2, 3) leave a one-pixel seam artifact along the cylinder's axis: a sliver hanging below in (2)
  and a slit through the dome in (3). The huge-sphere variants (1, 4) are clean. Over 1000 B, the cutter's
  curvature is 0.05 % of the radius, which is invisible. The render (640×200, no AA) took about 10 minutes,
  much slower than plain primitives.

## 3. Lights

The classes are C3dSphereLight (785 B, the radial/point light), C3dConeLight (792 B, spotlight) and
C3dCubeLight (792 B). The light editor is Objects > Edit Object (Ctrl+E) on a selected light. It is the
"Edit Lights" dialog, with two drag thumbnails, a colour swatch, a menu (Render in Scene / Against Neutral,
Visible Light, Infinite Light, Disable Cast Shadows, Remove Gel) and the buttons Pict Gels and Texture Gels.

| off | type | field | status |
|---|---|---|---|
| 0x8c | u32 | 0x80 light (P) · 0x200 Visible Light (V) · 0x800 Disable Cast Shadows (V) · 0x2000 Infinite Light, no falloff (V) | |
| 0x2e8 | u32 | 0 in every sample; probably where a gel reference goes (P). Applying a Texture Gel crashed Bryce under Wine | ? |
| 0x2ec | 3×f32 | light colour | V (diff + render) |
| 0x2f8 | f64 | intensity = dialog value / 2 (dialog default ≈ 20) | V (diff + render) |
| 0x300 | f64 | 1.0 everywhere | ? |
| 0x308 | 8 B | 0 | ? |
| 0x310 | f64 | spotlight edge softness = dialog value / 20 (0…100 → 0…5) | V (diff + render) |

- Both thumbnails drag the intensity. The second one sets softness on a spotlight.
- **Spotlight geometry (V, `L2.png`, `L3.png`):** the beam points down local −Y. Rotate the light to aim it.
  The cone's footprint follows the light's x/z size: a larger size gives a wider cone. A taller y size narrows
  it, because the cone angle follows the x/z : y ratio. There is no cone-angle field. Softness 100 gives a
  soft edge and also a smaller bright core.
- **Checked in `L3.png`** (black floor lit only by the lights, sky mode off, sun black):
  - colour works (a red light gives a red pool);
  - Disable Cast Shadows works (a ball next to the light casts no shadow; next to a normal light it casts a
    long one);
  - a cube light at intensity 20 gives no light at all;
  - Visible Light draws the light's sphere as a **black** ball over its coloured pool. In the editor the
    visible-light body probably uses a glow material that our template lacks (?).
- **C3dCubeLight:** in all 77 sample cube lights everything after 0x2e8 is zero (black, intensity 0). The editor
  shows a black swatch for it, and changing values saves nothing. It emits no light in a render (V, `L3.png`).
- The Mac samples also use 0x100 and 0x400 on lights (meaning unknown).

## 4. Sky `C3dBaseSky` (376 B)

The controls are on the Sky&Fog palette: Sky Mode, Shadows/Ambient Color, Fog/Fog Color, Haze/Haze Color,
Cloud Height, Cloud Cover/Cumulus Color, Frequency/Amplitude, and the Sun Control. Sky&Fog Options adds Auto
Update, Link Sun to View, Stratus Clouds, Cumulus Clouds, Reset Sky and Edit Sky&Fog. The Edit Sky&Fog dialog
shows numbers: Sun x y z, Shadow, Fog, Height, Haze, Clouds, Height, Scale, Amplitude.
The formulas below convert dialog numbers to stored values. Each was checked at 3–4 values per control
(differential saves).

| off | type | field | dialog ↔ stored | status |
|---|---|---|---|---|
| 0x88 | u32 | flags, see below | | V |
| 0x8c | f64 | cloud height | stored = (50 + 16·h)/10.24 (default h≈3) | V |
| 0x94 | 3×f32 | Cumulus Color (default 0.8 grey) | | V |
| 0xa0 | 3×f32 | (1,1,1); 0.247 grey in some samples. Setting it to red changes no pixel, with or without clouds (`sk_unk*.png`) | | ? |
| 0xbc | f64 | cloud cover | v/40 (default 20) | V |
| 0xc4 | f64 | amplitude | v/100 (default 100) | V |
| 0xcc | f64 | frequency ("Scale") | v/100 (default 25); 0 is stored as 1e-7 | V |
| 0xec | 3×f32 | Custom Sky swatch 2 (default 0.2,0.2,1): the main sky colour in Custom Sky mode (`sk_custom.png`) | | V |
| 0xf8 | 3×f32 | Custom Sky swatch 3 (default white): shows near the horizon in Custom Sky, mixed with haze | | V (diff), P (role) |
| 0x104 | 3×f32 | 0 in Win default, coloured in some samples. Setting it to green changes no pixel | | ? |
| 0x110 | 3×f32 | background colour in mode "Atmosphere Off" (default 0.2,0.2,1). Haze still tints the horizon; set haze=0 for a flat colour | | V (diff + render) |
| 0x11c | f64 | shadows | 1 − v/100 (default 90) | V |
| 0x124 | 3×f32 | Ambient Color | | V (diff) |
| 0x130 | f64 | 1.0 everywhere. At 0 the shadowed sides go black and the ground darkens (`sk_unk130.png`): an ambient-strength factor | | P (one render) |
| 0x138 | 3×f32 | Haze Color | | V (diff) |
| 0x144 | f64 | haze | v/20 (default 8); 0 = no distance tint | V |
| 0x14c | 3×f32 | Fog Color | | V (diff) |
| 0x158 | f64 | fog density | v²/2000 | V |
| 0x160 | f64 | fog height | v/100 | V |
| 0x168 | "xtrb" "xtrb" + 2×u32 LE | ids of the two cloud C3dTextures ("high"/"low cloud texture"), little-endian | | P |

Flags (0x88):

| bits | meaning | status |
|---|---|---|
| low nibble | sky mode: 0x3 Soft Sky (default), 0x5 Darker Sky, 0x9 Custom Sky, 0x0 Atmosphere Off. Clicking the Sky Mode thumbnail cycles through them | V |
| 0x10 | clouds on (set whenever stratus or cumulus is on) | V |
| 0x20 | Stratus Clouds | V |
| 0x40 | Cumulus Clouds | V |
| 0x80 | set in the Win default | ? |
| 0x100 | set in many Mac samples | ? |
| 0x200 | Link Sun to View | V |

"Auto Update" is not stored. Changing the frequency also rewrites a few bytes of the high cloud
C3dTexture (0x409, 0x425). `set_sky` does not copy that over. Clouds still render with structure
(`sk_cl30.png`), so the frequency still takes effect without that copy.

## 5. Sun `C3dSunLight` (832 B)

| off | type | field | status |
|---|---|---|---|
| 0x8c | u32 | 0x280 (Win default), 0x500 in some samples | ? |
| 0x2ec | 3×f32 | sun colour (Sky&Fog "Sun Color" swatch) | V (diff) |
| 0x2f8, 0x300 | f64 | 1.0, 1.0 | ? |
| 0x310 | 3×f32 | copy of the sun colour (written together with 0x2ec) | V (diff) |
| 0x31c | 3×f32 | Custom Sky swatch 1. The first swatch of Custom Sky mode is stored in the sun. Red here was not visible with the sun out of view, so it is probably the colour around the sun | V (diff), P (role) |
| 0x328 | 3×f64 | unit vector toward the sun. Edit Sky&Fog shows it ×100 | V |

## 6. Camera `C3dBaseCamera` (884 B)

| off | type | field | status |
|---|---|---|---|
| 0x8c | u32 | 0x4001 normal; 0x10001 with "360 Panorama Render" (Render Options) | V (diff) |
| 0x2ec / 0x304 | 3×f64 | forward / up | V |
| 0x33c | f64 | "FOV", radians. **Horizontal FOV = 0.8 × this value at any document aspect** (60° → 48°, 30° → 24°, 90° → 72°; focal length in px = (W/2)/tan(0.4·fov)) | V (render, `fov_*.png`) |
| 0x344, 0x34c | f64 | 1.0, 1.0 | ? |
| 0x354, 0x35c | f64 **LE** | 2D pan x, y (samples: −59, −2; −4, −102) | P |
| 0x364, 0x36c | f64 **LE** | 2D zoom x, y (samples: 1.333, 0.627, 2.4) | P |

Measured: a 640 px wide render at fov 60° puts a point 20 B off-axis at 100 B distance 143.8 px from
centre, for both 4:3 and 2:1 documents. Vertical FOV follows from the aspect.

## 7. Document `brycedocset` (slot A empty, data in slot B, 416 B)

Found by differential saves of File > Document Setup (Ctrl+Alt+N), then checked by render:

| off | type | field | status |
|---|---|---|---|
| 0x00 | u32 | document width | V |
| 0x04 | u32 | document height (aspect = width:height) | V |
| 0x08 | u32 | render width = document width × "Render Resolution" (1:0.25 … 1:4) | V |
| 0x0c | u32 | render height | V |
| 0x10 | 4×u32 | render rect: 0, 0, render height, render width | V |
| 0x20… | | zeros | |

- A scene written with 640×320 renders to disk at 2:1 (`aa_*.png`: 400×200 for width 400). The Render to
  Disk dialog then says "Aspect ratio constrained at 2:1" (V). The palette frame grows with the document.
- **Antialiasing is not in the scene and not in any preference file** (V: no diff when it was toggled; the
  registry and the Bryce folder do not change). It is a per-session menu setting: Control palette > Render
  Options… (the triangle under the render spheres) > AntiAliasing Off / Normal Quality / Supreme Quality.
  The same menu has Spatial Optimization Off/Low/High, Report Render Time, and the render modes Perspective,
  360 Panorama (camera flag, §6), Mask, Distance and Altitude. Mask, Distance and Altitude are not stored either.
  `brc_scene.set_document(scene, w, h, antialias='normal')` remembers the choice. `brc_scene.write()` stores it
  in a `<file>.brc.render.json` sidecar, and `render()` applies it (V, `side_*.png`).
  `brc_scene.render(scene, out, width, antialias='normal'|'supreme', mode='mask'|…)` restarts Bryce, opens
  the scene, picks the menu items and renders to disk. AA renders: `aa_None.png`, `aa_normal.png` and
  `aa_supreme.png` (41 s, 47 s and 50 s at 400×200).
- `bryce.render_to_disk` OCRs the whole view for "Output Size in Pixels". On wide documents that fails,
  because the view is mostly black. `brc_scene` has a variant that also OCRs crops around the screen centre,
  where Bryce centres the dialog.

## 8. Render checks

All renders are in `work/re_scene/` and were viewed. The scripts are scratch scripts that use `brc_scene`.

| render | scene | result |
|---|---|---|
| `pill.png` | glass cylinder + 2 end spheres; ungrouped, neutral group, boolean union | union removes the internal surfaces (faint hairlines remain) |
| `cubecut.png` | slab minus negative cubes 10/20 B, minus negative spheres 10/20 B | spheres cut clean round holes; cubes cut a thin bar or a speckled hole |
| `hemi2-4.png` | sphere minus/intersect cube that covers half of it | no cut, or a sliver: negative/intersect cubes are unusable |
| `hemi5.png` | sphere: − huge sphere, − cylinder, ∩ cylinder, ∩ huge sphere | all are flat hemispheres; the cylinder versions show a 1 px seam artifact; the huge-sphere versions are clean |
| `aa_None/normal/supreme.png`, `aa_zoom.png` | 640×320 document rendered at 400 px | 2:1 output; AA visibly smooths edges |
| `side_None/normal.png` | `set_document(..., antialias='normal')` + `render(sb, …)` (sidecar path) | 0 vs 333 intermediate edge pixels: the sidecar options are applied |
| `fov_def/30/90.png`, `fov_def_21.png` | marker sphere 20 B off-axis at 100 B | horizontal FOV = 0.8 × stored FOV, at 4:3 and 2:1 |
| `L1.png`, `L2.png`, `L3.png` | lights on a black floor, sky off | colour, intensity, no-shadows, spot size/softness work; cube light emits nothing; Visible Light body renders black |
| `sk_soft/darker/custom/off.png` | sky modes | 3 = Soft, 5 = Darker, 9 = Custom (0xec = main colour), 0 = flat 0x110 background |
| `sk_fog.png` | fog 50, height 30, orange; haze 30, purple | orange ground fog and a purple horizon band |
| `sk_clouds.png`, `sk_cl30.png` | stratus + cumulus, cover 60 (pink cumulus) / 30 | clouds render; cover 60 fills the sky with the cumulus colour |
| `sk_unk.png`, `sk_unk2.png`, `sk_unk130.png` | 0xa0 = red, 0x104 = green (with and without clouds); 0x130 = 0 | 0xa0 and 0x104 give pixel-identical renders; 0x130 = 0 removes the ambient light |

### Open questions

- Sky 0xa0, 0x104 and flag bits 0x80/0x100: no visible effect found.
- Lights: 0x300 (always 1.0), gels (0x2e8?). Texture Gels crashed Bryce under Wine, so gels were not tested.
  The Visible Light body renders black.
- Sun 0x8c and 0x2f8/0x300. Camera 0x344/0x34c. 2D pan/zoom at 0x354–0x36c is P (corpus only, no render).
- Group 0x31c (group number) and 0x320 (01 01 00 00): copied, not varied.
- Header family byte/colour (0x2e0/0x2e4): wireframe only, not varied.

## 9. API (`bryce_harness.brc_scene`, imported as `bs`)

```python
from bryce_harness import brc, brc_scene as bs
sb = brc.SceneBuilder()
bs.set_document(sb, 512, 128, antialias="normal")    # aspect 4:1; AA is remembered, not stored in .brc
bs.set_camera(sb, (0, 10, -90), look_at=(0, 10, 0), hfov=40)   # hfov = true horizontal degrees
bs.set_sky(sb, mode="off", background=(1, 1, 1), haze=0, shadows=80)
cyl = sb.add("cylinder", offset=(0, 10, 0), rotate=(0, 0, 90), size=(10, 40, 10), material=glass)
a = sb.add("sphere", offset=(-20, 10, 0), size=(10,) * 3, material=glass)
b = sb.add("sphere", offset=(20, 10, 0), size=(10,) * 3, material=glass)
bs.group(sb, [cyl, a, b], booleans=["positive"] * 3)  # seamless union
bs.add_light(sb, "spot", offset=(0, 60, 0), intensity=20, softness=40, color="#ffe0c0")
bs.write(sb, "work/x.brc")                           # .brc + x.brc.render.json (AA)
bs.render("work/x.brc", "work/x.bmp", 512)           # or bs.render(sb, "work/x.bmp", 512)
```

| function | does |
|---|---|
| `set_document(scene, w, h, render_scale=1, antialias=None, mode=None)` | brycedocset size/aspect/render size; AA ('off'/'normal'/'supreme') and render mode ('mask'/'distance'/'altitude') kept as session options |
| `write(sb, path)` | write .brc plus the `.render.json` sidecar with the session options |
| `render(scene_or_path, out_bmp, width, antialias=None, mode=None)` | restart Bryce, open, set Render Options menu items, Render to Disk, wait until the BMP is closed |
| `get_document(scene)` | dict of the docset fields |
| `group(sb, objs, booleans=None, name="", material=None)` | C3dGroupType; `booleans` = list parallel to objs or {oid: kind}, kinds 'positive'/'negative'/'intersect'/None |
| `members(group)` | [(tag, oid)] |
| `set_attributes(obj, boolean=, locked=, show_as_box=, selected=, family=, family_rgb=, name=)` / `get_attributes(obj)` / `set_name(obj, s)` | header fields of §1 |
| `add_light(sb, kind='sphere'|'spot'|'cube', offset, rotate, size, color, intensity, softness, visible, shadows, falloff, name)` | light from template; intensity/softness in dialog units |
| `set_light(obj, ...)` / `get_light(obj)` | edit an existing light |
| `set_sky(sb, mode, shadows, ambient, fog, fog_height, fog_color, haze, haze_color, cloud_cover, cloud_height, frequency, amplitude, cumulus_color, stratus, cumulus, link_sun, background, custom1..3, sun, sun_color)` / `get_sky(scene)` | dialog units, converted per §4 |
| `set_sun(sb, toward, color, custom1)` | sun record |
| `set_camera(sb, position, look_at=None, forward=None, hfov=None, fov=None, panorama=None)` | camera; `hfov` is converted with the 0.8 factor |

Colours accept `(r, g, b)` floats 0–1 or `'#rrggbb'`.
