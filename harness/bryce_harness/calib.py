"""Pointer verification: find where the guest actually drew the mouse cursor.

The arrow cursor's hotspot is its top-left pixel, so we move the pointer to (x, y), grab a frame,
park the pointer somewhere else, grab another frame, and take the top-left of the changed area
near the target.  No templates, works for any cursor shape whose hotspot is top-left.
"""
from __future__ import annotations

import time

import numpy as np

from .screen import to_np


def cursor_at(vm, x: int, y: int, park=(5, 5), radius: int = 40):
    vm.move_to(x, y)
    time.sleep(0.15)
    a = vm.screenshot()
    vm.move_to(*park)
    time.sleep(0.15)
    b = vm.screenshot()
    d = np.abs(to_np(a) - to_np(b)).max(axis=2) > 24
    x0, y0 = max(0, x - radius), max(0, y - radius)
    sub = d[y0:y + radius, x0:x + radius]
    ys, xs = np.nonzero(sub)
    if len(xs) == 0:
        return None
    return int(xs.min()) + x0, int(ys.min()) + y0


def check_pointer(vm, points=None, tol: int = 1):
    """Return list of (target, seen, ok)."""
    if points is None:
        w, h = vm.screenshot().size
        points = [(w // 2, h // 2), (100, 100), (w - 120, 90), (130, h - 140), (w - 200, h - 160)]
    out = []
    for (x, y) in points:
        seen = cursor_at(vm, x, y)
        ok = seen is not None and abs(seen[0] - x) <= tol and abs(seen[1] - y) <= tol
        out.append(((x, y), seen, ok))
    return out
