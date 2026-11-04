# Bryce-rendered UI library: foundations

Working name: **Aerolith**. Every visible surface is a sprite pre-rendered in Bryce 2. The HTML underneath stays plain and semantic, so the library also works without its images.

## 1. Concept

Every UI element is a physical object in one small Bryce world: glass, water, chrome, polished stone and light, rendered with the same sun, the same softboxes and the same sky, so the whole set reads as one place. The interaction metaphors follow the materials:

| element | object |
|---|---|
| button | glossy pill (3-slice), pressed state = the pill sinks and its highlight shrinks |
| toggle | glass capsule with a floating orb that slides; on = the orb glows green |
| checkbox | small glass cube; checked = a green orb or tick inside |
| radio | bubble; selected = an inner pearl |
| slider | glass tube rail and an orb thumb; filled part = liquid in the tube |
| progress | liquid level rising in a glass tube, with a looping animated surface |
| panel / window | frosted glass slab with a bevelled rim (9-slice); body = CSS backdrop blur behind a rendered rim |
| tabs | glass tabs attached to a panel rim |
| text input | recessed glass well (9-slice); focus = rim lights up |
| file dropzone | shallow water basin; drag-over = the water ripples and glows |
| toast / tooltip | bubble glass with a pointer |
| spinner | ring of orbs (animated sprite sheet) |
| icons | embossed chrome/glass glyphs (heightfields), 3 sizes |
| page | Bryce wallpaper (sky, water, terrain) in era style |

States are rendered, not faked with CSS filters: hover = a brighter softbox, active = depressed geometry, focus = a lit rim plus a CSS outline (see §3), disabled = frosted and desaturated material.

## 2. Accessibility targets

> **Priority (user, 2026-11-03): make it as accessible as possible without much extra work and never at the
> expense of the look.** The look wins every conflict. The rules below are the cheap, high-value ones:
> native semantics, a label halo instead of de-glossed buttons, focus outline, target sizes, reduced motion and a
> basic forced-colours fallback. AAA, APCA reporting and a per-sprite non-text contrast audit are nice-to-haves.

Interpretation of "two accessibility standards":
- **WCAG 2.2 level AA**, the international baseline.
- **EN 301 549 / BITV 2.0**, which is what applies in Germany. It references WCAG 2.1 AA for web content and adds requirements for platform settings: user colour/contrast settings, no reliance on images for meaning, and keyboard use.

AAA criteria are met wherever this design allows it (target size, contrast for body text).

Concrete rules for a sprite-skinned library:
1. **Semantics first.** Every component is a native element (`button`, `input type=checkbox/range/file`, `select`, `textarea`, `details`, `dialog`). Sprites are backgrounds or `border-image` only and never carry meaning, so assistive tech sees ordinary controls.
2. **Text contrast is measured, not assumed.** Glossy sprites have highlights, so the build samples every sprite pixel under the text box and calculates the worst-case WCAG ratio, which must be at least 4.5:1 (7:1 targeted for body text). It also reports APCA Lc as a second, perceptual check. Labels on glossy surfaces get a rendered or CSS text shadow when needed, and the check runs with the shadow applied.
3. **Non-text contrast ≥ 3:1** (1.4.11) for control boundaries and states. This is checked between each sprite's silhouette edge and both the light and dark page backgrounds, and between checked and unchecked states.
4. **Focus visible** (2.4.7, and 2.4.13 as a goal): a rendered glow plus a CSS `outline` of at least 2 px with ≥ 3:1 contrast, which never relies on the sprite alone. `:focus-visible` only.
5. **Target size**: at least 24×24 CSS px everywhere (2.5.8 AA). The default is 44×44 (2.5.5 AAA); see §4.
6. **Forced colours / Windows High Contrast**: background images are dropped. Each component has a `@media (forced-colors: active)` style made of system colours and borders. It is tested.
7. **`prefers-contrast: more`** swaps to "solid" material variants (no transparency, darker rims) and stronger text.
8. **`prefers-reduced-motion`**: animated sprite sheets show their resting frame, with no slide or ripple animations.
9. **Zoom / reflow** (1.4.4, 1.4.10): all slicing is done with `border-image` and fixed-size sprites in `rem`, so 200% zoom and 320 px reflow work. Sprites are shipped at 1×, 2× and 3× (`image-set`) so zoom stays sharp.
10. **Text spacing** (1.4.12): no fixed-height text containers. 3-slice and 9-slice sprites stretch.
11. **Motion/flash** (2.3.1): no animation flashes more than 3 times per second.

