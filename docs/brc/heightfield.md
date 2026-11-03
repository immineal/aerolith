# C3dHeightField (`3dobhfld`): terrains and symmetrical lattices

Status legend as in `docs/brc-format.md`: **V** = verified by a Bryce render or a differential save,
**P** = plausible, not verified, **?** = unknown.
Code: `harness/bryce_harness/brc_hfield.py`. Templates: `brc_templates/C3dHeightField_terrain.{a,tail}`
and `C3dHeightField_lattice.{a,tail}` (the 848-byte headers of a terrain and a lattice that Bryce 2.1
created from the Create palette and saved; the grid is appended at write time).

## 1. Terrain vs. Symmetrical Lattice

The Create palette's "Symmetrical Lattice" is **not its own class**. It is a `C3dHeightField` with
the byte at 0x34c set to 1 (V: differential save of a Bryce-created terrain vs lattice, render, and
the executable: "select sym lattices" filters on `hfld` objects whose data struct has byte +0x60 = 1,
the terrain filter on +0x60 = 0). The undo entries "convert to sym lattice" / "convert to terrain"
most likely just flip the byte. One HF method writes 0 to +0x60 (0x40d93e), but the rest of the
conversion was not traced (P).

- Terrain: a solid. Walls run from the grid edge down to height 0, and the h = 0 floor is a face (V).
- Lattice: the surface is mirrored below local y = 0, giving a closed lens. Areas with h = 0 have zero
  thickness but still render as a flat sheet unless clipped (V, edge-on render).

## 2. Record layout

Record size = 848 + 2·N² bytes. The first 0x2ec bytes are the header that all `3dob*` objects share
(primitives are 0x2ed = 749 bytes). Bryce keeps the rest (0x2ec onward) in a separate data struct
(`[object+0x458]` in memory); "struct +x" below means file offset 0x2ec + x.

| offset | type | field | status |
|---|---|---|---|
| 0x000 | char[128] | name (empty for Create-palette terrains) | V |
| 0x080 | char[8] | tag `3dobhfld` | V |
| 0x088 | u32 BE | 1 in a freshly created object, 0 in all but one sample (selection state?) | P |
| 0x08c | u32 BE | object flags, shared with primitives (samples: 4, 8, 0x10, 0x24, 0x48; 0 when Bryce 2.1 creates one). Not heightfield-specific | ? |
| 0x090 | `base` + u32 BE | material object id | V |
| 0x098 | 3×f64 BE | (1, 1, 1), same in primitives | ? |
| 0x0e0 | 3×f64 BE | **pivot** in grid units. Bryce writes (N/2, N/2, N/2); primitives have 0. The renderer uses it (zeroing only this triple moves the object by pivot·scale) | V |
| 0x158 | 9×f64 LE | identity 3×3 (one −0.0), same in primitives | ? |
| 0x1a0 | 3×f64 LE | copy of the pivot. Ignored on load (zeroing it alone changes nothing) | V |
| 0x1bc–0x2db | | transform block (scale, rotation, position, cached matrix), see brc-format.md §3 | V |
| 0x2e0 | u32 + 3 B | wireframe family index + RGB (0x555555 for a new object; samples: 1/000000, 2/ff0000, 3/ff8000, 5/00809d, 7/800040), shared with primitives | P |
| 0x2e8 | u32 | 0 | ? |
| 0x2ec | u8 (struct +0x00) | **grid format**: 1 in every file. 0 makes Bryce read the samples ×4 (14-bit heights, overflow wraps: a 0..1 ramp renders as 4 saw teeth); 2 renders like 1. Keep 1 | V (render), P (meaning) |
| 0x2f0 | 3×f64 BE (+0x04) | local bounding box min. Terrain (0,0,0); lattice (0,−N,0) | V |
| 0x308 | 3×f64 BE (+0x1c) | local bounding box max. Terrain (N−1)×3; lattice N×3 | V |
| 0x320 | 3×f64 BE (+0x34) | 0 in every file. Setting it to (20, 20, 20) changed nothing in a render | ? |
| 0x338 | f64 BE (+0x4c) | **clip low**, normalized height. Bryce 2.1 writes −0.01 | V |
| 0x340 | f64 BE (+0x54) | **clip high**. Bryce 2.1 writes 1.01 | V |
| 0x348 | u32 BE (+0x5c) | **N**, grid resolution (the grid is always square) | V |
| 0x34c | u8 (+0x60) | **symmetric**: 0 = terrain, 1 = symmetrical lattice. 0x34d–0x34f are 0 | V |
| 0x350 | u16 BE [N][N] (+0x64) | **height grid**, row-major. 0 = lowest, 65535 = highest | V |

The 48-byte instance-table tail (`.tail`) is kept from the Bryce-saved templates, as for primitives.

## 3. Geometry (V, renders against marker spheres)

