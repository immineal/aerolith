"""`bry` command line: drive Bryce from a shell, one action per call.

Backends: the Win98 VM (default) or Bryce under Wine (`--wine` or BRY_BACKEND=wine; native speed).
Wine-side paths: W:\\ = work/, R:\\ = build/cd (Bryce CD content), B:\\ = the Bryce folder."""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from . import screen
from .vm import VM, RUN

SHOTS = RUN / "shots"


def _shot_path(name: str | None) -> Path:
    SHOTS.mkdir(parents=True, exist_ok=True)
    if name:
        return Path(name)
    return SHOTS / f"{time.strftime('%H%M%S')}_{int(time.time()*1000)%1000:03d}.png"


def main(argv=None):
    ap = argparse.ArgumentParser(prog="bry", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("start", help="boot the VM")
    s.add_argument("--floppy"); s.add_argument("--cdrom"); s.add_argument("--boot", default="c")
    s.add_argument("--kvm", action="store_true", help="use KVM (breaks Win98 unless EPT/NPT is off: SHLWAPI errors)")
    s.add_argument("--loadvm", help="start straight into a saved snapshot")
    s.add_argument("--cache", default="writeback", help="QEMU disk cache mode (unsafe for installs)")
    sub.add_parser("stop", help="hard power-off")
    sub.add_parser("status")

    s = sub.add_parser("shot", help="screenshot -> PNG (prints path)")
    s.add_argument("out", nargs="?"); s.add_argument("--grid", type=int, default=0)
    s.add_argument("--crop", help="x0,y0,x1,y1"); s.add_argument("--zoom", type=int, default=1)
    s.add_argument("--stable", action="store_true", help="wait for the screen to settle first")

    s = sub.add_parser("wait", help="wait until the screen is stable")
    s.add_argument("--settle", type=float, default=1.0); s.add_argument("--timeout", type=float, default=60)

    s = sub.add_parser("key", help="press key combos, e.g. ret, alt-f4, ctrl-s")
    s.add_argument("combos", nargs="+"); s.add_argument("--delay", type=float, default=0.15)
    s = sub.add_parser("type", help="type literal text (US layout)")
    s.add_argument("text")

    for name in ("click", "dclick", "rclick", "move"):
        s = sub.add_parser(name); s.add_argument("x", type=int); s.add_argument("y", type=int)
    s = sub.add_parser("drag"); [s.add_argument(a, type=int) for a in ("x0", "y0", "x1", "y1")]
    s.add_argument("--steps", type=int, default=20); s.add_argument("--right", action="store_true")

    s = sub.add_parser("ocr", help="OCR the screen or a region")
    s.add_argument("--crop"); s.add_argument("--words", action="store_true")
    s = sub.add_parser("findtext", help="print screen coords of a text on screen")
    s.add_argument("text"); s.add_argument("--crop")
    s = sub.add_parser("clicktext", help="OCR-locate text and click it")
    s.add_argument("text"); s.add_argument("--crop"); s.add_argument("--double", action="store_true")

    s = sub.add_parser("cd", help="insert ISO into the CD drive (or 'eject')"); s.add_argument("iso")
    s = sub.add_parser("floppy", help="insert floppy image (or 'eject')"); s.add_argument("img")
    s = sub.add_parser("savevm"); s.add_argument("name")
    s = sub.add_parser("loadvm"); s.add_argument("name")
    sub.add_parser("snapshots")
    s = sub.add_parser("hmp", help="raw human-monitor command"); s.add_argument("line")
    sub.add_parser("selftest", help="verify screen/pointer/keyboard/transfer at the Win98 desktop")
    s = sub.add_parser("pointer", help="closed-loop pointer check at a point"); s.add_argument("x", type=int); s.add_argument("y", type=int)
    s = sub.add_parser("run", help="Start > Run a command line in the guest"); s.add_argument("command")
    s = sub.add_parser("pull", help="copy a file from guest D: to the host")
    s.add_argument("guest_path"); s.add_argument("host_dest")
    s = sub.add_parser("xls", help="list a directory on guest D:"); s.add_argument("guest_dir", nargs="?", default="D:\\")
    s = sub.add_parser("push", help="put host files on an ISO in the guest CD drive (E:)")
    s.add_argument("files", nargs="+"); s.add_argument("--label", default="HOSTFILES")

    # ---- Bryce level
    s = sub.add_parser("frame", help="print Bryce's palette frame and view boxes")
    s = sub.add_parser("label", help="what Bryce's hover help says under the pointer (optionally move first)")
    s.add_argument("x", type=int, nargs="?"); s.add_argument("y", type=int, nargs="?")
    s = sub.add_parser("ui", help="click a control from ui_map.json (hover-verified)")
    s.add_argument("name", nargs="?"); s.add_argument("--list", action="store_true")
    s.add_argument("--double", action="store_true"); s.add_argument("--no-verify", action="store_true")
    s.add_argument("--move", action="store_true", help="only hover, print the label")
    s = sub.add_parser("probe", help="hover-scan a frame-relative region and list Bryce's control labels")
    s.add_argument("region", help="x0,y0,x1,y1 relative to the frame"); s.add_argument("--step", type=int, default=8)
    s = sub.add_parser("render", help="Ctrl+R and wait until the render is finished")
    s.add_argument("--no-wait", action="store_true"); s.add_argument("out", nargs="?", help="save final view crop")
    s = sub.add_parser("waitrender", help="wait for a running render to finish (sends no input)")
    s.add_argument("out", nargs="?")
    s = sub.add_parser("rendering", help="exit 0 if a render is in progress")
    s = sub.add_parser("open", help="open a .BRC scene (guest path)"); s.add_argument("path")

    argv = list(sys.argv[1:] if argv is None else argv)
    wine = os.environ.get("BRY_BACKEND") == "wine"
    if "--wine" in argv:
        argv.remove("--wine"); wine = True
    a = ap.parse_args(argv)
    if wine:
        from .winebox import WineBryce
        vm = WineBryce()
        if a.cmd == "start":
            vm.start(); print("Bryce running under Wine on DISPLAY", vm.display); return 0
    else:
        vm = VM()
    crop = tuple(int(v) for v in a.crop.split(",")) if getattr(a, "crop", None) else None

    if a.cmd == "start":
        vm.start(floppy=a.floppy, cdrom=a.cdrom, boot=a.boot, accel="kvm" if a.kvm else "tcg", cache=a.cache)
        if a.loadvm:
            vm.loadvm(a.loadvm)
        print("started; VNC on 127.0.0.1:5905")
    elif a.cmd == "stop":
        vm.stop(); print("stopped")
    elif a.cmd == "status":
        print(vm.status())
    elif a.cmd in ("shot",):
        img = screen.wait_stable(vm) if a.stable else vm.screenshot()
        if crop:
            img = img.crop(crop)
        if a.zoom > 1:
            img = img.resize((img.width * a.zoom, img.height * a.zoom))
        if a.grid:
            img = screen.grid(img, a.grid)
        p = _shot_path(a.out); img.save(p); print(p)
    elif a.cmd == "wait":
        screen.wait_stable(vm, settle=a.settle, timeout=a.timeout); print("stable")
    elif a.cmd == "key":
        for c in a.combos:
            vm.key(c); time.sleep(a.delay)
    elif a.cmd == "type":
        vm.type(a.text)
    elif a.cmd == "click":
        vm.click(a.x, a.y)
    elif a.cmd == "dclick":
        vm.click(a.x, a.y, double=True)
    elif a.cmd == "rclick":
        vm.click(a.x, a.y, button="right")
    elif a.cmd == "move":
        vm.move_to(a.x, a.y)
    elif a.cmd == "drag":
        vm.drag(a.x0, a.y0, a.x1, a.y1, steps=a.steps, button="right" if a.right else "left")
    elif a.cmd == "ocr":
        img = vm.screenshot()
        if a.words:
            for w in screen.ocr_words(img, box=crop):
                print(*w)
        else:
            print(screen.ocr(img, box=crop))
    elif a.cmd in ("findtext", "clicktext"):
        pos = screen.find_text(vm.screenshot(), a.text, box=crop)
        if not pos:
            print("not found", file=sys.stderr); return 1
        print(*pos)
        if a.cmd == "clicktext":
            vm.click(*pos, double=a.double)
    elif a.cmd == "cd":
        vm.change_cd(None if a.iso == "eject" else Path(a.iso).resolve())
    elif a.cmd == "floppy":
        vm.change_floppy(None if a.img == "eject" else Path(a.img).resolve())
    elif a.cmd == "savevm":
        vm.savevm(a.name); print("saved", a.name)
    elif a.cmd == "loadvm":
        vm.loadvm(a.name); print("loaded", a.name)
    elif a.cmd == "snapshots":
        print(vm.snapshots())
    elif a.cmd == "hmp":
        print(vm.hmp(a.line))
    elif a.cmd == "selftest":
        from .selftest import selftest; return 0 if selftest(vm) else 1
    elif a.cmd == "pointer":
        from .calib import cursor_at; print(cursor_at(vm, a.x, a.y))
    elif a.cmd == "run":
        from .selftest import run_dialog; run_dialog(vm, a.command)
    elif a.cmd == "pull":
        from . import xfer; print(xfer.pull(vm, a.guest_path, a.host_dest))
    elif a.cmd == "xls":
        from . import xfer; print(xfer.ls(vm, a.guest_dir))
    elif a.cmd == "push":
        from . import xfer; print(xfer.push(vm, a.files, a.label))
    elif a.cmd in ("frame", "label", "ui", "probe", "render", "waitrender", "rendering", "open"):
        return _bryce(vm, a)
    return 0


def _bryce(vm: VM, a) -> int:
    from . import bryce, probe
    if a.cmd == "frame":
        fb = bryce.frame_box(vm.screenshot()); print("frame", *fb); print("view ", *bryce.view_box(fb))
    elif a.cmd == "label":
        if a.x is not None:
            vm.move_to(a.x, a.y); time.sleep(0.4)
        print(bryce.read_label(vm.screenshot()))
    elif a.cmd == "ui":
        if a.list or not a.name:
            for k, v in bryce.flatten(bryce.load_map()):
                print(f"{k:50s} {v['at'] if isinstance(v, dict) else v}")
        elif a.move:
            x, y = bryce.ui_point(vm, a.name); vm.move_to(x, y); time.sleep(0.4)
            print(x, y, bryce.read_label(vm.screenshot()))
        else:
            bryce.ui_click(vm, a.name, double=a.double, verify=not a.no_verify)
    elif a.cmd == "probe":
        import json
        res = probe.probe_region(vm, tuple(int(v) for v in a.region.split(",")), a.step)
        print(json.dumps(res, indent=1))
    elif a.cmd in ("render", "waitrender"):
        log = lambda m: print(m, flush=True)
        if a.cmd == "render":
            bryce.focus(vm); vm.key("ctrl-r")
            if a.no_wait:
                return 0
            time.sleep(3)
        img = bryce.wait_render(vm, log=log)
        out = _shot_path(a.out)
        img.crop(bryce.view_box(bryce.frame_box(img))).save(out); print("done", out)
    elif a.cmd == "rendering":
        r = bryce.is_rendering(vm); print("rendering" if r else "idle"); return 0 if r else 1
    elif a.cmd == "open":
        bryce.open_scene(vm, a.path); print("opened", a.path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
