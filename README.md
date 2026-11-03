# Aerolith

Glossy buttons and real glass for the web, in the Frutiger Aero style. I rendered every button,
field, pane and icon in Bryce 2, the landscape renderer from 1996, and the CSS lays them over plain
HTML elements.

**[Live showcase](https://immineal.github.io/aerolith/)** · [npm](https://www.npmjs.com/package/aerolith) · [Changelog](CHANGELOG.md)

![Aerolith components in light and dark mode](docs/images/hero.png)

Behind the camera in every render there's a sunny meadow, so each glossy button carries a bit of
blue sky in its top half and green grass along its lower edge. The glass is real Bryce glass and
stays see-through on your page. Press a button and its face sinks into a bowl, so the shine slides
to the bottom. None of it is a CSS gradient.

## Use it

There's no build step. Link the stylesheet, and the script if you want the extras:

```html
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/aerolith@1/library/dist/aerolith.css">
<script src="https://cdn.jsdelivr.net/npm/aerolith@1/library/dist/aerolith.js" defer></script>
```

jsDelivr also serves the files straight from GitHub
(`https://cdn.jsdelivr.net/gh/immineal/aerolith@v1.0.0/library/dist/aerolith.css`), and the
release zip has them too. If you host them yourself, keep `sprites/` next to `aerolith.css`,
because the CSS looks for the images relative to itself.

Then put the classes on ordinary elements:

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

Put `class="aer"` on `<body>` or any container to get the focus ring and the reduced-motion rules.
The showcase uses every component, so view its source when you need an example.

### Package managers

| Where | Install | Then |
|---|---|---|
| npm | `npm i aerolith` | `import "aerolith/aerolith.css"` (and `import "aerolith/aerolith.js"`) |
| GitHub Packages | `npm i @immineal/aerolith --registry=https://npm.pkg.github.com` | same, under `@immineal/aerolith` |
| Composer | `composer require immineal/aerolith` | serve `vendor/immineal/aerolith/library/dist/` |
| PyPI | `pip install aerolith` | `aerolith.static_dir()`; Django: add `"aerolith"` to `INSTALLED_APPS` |
| CDN | unpkg, jsDelivr, esm.sh mirror the npm package | see above |

### Frameworks

Aerolith is just classes on native elements, so React, Vue and friends need no wrappers. Import the
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

In JSX it's `className="aer-button"`. If your router adds components after the page has loaded,
call `window.Aerolith.init(container)` so the script picks them up.

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

Dark mode follows the system setting. To force it, set `<html data-theme="dark">` (or `"light"`),
or put `.aer-dark` on one part of the page. The sun and moon switch (`input[data-aer-theme]`) sets
the attribute for you and remembers the choice.

## Accessibility

The skins sit on top of real form controls, so keyboards, screen readers, autofill and form
submission work as they would without Aerolith.

I measured label contrast on the rendered pixels, taking the darkest 5 % of the area behind the
text and leaving out the text halo. White on aqua comes out at 4.4:1, white on green at 4.7:1,
and dark text on clear glass at 4.6:1 or better in both themes. Hover and pressed states are
lighter, so their labels get a stronger halo.

- Controls are 44 px high by default. The small ones (checkbox, radio, close orb) still have a
  44 px hit area, through their label or a pseudo-element.
- In Windows high contrast mode (`forced-colors`) the sprites go away and system colours take
  over. Icons turn `CanvasText`.
- With `prefers-reduced-motion` the spinner stands still and the toggle, toast and dialog
  animations are off.

Where the look and accessibility pulled in different directions, I did the cheap fixes first
(text colour, halos, hit areas) and then let the look win. Without their halo, glossy hover
states measure 3.3 to 3.6:1, and pressed states about 2.4:1 because the sunken face catches more
light. You only see those states while the pointer is on the button.
`python3 library/build/a11y.py` prints the numbers for every sprite with a label.

## How it's made

![The three render passes of one sprite](docs/images/passes.png)

Bryce 2.1 for Windows runs under Wine on a virtual display, seven copies at once. A Python script
writes each scene as a Bryce `.brc` file. Nobody had documented that format, so I worked it out
and wrote it up in [docs/brc-format.md](docs/brc-format.md). Every sprite gets rendered three
times:

1. **K.** Over black. This gives the colour and every glint.
2. **W.** Over mid grey. Comparing it with K shows how much light the glass lets through.
3. **M.** In flat colours, as a mask of which pixels are solid and which are glass.

From those three, the build makes PNGs with real transparency. Gloss stays solid and glass stays
see-through. A second pass for dark pages turns frosted glass into smoked glass.

Each sprite sits alone in its own scene. When I rendered them side by side, every button mirrored
its neighbours, and that looked random once the sheet was cut apart. The camera is 4000 units away
with a long lens, so there's almost no perspective, and one CSS pixel is exactly six render
pixels. The build scales that down to 3x, 2x and 1x.

![Button states and orbs at 3x: the sky in the top half, the meadow in the lower bevel](docs/images/closeup.png)

The meadow is behind the camera: a painted sky, a big soft light for the shine across the top,
and a tilted field with two hills. The camera never sees it directly. You only ever see it
reflected.

The shapes are Bryce height fields that NumPy computes. Buttons are rounded rectangles with a soft
bevel, pressed buttons get a bowl, fields get a shallow well, and icons are embossed from
drawings. The CSS draws each sprite with `border-image`, with slice sizes in image pixels for
each resolution. Chromium, Firefox and WebKit all handle that the same way. They don't agree on
`image-set()` inside `border-image`, so I avoided it.

## Rebuild it yourself

The finished sprites are already in `library/dist/`, so you only need this to make new ones. You
need Wine and your own copy of Bryce 2 for Windows. This repo doesn't include Bryce and never
will.

```sh
cd library/build
python3 build.py              # renders what changed (hash cache), exports, writes dist/
python3 build.py btn-         # only sprites whose names start with btn-
python3 build.py --export-only
python3 shots.py              # screenshots in Chromium, Firefox, WebKit, light and dark
```

How to set up the renderer is in [harness/README.md](harness/README.md). The design rules are in
[docs/ui-library/foundations.md](docs/ui-library/foundations.md).

## What it does not do

- **No colour picker.** The colours are baked into the renders. A new colour means rendering
  again.
- **Three heights.** Buttons are 32, 44 or 56 px tall. They stretch sideways, not up.
- **The lens only bends light in Chrome and Edge.** It needs an SVG filter inside
  `backdrop-filter`, and only Chromium supports that. Firefox and Safari show the same clear
  glass without the bend.
- **No React or Vue components.** You put the classes on your own elements.
- **No icon font or SVGs.** The 35 icons are bitmaps at 16 and 24 px, and they get blurry if
  you scale them up.

## License

MIT, for the code and the sprites. See [LICENSE](LICENSE). Bryce is a trademark of its owner.
Aerolith has nothing to do with them officially and contains no part of the Bryce software.