For grid sample `g[i][j]` (i = row, j = column):

    local = (x = j,  y = g/65535 · (N−1),  z = i)            lattice: also (j, −y, i)
    world = position + R · diag(scale) · (local − pivot)

- Rows run along +Z (row 0 at −Z) and columns along +X (column 0 at −X), seen with the Y axis up.
- Heights span the same number of units as the grid does: full scale = N−1 grid units. A Bryce-made
  terrain has scale (8/127, 2/127, 8/127) internal units per grid unit at N = 128, so it is 81.92 B
  wide and 20.48 B high (8 and 2 internal units). A Bryce-made lattice has (4/128, 1/128, 4/128) at N = 128.
- With Bryce's pivot of N/2 the footprint spans −N/2 … N/2−1 cells around the position, so it is
  half a cell off-centre (V: spike-apex render at N = 32). `brc_hfield` writes the pivot
  ((N−1)/2, 0, (N−1)/2) instead, so `offset` is the centre of the footprint at height 0 (the mirror
  plane for a lattice), and the extent is exactly `size`.
- The scale/rotation/position block is the same as for primitives (brc-format.md §3), with the
  same X-then-Y-then-Z rotation order. `rotate=(-90, 0, 0)` turns the heights toward a camera on −Z;
  `brc_hfield` then reverses the rows so that an image reads upright and is not mirrored (V: the
  letter "R" render).

## 4. Clipping and the bounding box

- **Clip** (0x338/0x340): parts of the surface below `lo` or above `hi` (normalized heights) are cut
  away, leaving an open surface (V, ramp render). In the intersector both values are multiplied by an
  integer height range before use (0x40dce7/0x40dcfc in Bryce2.exe). Useful values:
  - `(0.002, 1.01)` removes the h = 0 floor of a terrain, leaving only the raised shape: this is what
    turns a heightfield into a free-standing button or glyph. On a lattice it removes the
    zero-thickness sheet around the shape and leaves a closed pillow.
  - Sample scenes from Bryce 2.0 store clip in 16-bit sample units (−0.0001 / 65536.0000016, or a
    floor cut such as 1983.9999 / 3967.9999). Bryce 2.1 does **not** convert them: re-saving keeps the
    values unchanged, and a low clip above 1 hides the whole object (V: INVASION.BRC terrain 82 renders
    nothing as stored; the full sample scene renders without its four "city" terrains). Dividing by 65535
    gives the intended look (V: city towers with the floor cut away). `fix_legacy_clip(rec)` does that.
    Samples with clip ≠ default: AFRICAN, EGGWORLD, EUROPA, INVASION, MAGICAL(2,3), PIPELIN(E,2),
    ROCKSHOR, TRAFFIC(T).
- **Bounding box** (0x2f0/0x308) does not move or scale anything (V: changing the min or max moved
  nothing), but the renderer clips rays to it. With Bryce's own max of N−1, the +X and +Z edge cells
  lose one triangle each (a sawtooth along those two edges, plus thin slits in the side walls). With
  the max set to N (as Bryce itself writes for lattices) the edges are clean (V, zoomed renders).
  `brc_hfield` writes min (0, 0, 0) for a terrain, (0, −N, 0) for a lattice, and max (N, N, N).

## 5. Rendering behaviour and quality

- Shading normals are interpolated across the grid, so surfaces look smooth rather than faceted (V).
- Resolution: N = 32, 64, 128, 256 and 512 load and render, and so does a non-power-of-two N = 100 (V).
  N = 16 is rejected: Bryce silently keeps the previous scene (V). N = 1024 loads and renders, but the
  object comes out slightly smaller and shifted, so `brc_hfield` stays within 32..512 (open question).
  The samples only use 64, 128, 256 and 512, and the Create palette makes 128.
- Stair-stepping and ripples come from the edge profile, not from N alone:
  - A quarter-circle edge (vertical tangent at the outline) shows ripple bands and a jagged clip contour
    at N = 256, and still some at 512.
  - A profile with a finite slope at the outline (`ease` = 1−(1−t)³) or a zero slope (`pillow` =
    cosine) renders clean at N = 512 (V, zoomed corner renders `work/re_hf/e7_*.png`).
  - Glyphs: a distance field computed from an aliased binary mask has a staircase that shows up as
    ripple bands on a steep bevel. Draw the mask 4× larger, average the signed distance down, and blur it
    by about 0.7 px (`signed_distance(..., ss=4, blur=0.7)`).
- Use N = 512 for anything that fills more than about 200 px of the final sprite.
- Quantisation: 16 bits per sample, so a 4 B tall button has height steps of 0.00006 B. This is never
  visible.

## 6. Round trip, and what is still open

- **Round trip (V):** Bryce 2.1 opened a scene written by `brc_hfield` (pivot ((N−1)/2, 0, (N−1)/2),
  bbox max N, clip 0.002) and re-saved it with the header and grid byte-identical. It also re-saves the
  Bryce 2.0 samples' heightfield records unchanged.
