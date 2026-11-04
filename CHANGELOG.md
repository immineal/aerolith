# Changelog

## 1.3.1 (2026-11-04)

- npm releases come straight from GitHub Actions through trusted publishing, with provenance
  (npm shows which commit and workflow built the package). No package changes.

## 1.3.0 (2026-11-04)

- Istok Web is no longer bundled. Aerolith Text is the only text face; `data-aer-type="istok"`
  and `dist/fonts/istok-web-*.woff2` are gone.
- `fonts/` holds Aerolith Text and Aerolith Display as TTF files to install on a computer. Each
  release attaches them as `aerolith-fonts.zip`, and the showcase links to it.
- `data-aer-toggle` on a button flips `aria-pressed` on click. A heart icon inside a button that
  is not pressed shows as an outline.

## 1.2.0 (2026-11-04)

- Segmented controls and tab bars: with aerolith.js the selected chip slides to the new item
  instead of jumping. It follows radios, `aria-current`, `aria-selected` and `aria-pressed`; after
  setting `input.checked` from script, call `Aerolith.init()` to move it. Reduced motion turns the
  slide off; without the JS each item draws its own chip as before.
- Fields show focus with their rendered aqua rim only. The square outline is gone; forced-colours
  mode keeps a system outline.
- Package descriptions and keywords say "tactile UI" and no longer name a design style.
- Lens: `data-aer-lens-backdrop="<selector>"` bends the rim in Firefox too (the lens carries a copy
  of that element and filters it). `data-aer-drag` makes a lens movable by pointer, touch or arrow
  keys inside its parent. Safari still shows plain glass.
- Lens glass re-rendered with one continuous curve over the rim and rounder (superellipse)
  corners, so the edge has no crease. The refraction follows Snell's law over that curve and
  splits red, green and blue slightly, giving colour fringes at the rim. The map takes about 6 ms
  to build and scrolling or dragging stays at 60 fps.
- Showcase: starts in light mode, shorter headline, before/after images on a bluer sky, a lens
  you can drag, less text. The headline now reads "Aerolith, a nostalgic tactile UI".
- Text spacing: Chromium on Linux and Windows rounded every glyph advance to a whole pixel, so
  labels came out up to 1.7 px wider with uneven gaps (the hole after the f in "verfügbar").
  Controls now set `text-rendering: geometricPrecision`, which lays text out exactly. The
  before/after and hero images were shot again.
- Aerolith Text replaces Selawik as the default text face: the same outlines with a kern table
  (Selawik has none). It tightens open capital pairs (AT, Ta, LY, Fu), keeps r-f, t-v and
  f-ï apart and leaves ordinary lowercase spacing as drawn. It is renamed because the OFL
  reserves "Selawik". `dist/fonts/selawik-*.woff2` are gone; use `aerolith-text-*.woff2`.
  `library/build/spacing_check.py` checks the layout in Chromium and Firefox.

## 1.1.0 (2026-11-04)

- Aerolith Display: gel letters rendered in Bryce, one isolated render per glyph, packed into
  colour fonts (OpenType-SVG and sbix, picked with `tech()`). Three materials: aqua, glass (smoked
  on dark pages) and pearl. Use `.aer-display` on headings; on dark pages it uses the glass face
  unless you add `.aer-aqua`. Outlines are matted to the exact font outline, so they stay smooth
  instead of following Bryce's heightfield grid.
- Bundled text faces: Selawik (default) and Istok Web (`data-aer-type="istok"`). Before, the
  stack asked for Segoe UI and fell back to whatever the system had.
- `.aer-glow` text halo.
- Hover, pressed and checked sprites load with the page (zero-size backgrounds), and aerolith.js
  preloads the sprites of closed dialogs and popovers. A first tap no longer shows an empty
  control for a moment.
- Menus: a popover opens below its button (above when there is no room) instead of in the
  window's corner; `data-aer-menu="id"` opens one at the pointer on right-click or long-press;
  picking an item closes it. Popovers and toasts blur what is behind them, so text under
  them no longer shows through.
- Phones: toasts sit centred; the dialog backdrop blurs in Safari too.
- Showcase: titles in Aerolith Display, a text-face switch, a sky that follows the visitor's
  local time, a section menu on narrow screens.

## 1.0.0 (2026-11-03)

First release.

- Buttons: primary (aqua), secondary (green), quiet (clear glass) and disabled, at 32/44/56 px;
  hover, and a pressed state whose face sinks into a bowl.
- Icon buttons (44 px orbs), 35 embossed icons at 24 and 16 px in aqua and pearl.
- Switch, checkbox (with mixed), radio, theme switch with sun and moon knobs.
- Text field, textarea, select, segmented control / tab bar, choice cards, drop zone.
- Progress (liquid in a glass tube), slider, spinner (8 rendered frames), badges, status orbs,
  callouts, toasts.
- Panel, card, dialog (native `<dialog>`), popover menu, header bar, clear glass lens with rim
  refraction in Chromium, before/after compare.
- Light and dark themes: every glass sprite is matted twice; dark pages get smoked glass.
- Sprites at 1x, 2x and 3x, drawn with `border-image` on native elements; forced-colours and
  reduced-motion fallbacks.
