"""Map Bryce's UI by hovering: Bryce prints the name of the control under the pointer in the
bottom-left strip of its palette frame. `probe_region` walks a grid, OCRs that strip, and groups
the points per label. Each label's centre (median of its hits) relative to the frame's top-left
corner goes into ui_map.json.

    ./bry probe --region 0,0,141,560 --step 8     # frame-relative region
"""
from __future__ import annotations

import hashlib
import json
import time
from collections import defaultdict

import numpy as np

from . import screen
from .vm import VM


def frame_box(img) -> tuple[int, int, int, int]:
    """Bounding box of Bryce's light palette frame on the black desktop (screen coords)."""
    a = np.asarray(img.convert("L"), dtype=np.int16)
    if a.shape[0] == 768:
        a = a[:740]                      # VM: keep the Win98 taskbar out
    m = a > 60
    cols = np.where(m.sum(0) > 200)[0]
    if len(cols) == 0:
        raise RuntimeError("Bryce frame not found")
    x0 = int(cols[0])
    # rows: the left palette column is light from the frame's top to its bottom edge
    rows = np.where(m[:, x0:x0 + 130].sum(1) > 100)[0]
    if len(rows) == 0:
        raise RuntimeError("Bryce frame not found")
    return x0, int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1


def label_box(fb) -> tuple[int, int, int, int]:
    """The hover-help area under the left palette column: up to two centred lines,
    a group title in large type ("Render") and the control name in small type ("Fast Preview Mode")."""
    x0, y0, x1, y1 = fb
    return x0, y1 - 42, x0 + 137, y1


def read_label(img, fb=None) -> str:
    """Hover label as 'Title / Name' (or just one of them). '' when nothing is shown."""
    fb = fb or frame_box(img)
    crop = img.crop(label_box(fb))
    return read_label_crop(crop)


def read_label_crop(crop) -> str:
    n = np.asarray(crop.convert("L"))
    dark = (n < 170).sum(1) > 0
    lines, start = [], None
    for i, d in enumerate(list(dark) + [False]):
        if d and start is None:
            start = i
        elif not d and start is not None:
            if i - start >= 5:
                lines.append((start, i))
            start = None
    parts = []
    for a, b in lines:
        line = crop.crop((0, max(0, a - 3), crop.width, min(crop.height, b + 3)))
        scale = 3 if b - a > 12 else 4
        t = screen.ocr(line, scale=scale, psm=7).strip().strip("|").strip()
        if t:
            parts.append(t)
    return " / ".join(parts)


def hover_label(vm: VM, x: int, y: int, fb, settle: float = 0.35) -> str:
    vm.move_to(x, y, rehome=False)
    time.sleep(settle)
    return read_label(vm.screenshot(), fb)


def probe_region(vm: VM, rel_box, step: int = 8, settle: float = 0.35, log=print) -> dict:
    img = vm.screenshot()
    fb = frame_box(img)
    fx, fy = fb[0], fb[1]
    vm.home()
    cache: dict[str, str] = {}
    hits: dict[str, list[tuple[int, int]]] = defaultdict(list)
    x0, y0, x1, y1 = rel_box
    for ry in range(y0, y1, step):
        xs = range(x0, x1, step) if (ry - y0) // step % 2 == 0 else range(x1 - 1, x0 - 1, -step)
        for rx in xs:
            vm.move_to(fx + rx, fy + ry, rehome=False)
            time.sleep(settle)
            crop = vm.screenshot().crop(label_box(fb))
            h = hashlib.md5(crop.tobytes()).hexdigest()
            if h not in cache:
                cache[h] = read_label_crop(crop)
            t = cache[h]
            if t:
                hits[t].append((rx, ry))
        log(f"row {ry}: {len(hits)} labels")
    out = {}
    for t, pts in hits.items():
        a = np.array(pts)
        # the median hit lies inside the control even for non-convex shapes, most of the time
        cx, cy = np.median(a[:, 0]), np.median(a[:, 1])
        best = min(pts, key=lambda p: (p[0] - cx) ** 2 + (p[1] - cy) ** 2)
        out[t] = {"at": [int(best[0]), int(best[1])], "n": len(pts),
                  "bbox": [int(a[:, 0].min()), int(a[:, 1].min()), int(a[:, 0].max()), int(a[:, 1].max())]}
    return {"frame": list(fb), "controls": out}


if __name__ == "__main__":
    import sys
    box = tuple(int(v) for v in sys.argv[1].split(","))
    step = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    res = probe_region(VM(), box, step)
    print(json.dumps(res, indent=1))
