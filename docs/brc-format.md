# Bryce 2 scene format (.BRC), as reverse-engineered here

Status legend: **V** = verified by a Bryce render or a differential save · **P** = plausible, not verified · **?** = unknown.
Code: `harness/bryce_harness/brc.py` (container, object store, transforms, materials, camera, sun, sky, SceneBuilder).

## 1. Container: "CCmF" composite file (V)

- Magic string at 0 ("CCmF - Universal - Axiom - AGP - Composite File Management System ..."), and "Resource Composite File" at 0x200.
- Directory pointer at 0x248: three BE u32 values (flags, directory size, directory offset). Directory info at 0x260: (capacity, used entries, grow-by).
- Each directory entry is 12 bytes, BE u32 (flags, size, offset of the first block). Flag 0x01000000 = allocated.
- Every slot is a chain of blocks. A block header is 12 bytes, BE: (allocated size including the header, used bytes, offset of the next block, 0 = end).
- The writer rebuilds the whole file, with slots renumbered and blocks contiguous. Bryce accepts this.

## 2. Object store (V)

- Slot 16 is the class index: 32-byte rows of (class name 16 B, instance-table slot, table-header slot, 0, 0).
- Slot 17 is the class index's array header. All array headers are 8 BE u32: (item size, capacity, grow-by, count, 0…).
- An instance table is made of 60-byte rows: BE u32 (object id, slot A, slot B), then 48 bytes of what looks like uninitialised memory (kept as-is).
- Slot A holds the object record. Slot B is almost always empty (C3dCImage uses it).
- An object record (slot A) starts with a 128-byte name, then an 8-char tag at 0x80 (e.g. `3dobsphr`, `matrbase`, `lghtsunl`).
- Object ids are global. References between objects use them.

## 3. Transform block (V), shared by primitives, lights and cameras. Little-endian f64 (raw x86 doubles)

| offset | field |
|---|---|
| 0x1bc | scale xyz, internal units. Bryce "Size" = 2·scale·10.24 |
| 0x1ec | rotation xyz, radians, applied X then Y then Z |
| 0x204 | position xyz, internal units. Bryce "Offset" = pos·10.24 |
| 0x27c | cached 3×3 matrix = S·Rᵀ (Bryce recomputes it, but it is written anyway) |
| 0x2c4 | cached copy of the position |

## 4. Primitives (V)

These classes have 749-byte records: C3dSphere, C3dCube, C3dCylinder, C3dCone, C3dPyramid, C3dSquare (flat in XZ), C3dCircle (disk), C3dPlane (infinite ground). C3dTorusType has a 764-byte record.

**Size depends on the class (V).** Calibrated sheet, Size 40 requested with Size = 2·scale·10.24 for every class:

| class | rendered size |
|---|---|
| sphere, cylinder, cone, square, disk | 40 |
| cube, pyramid | 20 (their object space is ±0.5) |
| torus | 80, outer diameter |

`SceneBuilder.add` corrects for this with `SIZE_FACTOR`, so its `size` argument is always the rendered extent in B.

The material reference is at 0x94 (BE u32 object id), after the tag `base` at 0x90.

## 5. Material `C3dBaseMaterial` (568 B), big-endian

Dialog values 0..255 are stored as 0..1.

| offset | type | field | status |
|---|---|---|---|
| 0xd4 | 3×f32 | diffuse colour | V |
| 0xe0 | f64 | diffusion | V |
| 0xe8 | 3×f32 | ambient colour | V |
| 0xf4 | f64 | ambience | V |
| 0xfc | 3×f32 | specular colour | V |
| 0x108 | f64 | specularity | V |
| 0x110 | 3×f32 | specular coefficient (50.0) | P |
| 0x11c | 3×f32 | transparent colour (filters what shows through) | V |
| 0x128 | f64 | transparency | V |
| 0x130 | f64 | reflection | V |
| 0x138 | f64 | bump | P |
| 0x140 | f64 | refraction index (1.0 = dialog 100) | V |
| 0x150 | f64 | becomes 0.8 when transparency is set in the dialog; no visible effect | ? |
| 0x180, 0x1b0, 0x1e0, 0x210 | f64 + … | four 48-byte blocks, probably texture channels A–D (0.51 → 0.505 after edits) | ? |

Shading is additive: diffuse light is added on top of what shows through. A glass needs low diffusion and high transparency, otherwise it renders white (V).

## 6. Camera `C3dBaseCamera` (884 B)

The position is in the transform block. The aim comes from BE f64 vectors: forward at 0x2ec and up at 0x304 (V; changing only the transform did not move the view). FOV is a BE f64 in radians at 0x33c, default 60° (P). Cameras in a default scene: "perspective", "top", "right", "front", "left", "back", "bottom", plus 7 unnamed ones.

## 7. Sun `C3dSunLight` (832 B)

- 0x328: 3×f64 BE, unit vector pointing toward the sun (V, from the shadow direction).
- 0x2ec: 3×f32 BE = (1,1,1), probably the sun colour (P).

## 8. Sky `C3dBaseSky` (376 B), BE

- 0x144: f64, default 0.4. Haze. 0 removes all distance tint, so backdrops render exactly their colour (V).
- 0x8c: f64, default 9.77. Zeroing it removes a faint tint at the top of the frame (V, meaning unknown).
- Colours (f32 triples) at 0x94 (0.8 grey), 0xa0, 0xf4, 0x118, 0x124, 0x138, 0x14c (all ones); 0xec/0xf0/0x110/0x114 = 0.2 (?).
- f64 values: 0xbc 0.5, 0xc4 1.0, 0xcc 0.25, 0x11c 0.1, 0x130 1.0. Zeroing 0xbc, 0xcc, 0xc4, 0x11c or 0x130 had no visible effect on a backdrop-only test (?).

## 9. Decoded in detail elsewhere

- **Heightfields / symmetrical lattices** (`C3dHeightField`): [docs/brc/heightfield.md](brc/heightfield.md), code `brc_hfield.py`. The lattice is the same class with byte 0x34c = 1. The grid is u16 BE, N×N (N = 32–512).
- **Triangle meshes** (`C3dTriMeshType`): [docs/brc/mesh.md](brc/mesh.md), code `brc_mesh.py`. Vertices are LE f64 normalised to ±1024. Faces are 76 B BE records, and per-corner normals give smooth shading.
- **Materials, textures, pictures, presets**: [docs/brc/materials.md](brc/materials.md), code `brc_material.py`. 317 presets come from the `.shd` libraries. Picture textures are RLE planes, our own PNGs with alpha.
- **Lights, sky, groups / booleans, document settings, FOV**: docs/brc/scene.md (in progress).

## 10. Rendering facts (harness)

- Bryce 2.1 under Wine on Xvfb (`winebox.py`), with a fresh process per job (`bryce.render_job`). Render to Disk writes a BMP. Width is set in the dialog, and the height follows the document aspect (4:3 by default).
- Any keypress or click stops a render.
