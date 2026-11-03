"""Screen analysis helpers: change detection, waiting, template matching, OCR, cropping/zoom."""
from __future__ import annotations

import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image


def to_np(img: Image.Image) -> np.ndarray:
    return np.asarray(img.convert("RGB"), dtype=np.int16)


def diff_fraction(a: Image.Image, b: Image.Image, tol: int = 8) -> float:
    """Fraction of pixels that changed by more than `tol` in any channel."""
    if a.size != b.size:
        return 1.0
    d = np.abs(to_np(a) - to_np(b)).max(axis=2)
    return float((d > tol).mean())


def diff_bbox(a: Image.Image, b: Image.Image, tol: int = 8):
    if a.size != b.size:
        return (0, 0) + b.size
    d = np.abs(to_np(a) - to_np(b)).max(axis=2) > tol
    ys, xs = np.nonzero(d)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def wait_stable(vm, settle: float = 1.0, timeout: float = 60.0, interval: float = 0.25,
                tol_frac: float = 0.0005, ignore=None) -> Image.Image:
    """Return a screenshot once the screen stopped changing for `settle` seconds.

    `ignore` is an optional box (x0,y0,x1,y1) excluded from the comparison (e.g. a clock).
    """
    end = time.time() + timeout
    prev = vm.screenshot()
    stable_since = time.time()
    while time.time() < end:
        time.sleep(interval)
        cur = vm.screenshot()
        a, b = prev, cur
        if ignore:
            a = a.copy(); b = b.copy()
            blank = Image.new("RGB", (ignore[2] - ignore[0], ignore[3] - ignore[1]))
            a.paste(blank, ignore[:2]); b.paste(blank, ignore[:2])
        if diff_fraction(a, b) > tol_frac:
            stable_since = time.time()
        elif time.time() - stable_since >= settle:
            return cur
        prev = cur
    return prev


def wait_change(vm, ref: Image.Image, timeout: float = 30.0, interval: float = 0.25,
                tol_frac: float = 0.0005, box=None) -> Image.Image | None:
    """Wait until the screen (or `box`) differs from `ref`."""
    end = time.time() + timeout
    while time.time() < end:
        cur = vm.screenshot()
        a, b = (ref.crop(box), cur.crop(box)) if box else (ref, cur)
        if diff_fraction(a, b) > tol_frac:
            return cur
        time.sleep(interval)
    return None


def find_template(img: Image.Image, tpl: Image.Image, threshold: float = 0.92, region=None):
    """Best match of `tpl` in `img` -> (x, y, score) of the template's top-left, or None."""
    import cv2
    src = np.asarray(img.convert("RGB"))
    t = np.asarray(tpl.convert("RGB"))
    ox = oy = 0
    if region:
        ox, oy = region[0], region[1]
        src = src[region[1]:region[3], region[0]:region[2]]
    if src.shape[0] < t.shape[0] or src.shape[1] < t.shape[1]:
        return None
    res = cv2.matchTemplate(src, t, cv2.TM_CCOEFF_NORMED)
    _, score, _, loc = cv2.minMaxLoc(res)
    if score < threshold:
        return None
    return loc[0] + ox, loc[1] + oy, float(score)


def ocr(img: Image.Image, box=None, scale: int = 3, psm: int = 6) -> str:
    """OCR a region with tesseract (upscaled; works well on 90s system fonts)."""
    if box:
        img = img.crop(box)
    img = img.convert("L").resize((img.width * scale, img.height * scale), Image.LANCZOS)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "o.png"
        img.save(p)
        out = subprocess.run(["tesseract", str(p), "-", "--psm", str(psm)],
                             capture_output=True, text=True)
    return out.stdout.strip()


def ocr_words(img: Image.Image, box=None, scale: int = 3, psm: int = 11, min_conf: int = 40):
    """OCR with word boxes in screen coordinates: [(text, x0, y0, x1, y1, conf)]."""
    ox, oy = (box[0], box[1]) if box else (0, 0)
    if box:
        img = img.crop(box)
    big = img.convert("L").resize((img.width * scale, img.height * scale), Image.LANCZOS)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "o.png"
        big.save(p)
        out = subprocess.run(["tesseract", str(p), "-", "--psm", str(psm), "tsv"],
                             capture_output=True, text=True).stdout
    words = []
    for line in out.splitlines()[1:]:
        f = line.split("\t")
        if len(f) < 12 or not f[11].strip():
            continue
        conf = float(f[10])
        if conf < min_conf:
            continue
        l, t, w, h = (int(v) for v in f[6:10])
        words.append((f[11], ox + l // scale, oy + t // scale, ox + (l + w) // scale,
                      oy + (t + h) // scale, conf))
    return words


def find_text(img: Image.Image, text: str, box=None, **kw):
    """Locate a word/phrase on screen via OCR -> center (x, y) or None. Case-insensitive."""
    target = text.lower().split()
    words = ocr_words(img, box=box, **kw)
    toks = [w[0].lower().strip(".,:;…") for w in words]
    for i in range(len(words) - len(target) + 1):
        if all(toks[i + j].startswith(target[j]) for j in range(len(target))):
            seg = words[i:i + len(target)]
            x0 = min(w[1] for w in seg); y0 = min(w[2] for w in seg)
            x1 = max(w[3] for w in seg); y1 = max(w[4] for w in seg)
            return (x0 + x1) // 2, (y0 + y1) // 2
    return None


def zoom(img: Image.Image, box, factor: int = 3) -> Image.Image:
    c = img.crop(box)
    return c.resize((c.width * factor, c.height * factor), Image.NEAREST)


def grid(img: Image.Image, step: int = 50) -> Image.Image:
    """Overlay a labelled coordinate grid (for reading off click targets)."""
    from PIL import ImageDraw
    g = img.copy()
    d = ImageDraw.Draw(g)
    for x in range(0, g.width, step):
        d.line([(x, 0), (x, g.height)], fill=(255, 0, 255) if x % (step * 2) == 0 else (0, 200, 255), width=1)
        d.text((x + 2, 2), str(x), fill=(255, 255, 0))
    for y in range(0, g.height, step):
        d.line([(0, y), (g.width, y)], fill=(255, 0, 255) if y % (step * 2) == 0 else (0, 200, 255), width=1)
        d.text((2, y + 2), str(y), fill=(255, 255, 0))
    return g
