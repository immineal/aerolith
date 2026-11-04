# Changelog

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
