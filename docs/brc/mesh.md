# Triangle meshes: C3dTriMeshType (`3dobtmsh`)

Status: **V** = verified by a Bryce render or a differential save, **P** = plausible, **?** = unknown.
Code: `harness/bryce_harness/brc_mesh.py` (codec, `add_mesh`, generators). Templates:
`brc_templates/C3dTriMeshType.head` (bytes 0x000–0x2ef of PINE.BRC id 40) and `C3dTriMeshType.tail`
(the 48-byte instance-table row tail). Test scripts and renders: `work/re_mesh/`.

## 1. Record (slot A; slot B is empty)

Size = 0x308 + 24·vcap + 24·ncap + 76·fcap. This holds for all 232 meshes in the CD samples (V).

| offset | type | field | status |
|---|---|---|---|
| 0x000–0x2eb | | common object header and LE transform block, the same as the primitives (brc-format.md §3, §4). Material ref: BE u32 at 0x94 | V |
| 0x088 | BE u32 | 1 when the object was selected at save time. Bryce wrote 1 after the Smooth edit; it is 0 in every sample object. Write 0 | P |
| 0x2e0 | LE u32 | object family index (common header, also in primitives) | P |
| 0x2e4 | 4 B | family wireframe colour R,G,B,0 (common header) | P |
| 0x2ec | u8 | 1 in every mesh, 0 in primitives. Written as 1 | ? |
| 0x2f0 | BE u32 ×2 | vertex array: capacity, count | V |
| 0x2f8 | BE u32 ×2 | normal array: capacity, count. 0,0 until the mesh is smoothed | V |
| 0x300 | BE u32 ×2 | face array: capacity, count | V |
| 0x308 | vcap × 3 LE f64 | vertices (x, y, z) in object space | V |
| … | ncap × 3 LE f64 | corner normals in object space | V |
| … | fcap × 76 B | faces, see §2 | V |

- Unused capacity slots are zero-filled. Capacity = count is accepted (V). When Bryce saves, it rounds capacities up
  to a multiple of 50 or 16.
- **Object space (V).** Bryce normalises every mesh to −1024…+1024 on each axis independently,
  so the bounding box always fills that cube and the proportions sit in the transform's scale.
  Values are float32 cast to f64.
- **Scale (V).** Bbox extent in B = 2 · 1024 · scale · 10.24, so an object coordinate c is c · scale
  internal units, the same convention as a C3dSphere's Size (= 2 · scale · 10.24 for its ±1 space). `add_mesh(size=…)` is therefore
  the rendered bbox extent in B. Checks:
  - `t9.png`: a mesh sphere and a primitive sphere, both Size 20.48, have the same diameter.
  - `t8_pair.png`: a mesh ellipsoid and `add('sphere')`, both size (40,10,20) with rotate (0,0,30), render
    identically except for 14 of 117k object pixels. That one test confirms size, offset, rotation order and that Bryce
    transforms the stored normals correctly under non-uniform scale.
  - (The raw C3dCube template is half-size, 2 · scale · 10.24 = twice its extent. SceneBuilder.add now corrects this.
    An early "pixel-identical to a cube" check had calibrated the mesh against that cube and was wrong by 2×.)

## 2. Face record (76 bytes, big-endian)

| +off | type | field | status |
|---|---|---|---|
| +0 | u32 ×3 | vertex indices i0, i1, i2 | V |
| +12 | u32 ×3 | normal indices n0, n1, n2 into the normal array (0,0,0 when unsmoothed) | V |
| +24 | f64 ×3 | face normal = normalize(cross(v1−v0, v2−v0)), object space. All 52k sample faces match within 1e-6 | V |
| +48 | u32 ×3 | per-corner flag: 1 = the corner uses the face normal, 0 = it uses normal[n_k] | V |
| +60 | u32 | smooth switch: corners are smooth only when this is 1. As imported: 0. Smooth sets the face to (0,0,0,1), Unsmooth to (1,1,1,1) (code 0x454df0). INVASION and SULFURIC have (1,1,1,1), i.e. they were unsmoothed | V |
| +64 | u32 | runtime pointer to the face's material, set for all faces on load (0x453d10). 0 works | V |
| +68, +72 | u32 ×2 | more runtime pointers (+68 differs per face, +72 is the same for the whole object). 0 works | V |

Render test of the flags (t6_*.bmp, the same rounded box with valid corner normals):
(0,0,0,0) ≡ (1,1,1,1) → flat, pixel-identical; (0,1,1,1) → only corner 0 smooth (partially smooth);
(0,0,0,1) → fully smooth (t3rb). So a corner is smooth iff its flag is 0 **and** +60 = 1.

Winding: write faces so that cross(v1−v0, v2−v0) points outward. The renderer is a ray tracer, so
open or inverted meshes still render, but corner normals decide the shading and refraction, so keep them outward
and keep glass meshes closed.

## 3. Smoothing: Objects > Edit Object… (Ctrl+E) on a mesh opens the "Polyhedrons" dialog

