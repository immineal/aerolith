"""Render the catalog and export the web library.

    python3 build.py                 # everything
    python3 build.py toggle check    # only these sheets (by name prefix); re-export uses cached BMPs
    python3 build.py --export-only   # skip rendering, re-matte/export from the BMPs on disk
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

import studio  # noqa: F401  (sets up the harness import path)
from studio import Studio, ROOT
from bryce_harness import sheet as SH
import catalog
import materials as M
from PIL import Image
import export as EX

WORK = ROOT / "work" / "lib"


def isolated(sheets):
    """One scene per sprite. Objects rendered together reflect and refract each other, and which
    neighbour shows up depends on the sheet layout, so every sprite is rendered alone: all it can
    reflect is the studio rig (sky, softboxes), identical for every sprite. Multi-object sprites
    (a checkbox with its tick) are one Item and keep their own, consistent inter-reflection."""
    out = []
    for sh in sheets:
        for it in sh.items:
            out.append(catalog.Sheet(it.name, [it], gap=it.margin + 4).layout())
    return out


def _key(scene: Path, width: int) -> str:
    import hashlib
    return hashlib.sha1(scene.read_bytes() + str(width).encode()).hexdigest()


def fresh(scene: Path, width: int) -> bool:
    """The BMP was rendered from exactly these scene bytes at this width."""
    h = scene.with_suffix(".hash")
    return scene.with_suffix(".bmp").exists() and h.exists() and h.read_text() == _key(scene, width)


def stamp(scene: Path, width: int):
    scene.with_suffix(".hash").write_text(_key(scene, width))


def render_checked(job, aspect=None, attempts=3):
    """Render one pass; when Bryce ignored the document size (sporadic: a 4:3 BMP comes back),
    render it again."""
    from PIL import Image
    for i in range(attempts):
        SH.render_many([job], timeout=4 * 3600)
        if aspect is None:
            return
        w, h = Image.open(job[1]).size
        if abs(h - w * aspect) <= 4:
            return
        print(f"{job[0].name}: got {w}x{h}, expected {w}x{w * aspect:.0f}; re-rendering", flush=True)
    raise RuntimeError(f"{job[0].name}: wrong size after {attempts} attempts")


def write(sh: catalog.Sheet):
    def build(ctx):
        st = Studio(ctx, sh.width, sh.height)
        sh.build(st)
    return SH.write_passes(WORK / sh.name, build)


def exact(rgba, w, h):
    if rgba.shape[1] == w and rgba.shape[0] == h:
        return rgba
    from scipy import ndimage
    pre = np.dstack([rgba[..., :3] * rgba[..., 3:4], rgba[..., 3]])
    pre = ndimage.zoom(pre, (h / rgba.shape[0], w / rgba.shape[1], 1), order=1, grid_mode=True, mode="nearest")
    pre = pre[:h, :w]
    a = np.clip(pre[..., 3:4], 0, 1)
    rgb = np.where(a > 1e-6, pre[..., :3] / np.maximum(a, 1e-6), 0)
    return np.dstack([np.clip(rgb, 0, 1), a[..., 0]])


def type_outline(sh: catalog.Sheet, bmps: dict):
    """Display-face glyphs (one per sheet, "type<tag>-<material>-<codepoint>"): the exact outline
    coverage for the matte, or None (other sheets, or a fit that does not match the render)."""
    if not sh.name.startswith("type") or len(sh.items) != 1:
        return None
    import typeface as T
    m = SH.sprites.load(bmps["m"])
    ch = chr(int(sh.name.rsplit("-", 1)[1], 16))
    cov, rms = T.outline(ch, np.clip(m[..., 0] + m[..., 1], 0, 1), EX.RENDER_SCALE)
    if cov is None or rms > 1.2:                    # 512 lattice fits to ~0.4-0.5 px
        print(f"  {sh.name}: outline fit off (rms {rms:.2f} px), keeping the rendered edge", flush=True)
        return None
    return cov


def export_sheet(sh: catalog.Sheet, out_dir: Path, names: set = frozenset()) -> list[dict]:
    """names: every item name in the catalog. An item called "<x>.dark" is an explicit dark-theme
    sprite (matted for dark pages); a glass item without one gets an automatic dark matte."""
    bmps = {m: WORK / f"{sh.name}_{m}.bmp" for m in "kwm"}
    explicit_dark = all(it.name.endswith(".dark") for it in sh.items)
    edge = type_outline(sh, bmps)
    themes = {"light": SH.matte(bmps, over="dark" if explicit_dark else "light", outline=edge)}
    if sh.has_glass and not explicit_dark and any(it.glass and it.name + ".dark" not in names
                                                  for it in sh.items):
        themes["dark"] = SH.matte(bmps, over="dark", outline=edge)
    # Bryce renders 1-3 px short of the requested size: resample to exactly RENDER_SCALE x the
    # sheet so sprite boxes land on the 6-px grid (<= 0.15 % scale, no visible softening)
    k = EX.RENDER_SCALE
    themes = {t: exact(img, int(round(sh.width * k)), int(round(sh.height * k))) for t, img in themes.items()}
    entries = []
    for it in sh.items:
        x, y = it.pos
        shape = (x * k, y * k, (x + it.w) * k, (y + it.h) * k)
        m = it.margin * k
        box = (shape[0] - m, shape[1] - m, shape[2] + m, shape[3] + m)
        for theme, img in themes.items():
            if theme == "dark" and (not it.glass or it.name + ".dark" in names):
                continue
            name = it.name + (".dark" if theme == "dark" else "")
            sp = EX.Sprite(name, tuple(int(v) for v in box), slice=it.slice,
                           shape=tuple(int(round(v)) for v in shape), label=it.label, text=it.text,
                           hit=it.hit, meta={"sheet": sh.name})
            entries.append(EX.export(img, sp, out_dir))
    return entries


def skins_css() -> str:
    """Selectors -> sprite variables for multi-variant components (generated, so every
    colour x size x state combination exists and specificity stays uniform)."""
    out = ["/* generated by build/build.py: component state -> sprite */"]

    def rule(sel, n):
        out.append(f"{sel} {{ --_img: var(--aer-{n}); --_slice: var(--aer-{n}-slice); "
                   f"--_bw: var(--aer-{n}-border); --_out: var(--aer-{n}-outset); }}")

    colours = {"primary": "", "secondary": ".aer-secondary", "glass": ".aer-quiet"}
    sizes = {"m": "", "s": ".aer-s", "l": ".aer-l"}
    for c, cc in colours.items():
        for z, zc in sizes.items():
            base = f".aer-button{cc}{zc}"
            rule(base, f"btn-{c}-{z}")
            rule(f"{base}:hover", f"btn-{c}-{z}-hover")
            rule(f"{base}:active, {base}[aria-pressed=\"true\"]", f"btn-{c}-{z}-active")
    for c, cc in colours.items():
        for z, zc in sizes.items():
            base = f".aer-button{cc}{zc}"
            rule(f"{base}:disabled, {base}[aria-disabled=\"true\"]", f"btn-disabled-{z}")
    return "\n".join(out) + "\n"


def main(argv):
    only = [a for a in argv if not a.startswith("--")]
    sheets = [s for s in isolated(catalog.sheets()) if not only or any(s.name.startswith(o) for o in only)]
    WORK.mkdir(parents=True, exist_ok=True)
    if "--export-only" not in argv:
        jobs, cached = [], 0
        for sh in sheets:
            for mode, scene in write(sh).items():
                width = int(round(sh.width * EX.RENDER_SCALE))
                if fresh(scene, width):
                    cached += 1
                    continue
                jobs.append((scene, scene.with_suffix(".bmp"), width))
        print(f"{cached} passes up to date", flush=True)
        # heavy (glass) sheets first so the pool's tail is short
        jobs.sort(key=lambda j: (j[0].stem.endswith("_m"), -j[2]))
        t = time.time()
        print(f"rendering {len(jobs)} passes for {len(sheets)} sheets", flush=True)
        import concurrent.futures as cf
        failed = []

        aspect = {}
        for sh in sheets:
            for m in "kwm":
                aspect[(WORK / f"{sh.name}_{m}.brc").name] = sh.height / sh.width

        def one(job):                       # record each pass as soon as it is done (resumable)
            try:
                render_checked(job, aspect.get(job[0].name))
                stamp(job[0], job[2])
            except Exception as e:
                failed.append((job[0].name, str(e)))
        with cf.ThreadPoolExecutor(len(SH.POOL)) as ex:
            list(ex.map(one, jobs))
        if failed:
            print("FAILED:", failed, flush=True)
        print(f"rendered in {time.time() - t:.0f} s", flush=True)
    out = EX.DIST / "sprites"
    manifest_path = EX.DIST / "sprites.json"
    parts_path = PARTS / "parts.json"
    entries = {}
    for mp in (manifest_path, parts_path):
        if mp.exists():
            entries.update(json.loads(mp.read_text()))
    for e in entries.values():                       # JSON turned the DPR keys into strings
        e["files"] = {int(d): f for d, f in e["files"].items()}
    names = {it.name for s in catalog.sheets() for it in s.items}
    for sh in sheets:
        dest = PARTS / "sprites" if is_part(sh.name) else out
        dest.mkdir(parents=True, exist_ok=True)
        for e in export_sheet(sh, dest, names):
            entries[e["name"]] = e
    EX.optimise(sorted(out.glob("*.png")))
    lst = sorted(entries.values(), key=lambda e: e["name"])
    pub = [e for e in lst if not is_part(e["name"])]
    EX.write_manifest(pub, manifest_path)
    EX.write_manifest([e for e in lst if is_part(e["name"])], parts_path)
    (EX.DIST / "sprites.css").write_text(EX.css_vars(pub))
    (EX.DIST / "icons.css").write_text(icon_atlas(entries))
    (EX.DIST / "skins.css").write_text(skins_css())
    fonts(entries)
    bundle()
    print(f"{len(lst)} sprites -> {EX.DIST}")


# icon glyphs and spinner frames are only inputs to the atlases / strips: they are exported to
# library/work/parts (with their own manifest), not to dist/
PARTS = EX.LIB / "work" / "parts"


def is_part(name: str) -> bool:
    return name.startswith(("icon-", "spin-", "type"))


def part_file(e: dict, dpr: int) -> Path:
    return (PARTS if is_part(e["name"]) else EX.DIST) / e["files"][dpr]


def icon_atlas(entries: dict) -> str:
    """Pack the icon sprites into one atlas per native size and DPR (columns = glyphs, rows =
    styles) and return icons.css. Every cell is the icon box plus its glint margin; the
    ::before draws the cell over the element box, offset by that margin."""
    import icons as I
    styles = list(M.ICON)
    css = ["/* generated by build/build.py: icon atlases */",
           ".aer-icon { --_s: 24px; --_m: 3px; --_c: calc(var(--_s) + 2 * var(--_m)); --_i: 0; --_j: 0;",
           "  display: inline-block; position: relative; flex: none; inline-size: var(--_s); block-size: var(--_s);",
           "  vertical-align: middle; }",
           ".aer-icon::before { content: \"\"; position: absolute; inset: calc(-1 * var(--_m)); pointer-events: none;",
           "  background: var(--_atlas) no-repeat; background-size: var(--_bs);",
           "  background-position: calc(var(--_i) * -1 * var(--_c)) calc(var(--_j) * -1 * var(--_c)); }",
           ".aer-icon.aer-pearl, :is(.aer-button, .aer-iconbtn):not(.aer-quiet) .aer-icon:not(.aer-aqua) { --_j: 1; }"]
    glyphs = list(I.GLYPHS)
    for gi, g in enumerate(glyphs):
        css.append(f".aer-icon-{g} {{ --_i: {gi}; }}")
    media = {1: None, 2: "(min-resolution: 1.5dppx)", 3: "(min-resolution: 2.5dppx)"}
    for size, o in catalog.ICON_SIZES.items():
        m = o["margin"]
        cell = size + 2 * m
        sel = ".aer-icon" if size == 24 else f".aer-icon.aer-s"
        if size != 24:
            css.append(f"{sel} {{ --_s: {size}px; --_m: {m}px; }}")
        css.append(f"{sel} {{ --_bs: {cell * len(glyphs)}px {cell * len(styles)}px; --_atlas: var(--aer-icons-{size}); }}")
        for dpr, q in media.items():
            atlas = Image.new("RGBA", (cell * len(glyphs) * dpr, cell * len(styles) * dpr), (0, 0, 0, 0))
            missing = 0
            for gi, g in enumerate(glyphs):
                for si, st in enumerate(styles):
                    e = entries.get(f"icon-{size}-{st}-{g}")
                    if not e:
                        missing += 1
                        continue
                    im = Image.open(part_file(e, dpr)).convert("RGBA")
                    t, r, b, l = e.get("outset") or (0, 0, 0, 0)
                    atlas.alpha_composite(im, ((gi * cell + m - l) * dpr, (si * cell + m - t) * dpr))
            path = EX.DIST / "sprites" / f"icons-{size}@{dpr}x.png"
            atlas.save(path)
            EX.optimise([path])
            decl = f':root {{ --aer-icons-{size}: url("sprites/{path.name}"); }}'
            css.append(decl if q is None else f"@media {q} {{ {decl} }}")
            if missing and dpr == 1:
                print(f"icons-{size}: {missing} sprites missing", flush=True)
    # <select> chevron: the 16 px aqua glyph, drawn by the wrapper (a <select> has no ::after)
    m16 = catalog.ICON_SIZES[16]["margin"]
    c16 = 16 + 2 * m16
    ci = glyphs.index("chevron-down")
    css.append(f".aer-select::after {{ content: \"\"; position: absolute; pointer-events: none;"
               f" inset-inline-end: {12 - m16}px; inset-block-start: calc(50% - {c16 / 2:g}px);"
               f" inline-size: {c16}px; block-size: {c16}px; background: var(--aer-icons-16) no-repeat"
               f" {-ci * c16}px 0 / {c16 * len(glyphs)}px {c16 * len(styles)}px; }}")
    css += strip(entries, "spin", catalog.SPIN_FRAMES)
    css += ["@media (forced-colors: active) {",
            "  .aer-icon::before { forced-color-adjust: none; background: CanvasText;",
            "    mask: var(--_atlas) no-repeat; mask-size: var(--_bs);",
            "    mask-position: calc(var(--_i) * -1 * var(--_c)) calc(var(--_j) * -1 * var(--_c)); }",
            "}"]
    return "\n".join(css) + "\n"


def strip(entries: dict, name: str, frames: int, margin: int = 3) -> list[str]:
    """Animation frames <name>-0..n-1 -> one horizontal strip per DPR (sprites/<name>@Nx.png).
    Every cell is the object outline plus `margin` (frames are trimmed individually)."""
    es = [entries.get(f"{name}-{f}") for f in range(frames)]
    if not all(es):
        print(f"{name}: frames missing", flush=True)
        return []
    w, h = (v + 2 * margin for v in es[0]["shape_size"])
    out = []
    for dpr, q in {1: None, 2: "(min-resolution: 1.5dppx)", 3: "(min-resolution: 2.5dppx)"}.items():
        im = Image.new("RGBA", (w * frames * dpr, h * dpr), (0, 0, 0, 0))
        for f, e in enumerate(es):
            fr = Image.open(part_file(e, dpr)).convert("RGBA")
            t, r, b, l = e.get("outset") or (0, 0, 0, 0)
            im.alpha_composite(fr, ((f * w + margin - l) * dpr, (margin - t) * dpr))
        path = EX.DIST / "sprites" / f"{name}@{dpr}x.png"
        im.save(path)
        EX.optimise([path])
        decl = f':root {{ --aer-{name}: url("sprites/{path.name}"); --aer-{name}-cell: {w}px {h}px; }}'
        out.append(decl if q is None else f"@media {q} {{ {decl} }}")
    return out


FONTS = Path(__file__).resolve().parent / "fonts"
TEXT_FONTS = {   # dist name -> source (unmodified; Istok converted TTF -> WOFF2, Selawik as released)
    "istok-web-regular.woff2": "IstokWeb-Regular.ttf", "istok-web-italic.woff2": "IstokWeb-Italic.ttf",
    "istok-web-bold.woff2": "IstokWeb-Bold.ttf", "istok-web-bold-italic.woff2": "IstokWeb-BoldItalic.ttf",
    "selawik-light.woff2": "selawkl.woff2", "selawik-regular.woff2": "selawk.woff2",
    "selawik-semibold.woff2": "selawksb.woff2", "selawik-bold.woff2": "selawkb.woff2",
}


def fonts(entries: dict):
    """dist/fonts: the bundled text faces and the Aerolith Display colour fonts (built from the
    type-* parts when all of them have been rendered)."""
    import shutil
    from fontTools.ttLib import TTFont
    import fontbuild
    import typeface
    out = EX.DIST / "fonts"
    out.mkdir(parents=True, exist_ok=True)
    for dst, src in TEXT_FONTS.items():
        d = out / dst
        if d.exists() and d.stat().st_mtime >= (FONTS / src).stat().st_mtime:
            continue
        if src.endswith(".ttf"):
            f = TTFont(str(FONTS / src))
            f.flavor = "woff2"
            f.save(str(d))
        else:
            shutil.copyfile(FONTS / src, d)
    shutil.copyfile(FONTS / "OFL-Istok.txt", out / "OFL-Istok-Web.txt")
    shutil.copyfile(FONTS / "OFL-Selawik.txt", out / "OFL-Selawik.txt")
    (out / "OFL-Aerolith-Display.txt").write_text(
        "Aerolith Display is derived from Istok Web Bold by Andrey V. Panov. The outlines were made\n"
        "heavier and each glyph was rendered in Bryce; it is a Modified Version under the SIL Open\n"
        "Font License 1.1 below and does not use the Reserved Font Name \"Istok\".\n\n"
        "Copyright (c) 2026, Immineal (colour glyphs).\n\n" + (FONTS / "OFL-Istok.txt").read_text())
    for style in fontbuild_styles():
        mat, dark = style
        def sprite(ch, dpr, mat=mat, dark=dark):
            e = entries.get(f"type-{mat}-{ord(ch):04x}{dark}") or entries.get(f"type-{mat}-{ord(ch):04x}")
            if e is None:
                raise KeyError(ch)
            return part_file(e, dpr), tuple(e.get("outset") or (0, 0, 0, 0))
        try:
            sizes = fontbuild.build(mat + dark.replace(".", "-"), sprite, out)
            print(f"Aerolith Display {mat}{dark}: {sizes}", flush=True)
        except KeyError as k:
            print(f"Aerolith Display {mat}{dark}: glyph {k} not rendered yet, font skipped", flush=True)


def fontbuild_styles():
    import materials
    for mat in materials.TYPE:
        yield mat, ""
        if mat == "glass":
            yield mat, ".dark"


def bundle():
    """dist/aerolith.css = base + sprites + skins + components, next to dist/sprites/ (one file, so
    relative url()s in the sprite variables resolve the same way in every browser)."""
    src = EX.LIB / "src"
    parts = [src / "base.css", src / "type.css", EX.DIST / "sprites.css", EX.DIST / "skins.css", EX.DIST / "icons.css",
             src / "components.css"]
    (EX.DIST / "aerolith.css").write_text("\n".join(f"/* ---- {p.name} ---- */\n" + p.read_text() for p in parts))
    (EX.DIST / "aerolith.js").write_text((src / "aerolith.js").read_text())


if __name__ == "__main__":
    main(sys.argv[1:])
