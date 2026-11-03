"""Bryce 2 under Wine on a private Xvfb display: same Bryce2.exe as in the VM, native speed.

Exposes the same input/screen interface as vm.VM (screenshot, key, type, move_to, click, drag,
home), so bryce.py works unchanged on either backend.

Layout:
    wine/prefix          WINEPREFIX (drives: B: = wine/bryce2, W: = work/, R: = build/cd)
    wine/bryce2          Bryce 2 program folder, copied out of the VM install
    work/                host<->Bryce exchange folder, W:\\ inside Bryce
"""
from __future__ import annotations

import io
import os
import signal
import subprocess
import time
from pathlib import Path

from PIL import Image

from .vm import ROOT

WINE = ROOT / "wine"
PREFIX = Path(os.environ.get("BRYCE_PREFIX", WINE / "prefix"))   # a second instance needs its own prefix
BRYCE_DIR = WINE / "bryce2"
WORK = ROOT / "work"
RUN = WINE / ("run" + os.environ.get("BRYCE_DISPLAY", ":77").replace(":", "_"))
DISPLAY = os.environ.get("BRYCE_DISPLAY", ":77")
SCREEN = os.environ.get("BRYCE_SCREEN", "1280x1024x24")

# vm.py key names -> X keysyms
KEYSYMS = {"ret": "Return", "enter": "Return", "return": "Return", "esc": "Escape", "escape": "Escape",
           "tab": "Tab", "spc": "space", "space": "space", "bs": "BackSpace", "backspace": "BackSpace",
           "del": "Delete", "delete": "Delete", "ins": "Insert", "insert": "Insert", "home": "Home",
           "end": "End", "pgup": "Prior", "pgdn": "Next", "pageup": "Prior", "pagedown": "Next",
           "up": "Up", "down": "Down", "left": "Left", "right": "Right", "ctrl": "ctrl", "control": "ctrl",
           "alt": "alt", "shift": "shift", "win": "super", "minus": "minus", "equal": "equal",
           "dot": "period", "comma": "comma", "slash": "slash", "backslash": "backslash"}


def _keysym(p: str) -> str:
    p = p.strip()
    lo = p.lower()
    if lo in KEYSYMS:
        return KEYSYMS[lo]
    if len(lo) >= 2 and lo[0] == "f" and lo[1:].isdigit():
        return "F" + lo[1:]
    return lo