The dialog has **Smooth** and **Unsmooth** buttons, a 0°–180° slider (the crease angle) and a polygon count.
Differential save (ui1.brc → ui1_smooth.brc, 972 faces):
- one normal per face corner (count = 3 × faces = 2916, cap 2950). Corner k of face j gets index 3j + k.
- face flags (1,1,1,0) → (0,0,0,1).
- each normal is the unweighted average of the neighbouring face normals within the crease angle
  (loop at 0x454bb9), not renormalised (|n| ≈ 0.99).

`corner_normals()` (angle-weighted, renormalised) agrees with Bryce to 0.27° on average and 3.3° at worst.
In memory: normals count/data at object +0x46c/+0x470, faces at +0x478/+0x47c (P).

## 4. Import formats (Bryce 2.1 Windows)

The Plugins folder holds `DXFImport.bro` and `3DMFImport.bro`, so File > Import reads DXF and 3DMF
(QuickDraw 3D metafile). "Object presets (*.obj)" is Bryce's own object library, not Wavefront OBJ.
Import is unnecessary, since records are written directly.

## 5. Python API (`brc_mesh.py`)

```python
from bryce_harness import brc, brc_mesh as M
sb = brc.SceneBuilder()
v, f = M.capsule(w=4, h=1, segments=64)                   # unit-free, long axis = x
M.add_mesh(sb, v, f, offset=(0, 10.24, 0), size=(48, 12, 12), material=GLASS,
           smooth=True, normals=M.capsule_normals(v, 4, 1))
```

- `add_mesh(sb, vertices, faces, offset=None, rotate=(0,0,0), size=None, material=None, smooth=True, crease_deg=60, normals=None, name="") -> brc.Obj`
  - vertices are in B, faces index them.
  - offset = bbox centre in B (default: the vertices' own). size = bbox extent in B (default: the vertices' own).
    Rotation is about the bbox centre, in degrees, X then Y then Z.
  - smooth: write corner normals. They are averaged within crease_deg, or taken from `normals`, which can be per vertex (N,3) or
    per corner (M,3,3) in the vertices' space. Exact normals are only right when `size` keeps the
    vertices' proportions; with averaged normals any size works.
- `capsule(w, h, depth=None, segments=32, cap_segments=None)` + `capsule_normals(v, w, h, depth)`: pill
  along x, cylinder body and semi-ellipsoid caps, one closed surface.
- `rounded_box(w, h, d, r, segments)` + `rounded_box_normals(v, w, h, d, r)`: flat faces stay 2 triangles
  per span; `segments` steps per 90° of the arcs.
- `superellipsoid(rx, ry, rz, e1, e2, nu, nv)`: e = 1 gives an ellipsoid, about 0.2–0.35 a soft box.
- `extrude(polygon_2d, depth, bevel=0, bevel_segments=3)`: simple polygon without holes, extruded along z with
  a rounded bevel on both caps. The front cap faces −z. Use `crease_deg` ≈ 50 so the outline corners stay crisp.
- `rounded_rect_outline(w, h, r, segments)`, `star_outline(n, r_out, r_in)`, `weld(v, f)`.
- Codec: `encode`, `decode`, `mesh_record`, `corner_normals`.

All generators were checked to be watertight, consistently wound, with positive volume.

## 6. Limits and cost

- Largest sample mesh: 3360 vertices / 7440 faces. Written meshes of 40k faces load and render correctly (t7_40k).
- **Render cost grows linearly with face count**, which suggests brute-force triangle tests inside a mesh (P).
  Opaque smooth superellipsoid 30 B across, camera at 80 B, 480 px, total job time including the Bryce restart:

  | faces | job time (s) |
  |---|---|
  | 1 848 | 60 |
  | 9 800 | 178 |
  | 39 600 | about 620 |

  So keep sprite meshes at a few thousand faces and let corner normals carry the smoothness.
  No hard vertex limit was found; the u32 counts allow far more than is practical.
- Record size is about 24·V + 152·F bytes with smoothing (+72·F for the normals). 40k faces is about 6 MB.
  `encode` takes about 1 s per 40k faces (pure numpy plus a per-vertex loop).
- No pointers need to be valid. The table-row tail is copied from the sample file.
- Glass (transparent and refractive) meshes render slowly. A 64-segment pill at 640 px takes several minutes.
- A mesh flat on one axis gets a nominal half-extent. Prefer thin solids.

## 7. Open questions

- Byte 0x2ec (= 1 in meshes, 0 in primitives) has not been varied.
- Face +68 pointer: what it points to at runtime (irrelevant for writing).

## 8. Verification renders (work/re_mesh/)

| file | shows |
|---|---|
| `final_glass.png` | 48×12×12 B glass capsule (the main session's glass material) on a white backdrop: one closed surface, no inner seams |
| `t5cap.png` (partial) | for comparison, cylinder + 2 spheres: the inner sphere halves show through |
| `final_solid.png` | glossy smooth rounded box (48×16.8×12 B), extruded and bevelled star and rounded rectangle |
| `t2c.png` / `t3rb.png` | the same rounded box flat versus smooth (corner normals) |
| `t6_*.bmp` | face-flag semantics (§2) |
| `t8_pair.png` | mesh ellipsoid versus primitive sphere at size (40,10,20), rotate (0,0,30): identical |
| `t9.png` (partial) | scale calibration: primitive sphere, mesh sphere, raw cube (half-size), mesh cube |
