# Aerolith

A Frutiger Aero UI library for the web. Every button, field, pane and icon is a sprite rendered in
Bryce 2, the 1996 landscape renderer, and drawn onto native HTML elements with CSS.

**[Live showcase](https://immineal.github.io/aerolith/)** · [npm](https://www.npmjs.com/package/aerolith) · [Changelog](CHANGELOG.md)

![Aerolith components in light and dark mode](docs/images/hero.png)

The glossy parts reflect a sunny meadow, with blue sky above and green hills below, that sits
behind the camera in every render. Glass is real Bryce glass, rendered over two backdrops and
matted so it stays translucent on your page. Pressed buttons sink into a bowl, so the highlight
moves to the bottom edge. Every surface was rendered, not painted in CSS.

## Use it

No build step. Link the stylesheet and, optionally, the script:

```html
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/aerolith@1/library/dist/aerolith.css">
<script src="https://cdn.jsdelivr.net/npm/aerolith@1/library/dist/aerolith.js" defer></script>
```

The same files are on GitHub through jsDelivr
(`https://cdn.jsdelivr.net/gh/immineal/aerolith@v1.0.0/library/dist/aerolith.css`) and in the
release zip. Keep `sprites/` next to `aerolith.css`; the CSS finds the images relative to itself.

Then use native elements with Aerolith classes:

```html
<button class="aer-button">Convert to PDF</button>
<button class="aer-button aer-secondary aer-l">Start</button>
<button class="aer-button aer-quiet">Cancel</button>

<label class="aer-option"><input type="checkbox" role="switch" class="aer-toggle"> Keep metadata</label>
<label class="aer-label">File name <input class="aer-field" value="report.pdf"></label>
<progress class="aer-progress" max="100" value="62">62%</progress>

<button class="aer-iconbtn" aria-label="Settings">
  <span class="aer-icon aer-icon-gear" aria-hidden="true"></span>
</button>
```

Add `class="aer"` to `<body>` (or any container) to get the focus outline and reduced-motion
handling. The showcase uses every component, so its source doubles as reference markup.

### Package managers

| Where | Install | Then |
|---|---|---|
| npm | `npm i aerolith` | `import "aerolith/aerolith.css"` (and `import "aerolith/aerolith.js"`) |
| GitHub Packages | `npm i @immineal/aerolith --registry=https://npm.pkg.github.com` | same, under `@immineal/aerolith` |
| Composer | `composer require immineal/aerolith` | serve `vendor/immineal/aerolith/library/dist/` |
| PyPI | `pip install aerolith` | `aerolith.static_dir()`; Django: add `"aerolith"` to `INSTALLED_APPS` |
| CDN | unpkg, jsDelivr, esm.sh mirror the npm package | see above |

### Frameworks

Aerolith is plain CSS classes on native elements, so it needs no wrapper components. Import the
stylesheet once:

```js
// React (Vite, Next.js), Vue, Svelte, Solid: in your entry file or root layout
import "aerolith/aerolith.css";
import "aerolith/aerolith.js";   // optional: slider fill, drop zone, theme switch, lens
```

```astro
---
// Astro: in a layout
import "aerolith/aerolith.css";
---
```

In JSX write `className="aer-button"`. When you add components after page load (client-side
routing), call `window.Aerolith.init(container)` to wire up the optional behaviour.

## Components

| Class | On | States |
|---|---|---|
| `.aer-button` (+ `.aer-secondary`, `.aer-quiet`; `.aer-s`, `.aer-l`) | `<button>`, `<a>` | hover, pressed, `aria-pressed`, disabled |
| `.aer-iconbtn` (+ `.aer-quiet`) | `<button>` with an `.aer-icon` | hover, pressed |
| `.aer-icon .aer-icon-<name>` (+ `.aer-s`, `.aer-pearl`) | `<span aria-hidden="true">` | 35 glyphs, 24/16 px |
| `.aer-toggle` (+ `.aer-theme`) | `<input type="checkbox" role="switch">` | on, disabled |
| `.aer-check`, `.aer-radio` | checkbox, radio | checked, mixed, disabled |
| `.aer-field` | `<input>`, `<textarea>`, `<select>` | focus, disabled |
| `.aer-select` | wrapper around `select.aer-field` | |
| `.aer-segmented` | radios in labels, or links with `aria-current` | hover, selected |
| `.aer-choice` | `<label>` with a radio or checkbox | hover, checked, focus |
| `.aer-drop` | `<label>` with `<input type="file">` | drag-over, focus |
| `.aer-progress` | `<progress>` | value |
| `.aer-slider` | wrapper around `<input type="range">` | value (fill needs the JS) |
| `.aer-spinner` | `<span role="status" aria-label="…">` | 8-frame animation |
| `.aer-badge`, `.aer-orb` (+ `.aer-info`, `.aer-warn`, `.aer-error`) | any inline element | |
| `.aer-callout` (+ status colours), `.aer-toast` in `.aer-toaster` | any block | |
| `.aer-panel`, `.aer-card` | any block | card hover on links/buttons |
| `.aer-dialog`, `.aer-close` | `<dialog>`, `<button>` | open, backdrop |
| `.aer-popover`, `.aer-menu` | `[popover]` | item hover/focus |
| `.aer-bar` | `<header>`, `<nav>` | |
| `.aer-lens` | any block | rim refraction in Chromium |
| `.aer-compare` | two `<img>` and an `<input type="range">` | |

Dark mode follows `prefers-color-scheme`. Force it with `<html data-theme="dark">` (or `"light"`),
or scope it with `.aer-dark`. The theme switch (`input[data-aer-theme]`) sets the attribute and
remembers the choice.

## Accessibility

- Every skin sits on the native element, so keyboard use, form submission, screen readers and
  autofill behave as they would without Aerolith.
- Label contrast was measured on the rendered sprite pixels, at the darkest 5 % of the label
  area, before the text halo is added: white on aqua 4.4:1, white on green 4.7:1, dark ink on
  clear glass at least 4.6:1 in both themes. Hover and pressed states are lighter, so their
  labels get a stronger halo.
- Controls are 44 px high by default. Small controls (checkbox, radio, close orb) get a 44 px hit
  area through their label or a pseudo-element.
- `forced-colors` (Windows high contrast) drops the sprites and falls back to system colours.
  Icons switch to `CanvasText`.
- `prefers-reduced-motion` stops the spinner and the toggle, toast and dialog animations.
- Where look and accessibility conflict, the look won, but only after the cheap fixes (ink
  choice, halos, hit areas) were in. Without their halo, glossy hover states measure 3.3 to
  3.6:1 and pressed states about 2.4:1, because the sunken face catches more light. Both are
  momentary states. `python3 library/build/a11y.py` prints the numbers for every labelled sprite.

## How it's made

![The three render passes of one sprite](docs/images/passes.png)

Bryce 2.1 for Windows runs under Wine on a virtual X display, seven instances side by side. Python
writes each scene directly as a Bryce `.brc` file. The format was reverse-engineered for this:
see [docs/brc-format.md](docs/brc-format.md). Bryce then renders it to disk. Each sprite is
rendered three times:

1. **K:** over black, which gives the colour and every glint.
2. **W:** over mid grey, so the difference to K shows how much light the glass lets through.
3. **M:** flat colours, a mask that says which pixels are solid and which are glass.

The matting step turns those into PNGs with real alpha: solid gloss is opaque, glass keeps its
transparency, and a second matte for dark pages turns frosted glass into smoked glass.

Each sprite is rendered alone in its own scene. Rendered together, sprites reflect and refract
their neighbours, which looks random once the sheet is cut up. The camera sits 4000 units away
with a long lens, so the projection is near-orthographic and one CSS pixel is exactly six render
pixels. That is downsampled to 3x, 2x and 1x files.

![Button states and orbs at 3x: the sky in the top half, the meadow in the lower bevel](docs/images/closeup.png)

Behind the camera is the environment every gloss surface reflects: a custom sky, a big softbox
for the highlight band, and a tilted meadow with two hills. The camera never sees any of it,
but every glossy surface shows sky in its upper half and grass along its lower bevel.

Shapes are Bryce symmetrical lattices (height fields) computed in NumPy: rounded rectangles with
an eased bevel, a blurred-mask bowl for pressed states, a recessed well for fields, and icons
embossed from vector drawings. The CSS draws every sprite with `border-image`, with slices
measured in raw image pixels per resolution. That behaves the same in Chromium, Firefox and
WebKit, where `image-set()` inside `border-image` does not.

## Rebuild it yourself

The rendered output is committed in `library/dist/`, so you only need this to change sprites.
You need your own copy of Bryce 2 for Windows and Wine. Neither is included, and Bryce never will
be.

```sh
cd library/build
python3 build.py              # renders what changed (hash cache), exports, writes dist/
python3 build.py btn-         # only sprites whose names start with btn-
python3 build.py --export-only
python3 shots.py              # screenshots in Chromium, Firefox, WebKit, light and dark
```

The renderer setup is in [harness/README.md](harness/README.md), the design rules in
[docs/ui-library/foundations.md](docs/ui-library/foundations.md).

## What it does not do

- **No runtime colours.** The colours are baked into the sprites. A new colour means new renders.
- **Fixed control heights.** Buttons come in 32, 44 and 56 px. They stretch in width (3- and
  9-slice), not in height.
- **Glass distortion is Chromium-only.** The lens rim refraction uses an SVG filter in
  `backdrop-filter`, which only Chromium supports. Elsewhere you get the clear glass without
  distortion.
- **No JS framework components.** There are no React or Vue wrappers. The classes go on your
  own elements.
- **No icon font or SVG set.** The 35 icons are bitmaps at 16 and 24 px. They don't scale up
  cleanly.

## License

MIT, for the code and the rendered sprites. See [LICENSE](LICENSE). Bryce is a trademark of its
owner. This project is not affiliated with it and contains no part of the Bryce software.
