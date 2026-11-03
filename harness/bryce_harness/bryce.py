"""Bryce 2 (Windows) actions on top of the VM layer.

Geometry: Bryce draws one light "palette frame" centred on a black desktop. Its size follows the
document size, so every UI position is stored relative to the frame's top-left corner (the left
column and the top palettes are anchored there). `frame_box()` finds the frame in a screenshot.

ui_map.json was produced by hovering (see probe.py): Bryce names the control under the pointer
in the bottom-left corner of the frame, so each entry is a verified hit, not a guess.
`bry ui NAME` clicks one, `bry ui --list` lists them.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

from . import screen
from .probe import frame_box, read_label
from .vm import VM

UI_MAP = Path(__file__).with_name("ui_map.json")

# view (render area) inside the frame: fixed offsets from the frame edges
VIEW_INSET = (141, 80, 21, 21)          # left, top, right, bottom
BACKGROUND = (12, 750)                  # a black desktop spot: clicking it gives Bryce focus, does nothing else


def load_map() -> dict:
    try:
        return json.loads(UI_MAP.read_text())
    except FileNotFoundError:
        return {}


def view_box(fb) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = fb
    l, t, r, b = VIEW_INSET
    return x0 + l, y0 + t, x1 - r, y1 - b


def _lookup(name: str) -> list:
    node = load_map()
    for part in name.split("."):
        if part not in node:
            # allow case-insensitive / partial last component
            cands = [k for k in node if k.lower() == part.lower()] or \
                    [k for k in node if part.lower() in k.lower() and not k.startswith("_")]
            if len(cands) != 1:
                raise KeyError(f"{name}: {'ambiguous ' + str(cands) if cands else 'not in ui_map'}")
            part = cands[0]
        node = node[part]
    return node["at"] if isinstance(node, dict) else node


def ui_point(vm: VM, name: str, img=None) -> tuple[int, int]:
    rx, ry = _lookup(name)
    fb = frame_box(img or vm.screenshot())
    return fb[0] + int(rx), fb[1] + int(ry)


def ui_click(vm: VM, name: str, double: bool = False, verify: bool = True):
    """Click a mapped control. With verify, hover first and check Bryce's label names it."""
    img = vm.screenshot()
    x, y = ui_point(vm, name, img)
    if verify:
        vm.move_to(x, y)
        time.sleep(0.4)
        got = read_label(vm.screenshot())
        want = name.split(".")[-1]
        if want.lower() not in got.lower():
            raise RuntimeError(f"hover check failed for {name}: Bryce says {got!r}")
    vm.click(x, y, double=double)


def flatten(d: dict, prefix: str = "") -> list[tuple[str, object]]:
    out = []
    for k, v in d.items():
        if k.startswith("_"):
            continue
        key = f"{prefix}{k}"
        if isinstance(v, dict) and "at" not in v:
            out += flatten(v, key + ".")
        else:
            out.append((key, v))
    return out


def focus(vm: VM):
    """Give Bryce keyboard focus without touching the scene.
    Wine: via the window system (a click outside Bryce makes it hide its palettes until restart).
    VM: a click on the black desktop area, which belongs to Bryce's maximized window there."""
    vm.key("esc")
    if hasattr(vm, "focus_app"):
        vm.focus_app()
    else:
        vm.click(*BACKGROUND)
    time.sleep(0.3)


# ---------------------------------------------------------------- rendering

def progress_line(img, box) -> int | None:
    """Row of Bryce's render scan line (a 1-px light ridge across the whole view), or None."""
    a = np.asarray(img.convert("RGB"), dtype=np.int32)
    x0, y0, x1, y1 = box
    v = a[y0 + 2:y1 - 2, x0 + 2:x1 - 2].sum(2)
    up, mid, dn = v[:-2], v[1:-1], v[2:]
    # a 1-px ridge: brighter than BOTH neighbours (an edge such as the view's top border is not)
    ridge = (mid - up > 20) & (mid - dn > 20) & (mid - (up + dn) / 2 > 40)
    frac = ridge.mean(1)
    ys = np.where(frac > 0.8)[0]
    return int(ys[0] + y0 + 3) if len(ys) else None