class WineBryce:
    """One Bryce instance = one Wine prefix + one X display. Defaults come from BRYCE_PREFIX /
    BRYCE_DISPLAY; pass both explicitly to drive several instances from one process."""

    def __init__(self, display: str | None = None, prefix: str | Path | None = None):
        self.display = display or DISPLAY
        self.prefix = Path(prefix) if prefix else PREFIX
        self.run = WINE / ("run" + self.display.replace(":", "_"))
        self.env = dict(os.environ, DISPLAY=self.display, WINEPREFIX=str(self.prefix), WINEDEBUG="-all",
                        WINEDLLOVERRIDES="mscoree,mshtml=")
        self.env.pop("WAYLAND_DISPLAY", None)
        self.run.mkdir(parents=True, exist_ok=True)
        WORK.mkdir(exist_ok=True)

    # ------------------------------------------------------------ lifecycle
    def _x(self, *args, check=True, capture=False):
        return subprocess.run(list(args), env=self.env, check=check,
                              capture_output=capture, text=capture)

    def xvfb_running(self) -> bool:
        return self._x("xdpyinfo", check=False, capture=True).returncode == 0 if \
            subprocess.run(["which", "xdpyinfo"], capture_output=True).returncode == 0 else \
            Path(f"/tmp/.X11-unix/X{self.display.lstrip(':')}").exists()

    def pids(self) -> list[int]:
        """Bryce2.exe processes of *this* prefix (several instances may run in separate prefixes)."""
        r = subprocess.run(["pgrep", "Bryce2.exe"], capture_output=True, text=True)
        out = []
        for pid in r.stdout.split():
            try:
                env = Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
            except OSError:
                continue
            if f"WINEPREFIX={self.prefix}".encode() in env:
                out.append(int(pid))
        return out

    def running(self) -> bool:
        return bool(self.pids())

    def holds_open(self, host_path) -> bool:
        """True while a Bryce process of this prefix has the file open (Render to Disk keeps the
        BMP open until the last row is written; the file is full-size from the start)."""
        target = str(Path(host_path).resolve())
        for pid in self.pids():
            try:
                fds = list(Path(f"/proc/{pid}/fd").iterdir())
            except OSError:
                continue
            for fd in fds:
                try:
                    if os.readlink(fd) == target:
                        return True
                except OSError:
                    pass
        return False

    def start(self, timeout: float = 60, scene: str | None = None):
        if not Path(f"/tmp/.X11-unix/X{self.display.lstrip(':')}").exists():
            subprocess.Popen(["Xvfb", self.display, "-screen", "0", SCREEN, "-nolisten", "tcp"],
                             stdout=open(self.run / "xvfb.log", "w"), stderr=subprocess.STDOUT,
                             start_new_session=True)
            time.sleep(1.0)
        if self.running():
            return
        w, h = SCREEN.split("x")[:2]
        mode = os.environ.get("BRYCE_WINE_MODE", "bare")   # "wm" (twm) wedged the X server; "desktop" loses palettes
        if mode == "desktop":       # Wine virtual desktop
            cmd = ["wine", "explorer", f"/desktop=Bryce,{w}x{h}", "B:\\Bryce2.exe"]
        else:                       # plain X windows under a minimal window manager
            if mode == "wm" and subprocess.run(["pgrep", "-f", f"twm -display {self.display} "],
                                               capture_output=True).returncode != 0:
                # twm's default asks for interactive window placement and grabs the server: use wine/twmrc
                subprocess.Popen(["twm", "-display", self.display, "-f", str(WINE / "twmrc")], stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, start_new_session=True)
                time.sleep(0.5)
            cmd = ["wine", "B:\\Bryce2.exe"] + ([scene] if scene else [])
        subprocess.Popen(cmd, cwd=BRYCE_DIR, env=self.env,
                         stdout=open(self.run / "wine.log", "w"), stderr=subprocess.STDOUT,
                         start_new_session=True)
        end = time.time() + timeout
        while time.time() < end:
            if self.running():
                time.sleep(4)          # palettes finish drawing
                return
            time.sleep(0.5)
        raise TimeoutError("Bryce window did not appear")

    def focus_app(self):
        """Give Bryce keyboard focus without a click (clicking outside Bryce makes it drop its palettes)."""
        r = self._x("xdotool", "search", "--name", "^Bryce2$", check=False, capture=True)
        for wid in r.stdout.split():
            self._x("xdotool", "windowactivate", "--sync", wid, check=False, capture=True)
            self._x("xdotool", "windowfocus", "--sync", wid, check=False, capture=True)
            break

    def stop(self):
        subprocess.run(["wineserver", "-k"], env=self.env, check=False)

    def status(self) -> str:
        return "running" if self.running() else "stopped"

    def close(self):
        pass

    # ------------------------------------------------------------ screen
    def screenshot(self, path: str | Path | None = None) -> Image.Image:
        r = subprocess.run(["import", "-silent", "-window", "root", "png:-"], env=self.env,
                           capture_output=True, check=True)
        img = Image.open(io.BytesIO(r.stdout)).convert("RGB")
        if path:
            img.save(path)
        return img

    # ------------------------------------------------------------ keyboard
    def key(self, combo: str, hold: float = 0.05):
        parts = combo.split("+") if "+" in combo and combo != "+" else combo.split("-") if combo != "-" else ["minus"]
        self._x("xdotool", "key", "--clearmodifiers", "+".join(_keysym(p) for p in parts))
        time.sleep(0.05)

    def press(self, codes: list[str], hold: float = 0.05):
        self._x("xdotool", "key", "+".join(_keysym(c) for c in codes))

    def type(self, text: str, delay: float = 0.02):
        self._x("xdotool", "type", "--delay", str(int(delay * 1000)), text)

    # ------------------------------------------------------------ mouse (absolute)
    def home(self):
        self.move_to(0, 0)

    def move_to(self, x: int, y: int, rehome: bool = True):
        self._x("xdotool", "mousemove", str(x), str(y))
        time.sleep(0.03)

    def button(self, down: bool, button: str = "left"):
        b = {"left": "1", "middle": "2", "right": "3"}[button]
        self._x("xdotool", "mousedown" if down else "mouseup", b)

    def click(self, x: int, y: int, button: str = "left", double: bool = False, rehome: bool = True):
        self.move_to(x, y)
        for _ in range(2 if double else 1):
            self.button(True, button); time.sleep(0.05)
            self.button(False, button); time.sleep(0.08)

    def drag(self, x0: int, y0: int, x1: int, y1: int, steps: int = 20, button: str = "left",
             hold: float = 0.15):
        self.move_to(x0, y0)
        self.button(True, button)
        time.sleep(hold)
        for i in range(1, steps + 1):
            self.move_to(x0 + round((x1 - x0) * i / steps), y0 + round((y1 - y0) * i / steps))
            time.sleep(0.02)
        time.sleep(hold)
        self.button(False, button)

    # ------------------------------------------------------------ paths
    @staticmethod
    def guest_path(host: str | Path) -> str:
        """Host path under work/ or build/cd -> Bryce-side path (W:\\..., R:\\...)."""
        p = Path(host).resolve()
        for root, drive in ((WORK.resolve(), "W:"), ((ROOT / "build" / "cd").resolve(), "R:")):
            try:
                rel = p.relative_to(root)
                return drive + "\\" + str(rel).replace("/", "\\")
            except ValueError:
                pass
        raise ValueError(f"{host} is not under work/ or build/cd/")