## 3. Units and physical distances

The CSS reference pixel is defined as an angle: 1 px ≈ 0.0213° (1.28 arcmin), the size of one 96-dpi pixel seen from 71 cm. Browsers keep this angle roughly constant across device classes, so designing in CSS px means designing in visual angle, which is what reading comfort depends on. Physical size matters for touch, so the system has two axes:

| context | typical viewing distance | 1 CSS px ≈ | 44 px target ≈ | 16 px text x-height ≈ |
|---|---|---|---|---|
| phone (coarse pointer) | 30–35 cm | 0.16 mm | 7.0 mm | 1.4 mm |
| tablet | 40 cm | 0.19 mm | 8.4 mm | 1.6 mm |
| laptop (fine pointer) | 50–60 cm | 0.21–0.24 mm | 9.5 mm | 1.8 mm |
| desktop monitor | 60–70 cm | 0.26 mm | 11 mm | 2.2 mm |
| TV / projector | 2.5–3 m | ~1.1 mm | 48 mm | 9 mm |

Design rules derived from it:
- **Touch** (`@media (pointer: coarse)`): targets of at least 44 px (~7 mm on phones, close to the ~9 mm finger pad when the visual spacing is added), and at least 8 px between neighbouring targets (Fitts / mis-tap). On phones the hit areas grow through padding, and the sprites keep their proportions.
- **Fine pointer**: targets may shrink to a 32 px visual size, with the hit area still ≥ 24 px. Denser layouts are allowed.
- **Distance media** (TV / projector, `(min-width: 1600px) and (pointer: none)` or opt-in `.aer-distance`): type and spacing are scaled by 1.5×, so angles stay comfortable at 3 m.
- **Print**: sprites are dropped, and semantic borders and real units (mm) are used.

## 4. Spacing scale

The base unit is 4 px (≈ 0.85 mm at laptop distance, ≈ 5 arcmin). The scale is geometric between steps and anchored on the physical targets:

```
--aer-space-1:  4px   hairline gaps, icon-to-label
--aer-space-2:  8px   minimum gap between touch targets
--aer-space-3: 12px   control padding (fine pointer)
--aer-space-4: 16px   control padding (coarse), paragraph gap
--aer-space-5: 24px   group gap, minimum target size
--aer-space-6: 32px   section gap, fine-pointer control height
--aer-space-7: 44px   default control height / coarse target
--aer-space-8: 64px   panel padding (wide), header height
--aer-space-9: 96px   page section rhythm
```

Control heights come from the sprite sets: S = 32 px, M = 44 px (default) and L = 56 px. Each is rendered as its own geometry, not scaled, so highlight thickness and rim width stay physically right.

Type: the bundled Aerolith Text (Selawik with a kern table) with Segoe UI-like fallbacks ("Segoe UI", "Myriad Pro", Tahoma, system-ui). The base is 16 px with line-height 1.5, on a modular scale of 1.2 (13.3, 16, 19.2, 23, 27.6, 33.2).

## 5. Asset pipeline

1. A component is defined in Python as a Bryce scene builder (geometry + materials + state variants), at a shared physical scale: 1 Bryce unit ↔ a fixed number of CSS px per sheet.
2. `sheet.render_sheet` renders three passes (black backdrop, white backdrop, red/green silhouette mask) at 6× CSS size, which gives 3× DPR with 2× supersampling.
3. `sheet.matte` builds the alpha: solid objects get silhouette coverage, glass gets difference-matte partial alpha.
4. Sprites are cut, trimmed and downsampled to 3×, 2× and 1×. 3-slice and 9-slice insets are recorded in CSS px.
5. Atlas + generated CSS (custom properties per sprite: url, size, slice).
6. Automated checks: text contrast under label boxes, non-text contrast, target sizes, forced-colours screenshots, `axe-core` on the demo page.
7. A demo / docs page with every component in every state, on light, dark and wallpaper backgrounds.
