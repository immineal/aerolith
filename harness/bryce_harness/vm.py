"""Windows 98 SE QEMU VM: lifecycle, screen capture, keyboard and mouse input, media and snapshots."""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import time
from pathlib import Path

from PIL import Image

from .qmp import QMP, QMPError

ROOT = Path(__file__).resolve().parents[2]          # ~/Projects/customization
VMDIR = ROOT / "vm"
RUN = VMDIR / "run"                                    # sockets, pidfile, logs, temp files
QMP_SOCK = RUN / "qmp.sock"
QMP_WATCH_SOCK = RUN / "qmp-watch.sock"                 # second monitor for background watchers
PIDFILE = RUN / "qemu.pid"
STATE = RUN / "state.json"
VNC_DISPLAY = 5                                        # vncviewer localhost:5905

# ---------------------------------------------------------------- keyboard
SHIFTED = {'!': '1', '@': '2', '#': '3', '$': '4', '%': '5', '^': '6', '&': '7', '*': '8',
           '(': '9', ')': '0', '_': 'minus', '+': 'equal', '{': 'bracket_left',
           '}': 'bracket_right', '|': 'backslash', ':': 'semicolon', '"': 'apostrophe',
           '~': 'grave_accent', '<': 'comma', '>': 'dot', '?': 'slash'}
PLAIN = {' ': 'spc', '-': 'minus', '=': 'equal', '[': 'bracket_left', ']': 'bracket_right',
         '\\': 'backslash', ';': 'semicolon', "'": 'apostrophe', '`': 'grave_accent',
         ',': 'comma', '.': 'dot', '/': 'slash', '\n': 'ret', '\t': 'tab'}
ALIASES = {'enter': 'ret', 'return': 'ret', 'space': 'spc', 'escape': 'esc', 'del': 'delete',
           'bs': 'backspace', 'win': 'meta_l', 'pageup': 'pgup', 'pagedown': 'pgdn',
           'control': 'ctrl', 'ins': 'insert'}


def char_to_keys(ch: str) -> list[str]:
    if ch.isalpha() and ch.isascii():
        return ['shift', ch.lower()] if ch.isupper() else [ch]
    if ch.isdigit():
        return [ch]
    if ch in SHIFTED:
        return ['shift', SHIFTED[ch]]
    if ch in PLAIN:
        return [PLAIN[ch]]
    raise ValueError(f"cannot type {ch!r} on a US keyboard")


def parse_combo(combo: str) -> list[str]:
    """'ctrl-shift-s' / 'alt+f4' / 'ret' -> list of qcodes."""
    parts = combo.replace('+', '-').split('-') if combo not in ('-', '+') else [combo]
    out = []
    for p in parts:
        p = p.strip().lower()
        p = ALIASES.get(p, p)
        if len(p) == 1 and not p.isalnum():
            p = PLAIN.get(p, SHIFTED.get(p, p))
        out.append(p)
    return out


