# Component inventory (from linu.li, 2026-11-03)

Source: an audit of every page of linu.li (24 pages; the raw HTML/CSS is kept in the session scratchpad).
The site today:
- Plain CSS with tokens (`--paper`, `--ink`, `--accent`…); dark mode is the default (`body.dark-mode`).
- Fonts: Space Grotesk for UI, Libre Baskerville for body text.
- Strings in EN plus DE, which runs about 20–30% longer.
- It has five different segmented-control implementations, three modal families and two compare sliders.

The library unifies these into one set.

## Controls → Aerolith sprites

| Component | Variants / states needed | Bryce object |
|---|---|---|
| Button | primary, secondary, outline/quiet, sm; hover, active, focus, disabled; as `button`, `a`, `span` | glossy pill (3-slice) per colour; outline = clear glass pill |
| Icon button | ×, pin heart ♡/♥, drag ☰, ← →, ?, gear, undo/redo, +/−, fit | small glass orb/rounded square + embossed glyph |
| Segmented control / tabs / button group | selected, unselected, hover, focus, disabled; 2–6 items; also underline tabs | glass tray (3-slice) with a sliding raised chip |
| Toggle switch | off, on, focus, disabled; compact (0.8×) | glass capsule + floating orb (grey → green glow) |
| Checkbox | unchecked, checked, focus, disabled | glass cube cell + green orb or tick |
| Radio | unselected, selected, focus, disabled | bubble + pearl |
| Choice card (radio card, layout card, shape card) | default, hover, checked, focus, disabled | frosted tile (9-slice) with a lit rim when checked |
| Range slider | track, fill, thumb (hover, active, focus) | glass tube rail, liquid fill, orb thumb |
| Text input / textarea / select / number / search pill | default, focus, readonly, disabled, (invalid) | recessed glass well (9-slice); pill variant; select arrow orb |
| Value row (read-only + Copy) | — | well + small icon button |
| Colour swatch input | — | glass lens over the colour |
| Drop zone | idle, hover, drag-over; compact, massive | water basin (9-slice); drag-over = ripple + glow (animated) |
| File row | name, size, thumbnail, status, remove, drag handle; dragging, placeholder | frosted strip (9-slice) |
| Page / chip grid | default, selected, cut-marker, disabled | small glass chips |
| Progress bar | 0–100, done | glass tube + liquid (stretchable fill, animated surface) |
| Spinner | — | ring of orbs (sprite animation) |
| Toast | success, error, info, warning | bubble panel with a coloured orb |
| Badge / tag | ok, over, pass, fail, count, risk | small gem pills |
| Callout | note, warn, danger, info | frosted panel with a coloured left gem rail |
| Card | static, interactive (hover lift), with pin | frosted glass slab (9-slice); hover = brighter rim + shadow |
| Modal / dialog | header, body, footer; backdrop | large frosted window (9-slice) + window-control orbs |
| Popover / menu / explainer | items: hover, focus | bubble glass with a pointer |
| Compare slider handle | — | vertical glass rod + orb grip |
| Theme switch | light, dark | sun/moon orb toggle |
| Header bar / footer | — | glass bar (3-slice) over the wallpaper |
| Big number display, code block, table, JSON tree, diff rows | — | mostly CSS on frosted panels; tree arrows as tiny glyphs |
| Map / canvas controls (zoom strip, tool strip, grab handle) | — | icon buttons in a glass tray |

## Icon set (embossed glyphs, 3 sizes: 16/24/32)

heart, heart-filled, close, menu/handle, arrow-left/right, swap, play/expand, help, gear, undo, redo, plus, minus, fit,
search, download, upload, copy, check, warning, error, info, file, pdf, image, text, code, clock, colour, map, lock.

## Fixes the library brings for free (cheap accessibility wins)

- Native elements under every skin, so drop zones, toggles, tabs and cards stop being `div onclick`.
- Visible `:focus-visible` rim plus an outline.
- `aria-live` toasts and `role=progressbar` in the markup examples.
- German-length labels: everything stretches via 3- or 9-slice; no fixed widths.