def is_rendering(vm: VM, samples: int = 3, gap: float = 2.0) -> bool:
    img = vm.screenshot()
    box = view_box(frame_box(img))
    for i in range(samples):
        if progress_line(img, box) is not None:
            return True
        if i < samples - 1:
            time.sleep(gap)
            img = vm.screenshot()
    return False


def wait_render(vm: VM, timeout: float = 6 * 3600, poll: float = 5.0, log=None):
    """Wait until Bryce's render is finished: no scan line in 3 samples and the view unchanged.
    Never sends input (any key or click would stop the render). Returns the final screenshot."""
    end = time.time() + timeout
    t0 = time.time()
    img = vm.screenshot()
    box = view_box(frame_box(img))
    quiet = 0
    prev = img
    last_line = None
    while time.time() < end:
        time.sleep(poll)
        img = vm.screenshot()
        line = progress_line(img, box)
        changed = screen.diff_fraction(prev.crop(box), img.crop(box), tol=2) > 0
        prev = img
        if line is None and not changed:
            quiet += 1
            if quiet >= 3:
                return img
        else:
            quiet = 0
            if log and line is not None and line != last_line:
                log(f"{time.time() - t0:7.0f}s  scan line at y={line}")
                last_line = line
    raise TimeoutError("render did not finish")


def render(vm: VM, **kw):
    focus(vm)
    vm.key("ctrl-r")
    time.sleep(3)
    return wait_render(vm, **kw)


# ---------------------------------------------------------------- files

def _file_dialog(vm: VM, path: str, settle: float = 2.0):
    """Type a full path into a standard Win32 open/save dialog and confirm."""
    time.sleep(settle)
    vm.key("alt-n")             # File name: field
    vm.key("ctrl-a")
    vm.type(path)
    vm.key("ret")


def open_scene(vm: VM, path: str, wait: float = 8.0):
    """File > Open (Ctrl+O). Answers a 'save changes?' prompt with No."""
    focus(vm)
    vm.key("ctrl-o")
    time.sleep(2)
    img = vm.screenshot()
    if screen.find_text(img, "Save changes") or screen.find_text(img, "save"):
        vm.key("n")
        time.sleep(1.5)
    _file_dialog(vm, path)
    time.sleep(wait)
    return screen.wait_stable(vm, settle=2.0, timeout=120)


# ---------------------------------------------------------------- menus & dialogs

MENU_X = {"File": 14, "Edit": 45, "Objects": 85}


def menu(vm, top: str, item: str, settle: float = 0.8):
    """Pick a Win32 menu item by OCR. Bryce hides its menu bar until the pointer touches the
    top edge, so hover there first, open the top-level menu, then find the item text."""
    vm.key("esc")
    vm.move_to(MENU_X[top] + 40, 2)
    time.sleep(0.6)
    pos = screen.find_text(vm.screenshot(), top, box=(0, 0, 300, 40))
    vm.click(*(pos or (MENU_X[top], 17)))
    time.sleep(settle)
    img = vm.screenshot()
    pos = screen.find_text(img, item, box=(0, 20, 420, 420))
    if not pos:
        vm.key("esc")
        raise RuntimeError(f"menu item {top} > {item} not found")
    vm.click(*pos)
    time.sleep(settle)


def _dismiss_save_changes(vm):
    img = vm.screenshot()
    if screen.find_text(img, "save changes") or screen.find_text(img, "Save changes"):
        vm.key("n")
        time.sleep(1.0)