class VM:
    def __init__(self, watch: bool = False):
        RUN.mkdir(parents=True, exist_ok=True)
        self._q: QMP | None = None
        self._sock = QMP_WATCH_SOCK if watch and QMP_WATCH_SOCK.exists() else QMP_SOCK

    # ------------------------------------------------------------ lifecycle
    @property
    def system_disk(self) -> Path:
        q = VMDIR / "c.qcow2"
        return q if q.exists() else VMDIR / "c.raw"

    @property
    def xfer_disk(self) -> Path:
        q = VMDIR / "xfer.qcow2"
        return q if q.exists() else VMDIR / "xfer.raw"

    def cmdline(self, floppy: str | None = None, cdrom: str | None = None,
                boot: str = "c", accel: str = "tcg", cache: str = "writeback") -> list[str]:
        def drive(path: Path, index: int):
            fmt = "qcow2" if path.suffix == ".qcow2" else "raw"
            # The transfer export (blockdev-backup) reads through QEMU's block layer, so host-side
            # write caching is fine; "unsafe" (no fsync at all) is used for the OS install.
            return ["-drive", f"file={path},if=ide,index={index},format={fmt},cache={cache},node-name=disk{index}"]
        cmd = [
            "qemu-system-i386",
            "-name", "win98-bryce",
            "-machine", f"pc,accel={accel}",
            "-cpu", "pentium3" if accel == "tcg" else "host",
            "-m", "512",
            "-vga", "cirrus",
            "-rtc", "base=localtime",
            "-nic", "none",
            "-display", "none",
            "-vnc", f"127.0.0.1:{VNC_DISPLAY}",
            "-qmp", f"unix:{QMP_SOCK},server=on,wait=off",
            "-qmp", f"unix:{QMP_WATCH_SOCK},server=on,wait=off",
            "-pidfile", str(PIDFILE),
            "-daemonize",
            "-D", str(RUN / "qemu.log"),
        ]
        cmd += drive(self.system_disk, 0)
        cmd += drive(self.xfer_disk, 1)
        cmd += ["-drive", f"if=ide,index=2,media=cdrom,id=cd0" + (f",file={cdrom},format=raw" if cdrom else "")]
        cmd += ["-drive", "if=floppy,index=0,id=fd0" + (f",file={floppy},format=raw" if floppy else "")]
        cmd += ["-boot", f"order={boot}"]
        return cmd

    def running(self) -> bool:
        try:
            pid = int(PIDFILE.read_text())
            os.kill(pid, 0)
            return True
        except (OSError, ValueError):
            return False

    def start(self, **kw):
        if self.running():
            raise RuntimeError("VM already running")
        for p in (QMP_SOCK, QMP_WATCH_SOCK, PIDFILE):
            p.unlink(missing_ok=True)
        cmd = self.cmdline(**kw)
        (RUN / "cmdline.txt").write_text(" ".join(cmd) + "\n")
        subprocess.run(cmd, check=True)
        self.qmp()
        self.set_state(cursor=None)

    def qmp(self) -> QMP:
        if self._q is None:
            # QEMU serves one client per QMP socket; if ours is busy, use the other one.
            socks = [self._sock] + [s for s in (QMP_SOCK, QMP_WATCH_SOCK) if s != self._sock]
            last = None
            for _ in range(3):
                for sp in socks:
                    if not sp.exists():
                        continue
                    try:
                        self._q = QMP(str(sp)).connect(greeting_timeout=1.5)
                        return self._q
                    except QMPError as e:
                        last = e
                time.sleep(1)
            raise QMPError(f"no free QMP socket: {last}")
        return self._q

    def close(self):
        if self._q:
            self._q.close()
            self._q = None

    def stop(self, timeout: float = 5.0):
        """Hard power-off (use only when the guest is idle or after a snapshot)."""
        if not self.running():
            return
        try:
            self.qmp().cmd("quit")
        except (QMPError, OSError):
            pass
        pid = None
        try:
            pid = int(PIDFILE.read_text())
        except (OSError, ValueError):
            pass
        end = time.time() + timeout
        while pid and time.time() < end:
            try:
                os.kill(pid, 0)
            except OSError:
                break
            time.sleep(0.1)
        else:
            if pid:
                os.kill(pid, signal.SIGKILL)
        self._q = None

    def status(self) -> str:
        if not self.running():
            return "stopped"
        return self.qmp().cmd("query-status")["status"]

    # ------------------------------------------------------------ state file
    def get_state(self) -> dict:
        try:
            return json.loads(STATE.read_text())
        except (OSError, ValueError):
            return {}

    def set_state(self, **kw):
        s = self.get_state()
        s.update(kw)
        STATE.write_text(json.dumps(s))

    # ------------------------------------------------------------ screen
    def screenshot(self, path: str | Path | None = None) -> Image.Image:
        tmp = RUN / f"shot_{os.getpid()}.png"
        self.qmp().cmd("screendump", filename=str(tmp), format="png")
        img = Image.open(tmp)
        img.load()
        img = img.convert("RGB")
        if path:
            shutil.move(tmp, path)
        else:
            tmp.unlink(missing_ok=True)
        return img

    # ------------------------------------------------------------ keyboard
    def _keys(self, codes: list[str], down: bool):
        ev = [{"type": "key", "data": {"down": down, "key": {"type": "qcode", "data": c}}} for c in codes]
        self.qmp().cmd("input-send-event", events=ev)

    def key(self, combo: str, hold: float = 0.05):
        self.press(parse_combo(combo), hold)

    def press(self, codes: list[str], hold: float = 0.05):
        for c in codes:              # press modifiers first, one at a time
            self._keys([c], True)
            time.sleep(0.02)
        time.sleep(hold)
        for c in reversed(codes):
            self._keys([c], False)
            time.sleep(0.02)

    def type(self, text: str, delay: float = 0.04):
        for ch in text:
            self.press(char_to_keys(ch), hold=0.02)
            time.sleep(delay)

    # ------------------------------------------------------------ mouse (relative PS/2)
    def _rel(self, dx: int, dy: int, step: int = 60):
        """Send a relative motion, chunked so the PS/2 queue never overflows."""
        while dx or dy:
            sx = max(-step, min(step, dx))
            sy = max(-step, min(step, dy))
            ev = []
            if sx:
                ev.append({"type": "rel", "data": {"axis": "x", "value": sx}})
            if sy:
                ev.append({"type": "rel", "data": {"axis": "y", "value": sy}})
            self.qmp().cmd("input-send-event", events=ev)
            dx -= sx
            dy -= sy
            time.sleep(0.008)

    def home(self):
        """Pin the pointer to the top-left corner; afterwards its position is known: (0,0)."""
        self._rel(-4000, -4000, step=120)
        time.sleep(0.05)
        self.set_state(cursor=[0, 0])

    def move_to(self, x: int, y: int, rehome: bool = True):
        cur = self.get_state().get("cursor")
        if rehome or cur is None:
            self.home()
            cur = [0, 0]
        self._rel(x - cur[0], y - cur[1])
        time.sleep(0.03)
        self.set_state(cursor=[x, y])

    def button(self, down: bool, button: str = "left"):
        self.qmp().cmd("input-send-event", events=[{"type": "btn", "data": {"down": down, "button": button}}])

    def click(self, x: int, y: int, button: str = "left", double: bool = False, rehome: bool = True):
        self.move_to(x, y, rehome=rehome)
        for i in range(2 if double else 1):
            self.button(True, button)
            time.sleep(0.06)
            self.button(False, button)
            time.sleep(0.08)

    def drag(self, x0: int, y0: int, x1: int, y1: int, steps: int = 20, button: str = "left",
             hold: float = 0.15):
        """Press at (x0,y0), move in small steps to (x1,y1), release."""
        self.move_to(x0, y0)
        self.button(True, button)
        time.sleep(hold)
        cx, cy = x0, y0
        for i in range(1, steps + 1):
            nx = x0 + round((x1 - x0) * i / steps)
            ny = y0 + round((y1 - y0) * i / steps)
            self._rel(nx - cx, ny - cy)
            cx, cy = nx, ny
            time.sleep(0.02)
        time.sleep(hold)
        self.button(False, button)
        self.set_state(cursor=[x1, y1])

    # ------------------------------------------------------------ removable media
    def _qdev(self, drive: str) -> str:
        for b in self.qmp().cmd("query-block"):
            if b.get("device") == drive:
                return b["qdev"]
        raise QMPError(f"no drive {drive}")

    def _change(self, drive: str, path):
        q, dev = self.qmp(), self._qdev(drive)
        if path is None:
            q.cmd("eject", id=dev, force=True)
        else:
            q.cmd("blockdev-change-medium", id=dev, filename=str(path), format="raw")

    def change_cd(self, iso: str | Path | None):
        self._change("cd0", iso)

    def change_floppy(self, img: str | Path | None):
        self._change("fd0", img)

    # ------------------------------------------------------------ snapshots
    def savevm(self, name: str):
        out = self.hmp(f"savevm {name}")
        if out.strip():
            raise QMPError(out.strip())

    def loadvm(self, name: str):
        out = self.hmp(f"loadvm {name}")
        if out.strip():
            raise QMPError(out.strip())
        self.set_state(cursor=None)

    def snapshots(self) -> str:
        return self.hmp("info snapshots")

    def hmp(self, line: str) -> str:
        return self.qmp().hmp(line)