- **How the executable stores it (V):** in memory the object tag sits at `[obj+0xac]` (file 0x80 → memory
  +0x2c). The heightfield data (file 0x2ec…) is a separate struct at `[obj+0x458]`. The intersector
  (around 0x40dc00) reads clip at struct +0x4c/+0x54 and the lattice flag at +0x60. Select-by-type uses
  the pseudo-types `hfld` (terrains: +0x60 = 0) and `hmys` (lattices: +0x60 = 1). The C3dHeightField
  vtable is at 0x55ead4 and its methods are around 0x40c000–0x40f000.
- Open:
  - What Bryce's Object Attributes dialog shows as "Size" for a terrain. The dialog did not paint under
    Wine during this session. Probably scale·bbox extent·10.24 (P).
  - 0x320 triple, the 0x088 word, and the 0x098 triple (shared with primitives).
  - Why N = 1024 renders off-size.
  - Texture mapping on terrains (altitude-based textures in the samples, e.g. "Basic Altitude30")
    belongs to the material/texture records, not to this one.
  - The Terrain Editor (`CTerrainEditor`, `terraineditor.dat`) only rewrites the grid. Its filters and
    erosion leave no other trace in the record (P: the header has no other fields that vary across
    the 288 sample heightfields).

## 6a. Bryce-created defaults (differential saves)

| | N | pivot | bbox | scale (per grid unit, internal) | position (B) | clip |
|---|---|---|---|---|---|---|
| Create > Terrain | 128 | 64 | (0,0,0)–(127,127,127) | (8/127, 2/127, 8/127) | (0, 11.264, 0) | −0.01 / 1.01 |
| Create > Symmetrical Lattice | 128 | 64 | (0,−128,0)–(128,128,128) | (4/128, 1/128, 4/128) | (0, 31.744, 0) | −0.01 / 1.01 |

The two records differ only in 0x34c, the bbox, the scale and the position. Both use the default grey
material (identical to `brc_templates/C3dBaseMaterial.a`). Across the 288 sample heightfields only these
header bytes vary: the object flags (0x08b, 0x08f), the material id, the pivot (N/2), the transform, the
family/colour (0x2e0–0x2e6), the bbox (N−1), the clip and N.

## 7. API (`brc_hfield.py`)

```python
from bryce_harness import brc, brc_hfield as hf
sb = brc.SceneBuilder(); sb.sky(haze=0)
h = hf.rounded_rect(512, 200, radius=90, bevel=70, profile="ease")   # float 0..1 image
hf.add_heightfield(sb, h, offset=(0, 0, 0), rotate=(-90, 0, 0),      # face a camera on -Z
                   size=(40.96, 4.0, 16.0),                          # width, height of 1.0, depth (B)
                   material=dict(diffuse="#2a7fff", specularity=1.0, reflection=0.2),
                   clip=(0.002, 1.01),                               # drop the h=0 floor
                   symmetric=False)                                  # True = symmetrical lattice
```

- `make_record(heights, offset, rotate, size, symmetric, clip, n, pivot="base"|"bryce", bbox="full"|"bryce")`
  returns the raw record. `heights` can be any shape and is resampled to the smallest supported N that
  is at least as large (cubic spline up, Lanczos down), or to `n`.
- `rounded_rect(w, h, radius, bevel, profile)`, `from_mask(mask, bevel, profile, ss, blur)`,
  `signed_distance(mask, ss, blur)`, `shape_profile(t, profile)` with profiles `ease`, `pillow`,
  `round`, `linear`.
- Reading: `info(rec)`, `grid_of(rec)` (raw u16 as stored), `heights_of(rec)` (back to the image
  convention).

## 8. Verification renders (`work/re_hf/`, scripts alongside)

| file | what it shows |
|---|---|
| `exp2t.png`, `exp2s.png` | top and side views against marker spheres: axes, extent (N−1)·scale, height mapping |
| `e5_grid.png` | spike at N = 32: the pivot is the 0xe0 field (N/2), there is no half-cell offset, apex height = (N−1)·g/65535 |
| `e4_grid.png` | header differentials: bbox min/max, pivot BE vs LE, clip |
| `e6_grid.png`, `e7_grid.png` | terrain vs lattice, clip floor, edge-on lattice, resolution and profile comparison |
| `e9_grid.png`, `e10_grid.png`, `e11_grid.png` | Bryce 2.0 clip units, 0x2ec, N = 100 / 1024 |
| `fin_pillow_front.png` | (a) rounded-rectangle pillow button, glossy, N = 512, `ease` profile, floor clipped |
| `fin_glyph_front.png`, `fin_glyph_34.png` | (b) embossed "R" on a rounded plate (mask drawn at 2048 px, ss = 4) |
| `fin_lattice_34.png`, `fin_lattice_edge.png` | (c) the same pillow as a symmetrical lattice: a closed lens, both halves visible edge-on |