def save_as(vm, path: str):
    """File > Save As... to a Bryce-side path (W:\\x.brc). Overwrites."""
    menu(vm, "File", "Save As")
    _file_dialog(vm, path, settle=1.0)
    time.sleep(1.0)
    img = vm.screenshot()
    if screen.find_text(img, "replace") or screen.find_text(img, "already exists"):
        vm.key("y")
        time.sleep(1.0)
    screen.wait_stable(vm, settle=1.0, timeout=60)


def new_scene(vm):
    focus(vm)
    vm.key("ctrl-n")
    time.sleep(1.5)
    _dismiss_save_changes(vm)
    screen.wait_stable(vm, settle=1.0, timeout=30)


def render_to_disk(vm, path: str, width: int, wait_file=None, timeout: float = 6 * 3600):
    """File > Render to Disk...: width in pixels (height follows the document's aspect),
    saved as BMP at a Bryce-side path. With wait_file (the host path of the same file),
    blocks until Bryce has finished writing it."""
    import os
    if wait_file and os.path.exists(wait_file):
        os.unlink(wait_file)
    menu(vm, "File", "Render to Disk")
    time.sleep(0.5)
    img = vm.screenshot()
    pos = screen.find_text(img, "Output Size in Pixels", box=view_box(frame_box(img)))
    if not pos:
        raise RuntimeError("Render to Disk dialog not found")
    # the width field sits 104 px right of the label's centre (measured, both backends)
    vm.click(pos[0] + 104, pos[1] - 3, double=True)
    vm.key("ctrl-a"); vm.type(str(width)); vm.key("tab")
    time.sleep(0.4)
    # the confirm tick sits at the dialog's bottom-right; Enter also confirms
    vm.key("ret")
    time.sleep(1.5)
    _file_dialog(vm, path, settle=0.5)
    time.sleep(1.0)
    img = vm.screenshot()
    if screen.find_text(img, "replace") or screen.find_text(img, "already exists"):
        vm.key("y")
    if wait_file:
        # Bryce creates the BMP full-size at once and writes rows in chunks (~20 s apart on heavy
        # scenes), so file size/mtime say nothing. It keeps the file open until the render is done:
        # wait for the file to appear, be opened, then closed (Wine: /proc/<pid>/fd).
        t0 = time.time()
        seen_open = False
        while time.time() - t0 < timeout:
            if os.path.exists(wait_file):
                if hasattr(vm, "holds_open"):
                    if vm.holds_open(wait_file):
                        seen_open = True
                    elif seen_open or time.time() - os.path.getmtime(wait_file) > 10:
                        time.sleep(0.5)
                        return wait_file
                elif time.time() - os.path.getmtime(wait_file) > 45 and not is_rendering_disk(vm):
                    return wait_file           # VM backend: no fd view, fall back to a long quiet period
            if hasattr(vm, "running") and not vm.running():
                raise RuntimeError("Bryce exited during Render to Disk")
            time.sleep(1.0)
        raise TimeoutError("render to disk did not finish")


def is_rendering_disk(vm) -> bool:
    """Bryce shows a progress window while rendering to disk."""
    img = vm.screenshot()
    return bool(screen.find_text(img, "Rendering") or screen.find_text(img, "Stop"))


def render_job(scene_host: str, out_host: str, width: int, timeout: float = 6 * 3600, fresh: bool = True,
               instance=None, antialias=None, mode=None):
    """Wine backend, the production path: restart Bryce (clean screen state), open a .brc that
    lives under work/, set the session Render Options (antialias 'off'/'normal'/'supreme', mode
    'mask'/...; also read from the scene's .render.json sidecar), Render to Disk at `width` px
    (height follows the document aspect, see brc_scene.set_document), and wait until Bryce has
    closed the BMP. Paths are host paths; returns the output path.
    instance: (display, prefix) to use a specific Bryce instance (see winebox.WineBryce)."""
    from . import brc_scene
    return brc_scene.render(scene_host, out_host, width, antialias=antialias, mode=mode,
                            timeout=timeout, instance=instance)
