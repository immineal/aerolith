# Bryce 2 materials, textures and pictures (.BRC)

Status: **V** = verified by a Bryce render or a differential save (composer edit, save, diff) ·
**P** = plausible (corpus statistics, menu order, consistency) · **?** = unknown.
Code: `harness/bryce_harness/brc_material.py` (imports `brc.py`, does not change it).
Container, object store and transforms: `docs/brc-format.md`.

## 1. Object graph

```
primitive (0x90 'base', 0x94 oid) -> C3dBaseMaterial (568 B)
C3dBaseMaterial slot A..D        -> C3dTexture   'brtx'  (1216 B, procedural "3D texture")
                                 -> CPictTexture 'pctx'  (136 B)  +  C3dCImage, SAME object id (pixels)
```

Every object is a 60-byte row in the object store (oid, slot A, slot B, 48-byte tail; tails can be
zero for objects we create, V). Object ids are global; library files (.shd, textures.dat) use large
hash-like ids, so `transplant_material` gives fresh ids and rewrites the slot references (V).

## 2. C3dBaseMaterial (568 B, big-endian except bump)

Dialog values 0..255 are stored as 0..1 (the composer quantises to x/255 when OK is pressed, V).

| offset | type | field | status |
|---|---|---|---|
| 0x00 | char[128] | name ("Untiteld_Material" in Bryce's own scenes) | V |
| 0x80 | char[8] | tag `matrbase` | V |
| 0x88 | char[4] | `phex`, constant in all 3,163 corpus materials | V (constant) |
| 0x8c | 10 × i32 | channel drive modes, order: diffuse colour, diffusion, ambient colour, ambience, specular colour, specularity, transparent colour, transparency, reflection, bump. 0 = own value, 1..4 = texture A..D | V |
| | | 5 and 6 appear only in materials with all four slots filled, and then the bump word holds -1/-2/-3/-101/120 | ? |
| 0xb4 | 28 B | zero in corpus | V (constant) |
| 0xd0 | u32 | flags: bits 0-2 shading mode (0 normal, 1 additive, 2 fuzzy, 3 fuzzy additive, 4 light, 5 blend) | V (render, modes 0-5) |
| | | 0x08 "Distance Filter": changes how the transparent colour tints (a 10-unit cube rendered pale instead of saturated) | V effect, P name |
| | | 0x10 "Shadowable": no visible effect in normal, fuzzy or light mode (mirror-symmetric A/B renders are pixel-identical) | P name, ? effect |
| | | 0x40 set by the composer whenever a texture slot is filled | V (diff) |
| 0xd4 | 3 × f32 | diffuse colour | V |
| 0xe0 | f64 | diffusion | V |
| 0xe8 | 3 × f32 | ambient colour | V |
| 0xf4 | f64 | ambience | V |
| 0xfc | 3 × f32 | specular colour | V |
| 0x108 | f64 | specularity | V |
| 0x110 | 3 × f32 | specular coefficients, stored = 255 − dialog value (dialog 205 → 50.0) | V (205↔50), P (formula) |
| 0x11c | 3 × f32 | transparent colour | V |
| 0x128 | f64 | transparency | V |
| 0x130 | f64 | reflection | V |
| 0x138 | f64 **little-endian** | bump height = dialog/255 (may be negative). `brc.py` writes it big-endian, which is wrong | V (diff + render) |
| 0x140 | f64 | refraction index / 100 (1.0 = air) | V |
| 0x148 | 8 B | zero in corpus | V (constant) |
| 0x150 | f64 | becomes 0.8 after OK in the composer (0 in every corpus record); "Metallicity: %ld" exists in the composer resources. Values 0, 0.5, 1, 2 render the same | ? |
| 0x158 | 4 × f64 | zero, except in 3 corpus records (0.33, 0.8, 0.33, 4.0) | ? |
| 0x178 + 48·k | 48 B | texture slot k = A..D, see below | V |

Texture slot (48 B, big-endian):

| +off | type | field | status |
|---|---|---|---|
| +0x00 | char[4] | `brtx` (C3dTexture) / `pctx` (CPictTexture) / zero = empty | V |
| +0x04 | u32 | object id of the texture | V |
| +0x08 | f64 | frequency. Composer slider quantised to x/99 (default 0.505 = 50/99) | V |
| +0x10 | 24 B | zero (a few corpus records hold junk) | P |
| +0x28 | i32 | mapping: 0 object, 1 world (default), 2 parametric, 3 parametric scaled, 4 world top, 5 spherical, 6 cylindrical, 7 reflection map, 8 random, 9 object top, 10 object front | V (diff for each) |
| +0x2c | i32 | symmetric tiling (alternate tiles mirrored) | V (render) |

Shading (V): light is additive. What shows through a transparent surface gets the surface's
diffuse and ambient light added on top. A clear glass needs low diffusion. A picture with alpha needs premultiplied RGB (section 4).
Shading modes as rendered over black and white stripes (`work/re_mat/alpha_shading.png`):
normal = opaque; additive = colour added to the background; fuzzy = soft edges; fuzzy additive = both;
light = unshaded, see-through glow, casts and receives no shadows (`flags_plain_light.png`); blend = flat colour
mixed with the background.

## 3. Pictures: CPictTexture + C3dCImage

* **CPictTexture** (136 B): name[128] + tag `txtrpctx`. Nothing else (V: zeros work).
* **C3dCImage**, same oid as its CPictTexture:
  * slot B (80 B): `imge` `iv32`, u32 4 (bytes/pixel), width, rowbytes (= 4·width), height, 8 zero
    bytes, Rect (top, left, bottom, right) = (0, 0, height, width) at 0x20, rest zero (V).
  * slot A: `arle` + 60 zero bytes, then 4 planes **A, R, G, B** (height × width, top row first),
    each run-length coded on its own: byte n < 0x80 → n copies of the next byte; n ≥ 0x80 → n − 0x80
    literal bytes. Bryce never crosses a plane boundary, runs ≤ 126, literals ≤ 125 (V: our encoder
    reproduces 99 of 105 corpus images byte for byte; all 105 decode; our images render).
  * The same codec stores the 96×96 preset thumbnails (`matprevcimage`) and the pictures in
    textures.dat (`ImageIV32ARGB`).

Behaviour (all V by render):

* **Parametric mapping** maps the whole image onto each face, stretched to the face (a 2:1 square
  shows the image stretched 2:1). On a `square` rotated x = −90 and seen from −Z, the image's top-left is at the top left.
  A cube shows the full image on each face. A sphere wraps it around.
* **Repeats** per face with parametric mapping = 1 + round(20 · frequency): 0, 0.01, 0.02 → 1;
  0.05 → 2; 0.1 → 3; 0.2 → 5; 0.3 → 7; 0.4 → 9; 0.5 → 11; 0.6 → 13; 0.8 → 17; 1.0 → 21 (`freq2.png`).
  Symmetric tiling mirrors alternate tiles, and the tile grid is then shifted by part of a tile.
* **Alpha**: with transparency driven by the picture, alpha 255 = opaque and 0 = fully see-through. The
  rendered result is `background·(1−α) + RGB·ambience (+ diffuse light)`, linear in α to within 1–3 levels (`premul.png`).
  So store **premultiplied** RGB (`add_picture` does this by default) and set diffusion 0, ambience 1:
  the result is exact "over" compositing, and pixel colours come out unchanged (`api_demo.png`).
* Object-front / object-top on a flat square project along an in-plane axis and show streaks. Use
  parametric for sprites.
* Bryce's own picture materials (corpus): drive diffuse colour, (diffusion), ambient colour and
  transparency from A, flags 0x48, mapping object top with frequency 0.01, or parametric with frequency 1.0.

## 4. C3dTexture (1216 B, procedural)

Big-endian. Up to three noise "components" combined into an output. The editable fields below are
verified by render against a baseline render of the same scene (world mapping depends on position, so cells must be compared at the same position).

| offset | type | field | status |
|---|---|---|---|
| 0x00 | char[128] | name | V |
| 0x80 | char[8] | `txtrbrtx` | V |
| 0x88 | i32 | number of components combined, 1..3 (1 → only component 0 shows, in its own colours) | V |
| 0x8c..0xb8 | i32s | 0x8c ∈ {1..7}, 0x90, 0x94 (various), 0x98/0x9c ints, 0xa0 = global angle (cached matrix = Rz(90°+angle)·scale), 0xa8 3 × i32 global scale | P (layout); changing scale ×4 had no visible effect (?) |
| 0xbc, 0xc0 | f32 | | ? |
| 0xcc..0xd4 | 3 × u32 | colour-like values; changing them had no visible effect | ? |
| 0xd8 + 0x110·k | 272 B | component k = 0..2 | |
| +0x00 | i32 | type 1..7 (changing 6 → 1 changed the look; 6 → 2/3/7 did not) | ? |
| +0x04 | i32 | 0 or 4 | ? |
| +0x08 | i32 | packed value (e.g. 277, 1050) | ? |
| +0x0c, +0x10 | i32 | two angles in degrees (go into the cached matrix) | P |
| +0x14 | 3 × i32 | frequency multipliers x, y, z: larger = finer pattern | V |
| +0x20..+0x2c | i32 | | ? |
| +0x30 | 3 × i32 | second triple: changes the pattern | V |
| +0x3c, +0x40 | i32 | | ? |
| +0x44 | f32 | small effect when doubled | V (effect) |
| +0x48 | f32 | | ? |
| +0x4c | i32 | | ? |
| +0x50 | u32 | flag 0x40 in some textures | ? |
| +0x54 | 3 × u32 | colours 0x00RRGGBB | V (components 0, 1) |
| +0x60, +0xb8 | 9 × f64 | cached matrices: recomputed on load, edits ignored | V |
| +0xa8, +0x100 | u32 | pointer-like junk | P |
| 0x408..0x4bf | | global section: colour, 4 × f64, cached 3×3 matrix at 0x42c (ignored, V), ints 0x47c..0x4a4 | P |

The slot frequency multiplies texture coordinates (0.25 gives larger features than 0.505, V).
The Deep Texture Editor UI exposes turbulence, complexity, randomize and per-component colour/alpha/bump outputs.
Its noise-type controls are graphical, so component types 1..7 are not named yet.

Library: `wine/bryce2/Data/textures.dat` (CCmF) holds 105 named C3dTexture records
(`bm.texture_names()`), plus the pictures "leo" and "alpha test" as `ImageIV32ARGB`.

## 5. Preset materials (Materials palette)

* Location: `wine/bryce2/Bryce2 Support Files/*.shd`. They use the same CCmF object-store format as .BRC. For
  each preset there is a `CPresetDescr` (name in bytes 0..0x40, description from 0x40), a `C3dBaseMaterial`
  and a `matprevcimage` (96×96 ARLE thumbnail), all with the **same oid**, plus the C3dTexture /
  CPictTexture + C3dCImage objects the slots reference.
* `Basics.shd` and `User.shd` use the older "0.02__ot" stream (`obBc` records of 518 B with material only, 750 B with a texture, or 2–3 KB with a picture).
  This stream is not decoded. `Simple&Fast.shd` has broken block chains, but `simple4.shd` is a clean copy.
* 317 presets in 10 libraries (266 named, 51 "Untitled Preset" that are real materials, reachable as
  `"Library/@index"`). Transplant = copy the material and its referenced objects with fresh ids and
  remap the slot oids. Verified by `work/re_mat/presets.png` (20 presets incl. textured ones; matches Bryce's
  own thumbnails `presets_thumbs20.png`) and `api_demo.png` ("Death Star in Progress", a picture preset).
  Note: world-mapped presets (Classic Checkerboard, Bathroom Tile) depend on object size/position; the
  thumbnails show finer checks than our 20.48-unit spheres.

## 6. API (`brc_material.py`)

```python
from bryce_harness import brc, brc_material as bm
sb = brc.SceneBuilder()
m = bm.material(sb, diffuse="#ffffff", diffusion=0.8, ambience=0.2, specularity=0.8, specular="#ffffff",
                spec_coef_dialog=205, transparency=0.0, transparent="#ffffff", reflection=0.3,
                refraction=1.33, bump=0.4, shading="normal", flags=0)          # every field
pic = bm.add_picture(sb, "sprite.png")                          # premultiplied, alpha kept
m = bm.sprite_material(sb, pic)                                 # exact picture (self-lit, alpha see-through)
m = bm.sprite_material(sb, "tile.png", repeats=4, tiling=True, lit=True, alpha=False)
t = bm.add_texture(sb, "Marble", colours={0: ("#0a3d8f", "#3fb8e8", "#ffffff")}, scale={0: 0.5})
m = bm.material(sb, textures={"A": bm.Slot(t, mapping="object", frequency=0.505)},
                drive={"diffuse_color": "A", "ambient_color": "A", "bump": "A"}, bump=0.5)
m = bm.preset(sb, "Mercury Surface", reflection=0.8)            # preset + overrides
m = bm.transplant_material(other_scene, oid, sb)                # any material from any .brc/.shd
bm.preset_names(); bm.texture_names(); bm.get_material(m.a); bm.get_texture(t.a)
bm.decode_image(obj); bm.encode_image(rgba); bm.frequency_for_repeats(n)
```

## 7. Pitfalls found on the way

* `brc.py` writes bump big-endian at 0x138; Bryce reads it little-endian. Use `bm.set_material(bump=…)`.
* If a session starts by loading a file and then creates several new textures, Bryce can save them with the same object id, and one is lost. Make one new texture per session in UI experiments.
* Materials Composer UI: clicking the title-bar triangle (728,311) leaves the composer stuck (clicks ignored,
  OK fails, and the save keeps the old material). Open the composer from the Edit palette's Materials button with the palettes at their
  original position. Move palettes only while the composer is open.

## 8. Open questions

* Drive modes 5/6 and the odd bump mode values (-1/-2/-3/-101/120) in 4-texture materials.
* 0x150 ("Metallicity"?): no visible effect found. 0x10 flag: no visible effect found.
* C3dTexture: component type names, the header ints 0x8c..0xb8 (global scale had no effect on Marble),
  0xcc..0xd4, the f32s, and how components are combined (combine mode, alpha/bump outputs).
* Old-format presets (Basics.shd, User.shd, "0.02__ot" stream).

## 9. Preset list (library: names, in file order)

- **Clouds&Fogs** (30): Low Grey Clouds, Night Clouds, Cloud Plane #1, Planet Atmosphere, Winter Cloud, Romantic Sunset, Cotton Ball Storm, Marbled Clouds, Phantom Cloud Plane, Phantom Clouds, Cotton Ball II, Tea Kettle Steam, Cotton Ball, Smoke Stack, Sunset Variation, Looking Down, Incoming Sunset, Low Frequency Summer, Matte Summer Clouds, Summer Clouds, Wispy Afternoon II, Wispy Afternoon, Untitled Preset, Untitled Preset, Untitled Preset, Untitled Preset, Untitled Preset, Untitled Preset, Untitled Preset, Untitled Preset
- **Complex fx** (33): Stars, GreenLit, Fuzzy Blue Sphere, Fire, Light Rays, Weather Map, Alien Disco Ball, OilyBronze, CopperBump, Jupiter, Luna, WaterPuddles, RainMap, Wild Mirror, Untitled Preset, Untitled Preset, Untitled Preset, Untitled Preset, Untitled Preset, Untitled Preset, Untitled Preset, Untitled Preset, Untitled Preset, Untitled Preset, Untitled Preset, Untitled Preset, Untitled Preset, Untitled Preset, Untitled Preset, Untitled Preset, Untitled Preset, Untitled Preset, Untitled Preset
- **Miscellaneous** (35): Moon Lava, Cracked Clay Pot, Acid Build-up, Moon Lava II, Giger's Moss, Gilliam's Barnacles, Pale Toad Skin, Desert I, Storybook Grass Map, City Lights Map, City Lights Map II, Emerald Mud, Luminous Moss, Foliage, Yellow Noyze, Foliage II, Bladerunner City Map, Space Base Map II, Organic City Map, Death Star in Progress, Steel Cage, Urban Dwelling Map, Gilded Cage, Urban Dwelling extra bump, Mud/Bark Fusion, Global Glow Ball #2, FlatLands, Untitled Preset, Untitled Preset, Untitled Preset, Untitled Preset, Untitled Preset, Untitled Preset, Untitled Preset, Untitled Preset
- **Planes&Terrains** (36): From Underneath, Clayground, Deep Mossy Grass, Classic Bryce Snow, Moonage Daydream, Legacy Snow., Rocks and Ice, Whole Mountain, Mossy Rock, Distant Mountain, Highlands, Shaman Cliffs, Mud and Snow, Grand Canyon, Volcano Heart, Fresh Clay, Etched Rock, Painted Desert Rock, Desert Rock, Grassy Peaks III, Grassy Peaks II, Antique Pots, Painted Desert, New Mexico Cliffs, Bright Beach Sand, Sandstorm, Iceberg, Winter Thaw II, Spring Thaw., Mid-Winter., First Snow, Grassy peaks., Wind blasted rock., Painted Desert, Arizona, Lowlands
- **Rocks&Stones** (33): Kryptonite, Freshly Dug Grave, Alien Sandstone, Cave Wall, Stone Wall (high frequency), Pitted Concrete, Gilliam's Riverbed, Stone/Wood, Stone Wall, Petrified Barnacles, Veiny Stone, Archeological Find, Abalone, Marble, Blue and White, Marble, White on Orange, Marble, Blue-Purple, Marble, Deep Rose, Granite, Eroded, Marble, Black on White, Marble/Bronze Fusion, Marble, Dali-esque, Marble, Pink, Marble, Red and White, Petrified Moss, Desert Sandstone, Barnacles, Pitted Granite, Sandstone, Eroding Cliff, Dried Mud, Wet Rock, Riverbed, Nasty Green Slime
- **Waters&Liquids** (15): Black Lagoon, Caribbean Resort, Deep Blue, Mercury Surface, Dull Mirror, Nightime Lake, Oasis, New Age Whale Picture, Wave Water, Iceberg, , , , , 
- **Wild&Fun** (33): Carnival Tent, Warm Gradient Stripes, Black and White Cage, Gilded Cage, Circus Beach Ball, Dali Bee Stripes, Clown Collar, Worker Bee Stripes, Lobby Carpet, Tyrell Building, Dentist Office Wallpaper, Bathroom Tile, Office Building, Office Building II, Office Building at Night, Alien Tree Bark, Amazonian Toad Skin, Cross-hatched Wood, Robot Fungus, What are you looking at?, Peeling Paint, Abalone 2, Untitled Preset, Untitled Preset, Untitled Preset, Untitled Preset, Untitled Preset, Untitled Preset, Untitled Preset, Untitled Preset, Untitled Preset, Untitled Preset, Untitled Preset
- **p&t** (36): Lowlands, Arizona, Painted Desert, Wind blasted rock., Grassy peaks., First Snow, Mid-Winter., Spring Thaw., Winter Thaw II, Iceberg, Sandstorm, Bright Beach Sand, New Mexico Cliffs, Painted Desert, Antique Pots, Grassy Peaks II, Grassy Peaks III, Desert Rock, Painted Desert Rock, Etched Rock, Fresh Clay, Volcano Heart, Grand Canyon, Mud and Snow, Shaman Cliffs, Highlands, Distant Mountain, Mossy Rock, Whole Mountain, Rocks and Ice, Legacy Snow., Moonage Daydream, Classic Bryce Snow, Deep Mossy Grass, Clayground, From Underneath
- **r&t** (33): Riverbed, Wet Rock, Dried Mud, Eroding Cliff, Sandstone, Pitted Granite, Barnacles, Desert Sandstone, Petrified Moss, Marble, Red and White, Marble, Pink, Marble, Dali-esque, Marble/Bronze Fusion, Marble, Black on White, Granite, Eroded, Marble, Deep Rose, Marble, Blue-Purple, Marble, White on Orange, Marble, Blue and White, Abalone, Archeological Find, Veiny Stone, Petrified Barnacles, Stone Wall, Stone/Wood, Gilliam's Riverbed, Pitted Concrete, Stone Wall (high frequency), Cave Wall, Alien Sandstone, Freshly Dug Grave, Kryptonite, Nasty Green Slime
- **simple4** (33): Mirrored Checkerboard, Classic Checkerboard, Specularity Lesson #7, Specularity Lesson #6, Specularity Lesson #5, Specularity Lesson #4, Specularity Lesson #3, Specularity Lesson #2, Specularity Lesson #1, Polished Walnut, Walnut Wood, Plank Wood, Bleached Wood, Light Wood, Warped Wood, Metallic Chrome, Mirror, White Metal, Yellow Gold, Pale Blue Metal, Warm Gold, Soft Yellow, Soft Magenta, Soft Cyan, Chocolate Brown, Bryce Blue-Green, Bryce TerraCotta, Shiny Blue Plastic, Shiny Green Plastic, Shiny Red Plastic, Full Black, Flat Gray, Flat White
