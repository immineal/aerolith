"""VM-level self test. Run at the Win98 desktop (no Bryce needed):

    ./bry selftest

Checks:  screenshot -> pointer accuracy (closed loop, 5 points) -> keyboard (types into Notepad
and reads it back by saving to D:) -> guest->host transfer -> host->guest transfer (push ISO,
copy E:->D: via COMMAND, pull, compare bytes).
"""
from __future__ import annotations

import hashlib
import os
import random
import string
import tempfile
import time
from pathlib import Path

from . import calib, screen, xfer
from .vm import VM


def run_dialog(vm: VM, command: str, settle: float = 1.5):
    """Start > Run... and execute a command line."""
    vm.key("ctrl-esc"); time.sleep(0.6)
    vm.key("r"); time.sleep(0.8)
    vm.key("ctrl-a"); vm.type(command); time.sleep(0.2)
    vm.key("ret"); time.sleep(settle)


def selftest(vm: VM) -> bool:
    ok_all = True

    def report(name, ok, detail=""):
        nonlocal ok_all
        ok_all &= bool(ok)
        print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")

    img = vm.screenshot()
    report("screenshot", img.width >= 640, f"{img.size}")

    res = calib.check_pointer(vm)
    bad = [r for r in res if not r[2]]
    report("pointer accuracy", not bad, " ".join(f"{t}->{s}" for t, s, _ in res))

    # keyboard + guest->host: Notepad, type random text, save to D:, pull, compare
    token = "Bryce harness " + "".join(random.choice(string.ascii_letters + string.digits) for _ in range(16)) + " !@#$%^&*()_+-=[]{};:',.<>/?"
    run_dialog(vm, "notepad", settle=2.5)
    vm.type(token); time.sleep(0.3)
    vm.key("alt-f"); time.sleep(0.4); vm.key("s"); time.sleep(1.5)   # Win98 Notepad has no Ctrl+S
    vm.type("D:\\KEYTEST.TXT"); vm.key("ret"); time.sleep(1.2)
    # overwrite prompt if the file exists
    if screen.find_text(vm.screenshot(), "replace") or screen.find_text(vm.screenshot(), "already exists"):
        vm.key("y"); time.sleep(1.0)
    vm.key("alt-f4"); time.sleep(1.0)
    with tempfile.TemporaryDirectory() as td:
        dst = Path(td) / "k.txt"
        try:
            xfer.pull(vm, "D:\\KEYTEST.TXT", dst)
            got = dst.read_bytes().decode("latin1")
        except FileNotFoundError as e:
            got = f"<missing: {e}>"
        report("keyboard + pull", got == token, f"{got!r}" if got != token else "")

        # host->guest: push a random binary, copy E:->D: in the guest, pull back, compare hashes
        blob = Path(td) / "BLOB.BIN"
        blob.write_bytes(os.urandom(300_000))
        xfer.push(vm, [blob])
        time.sleep(3)
        run_dialog(vm, "command /c copy E:\\BLOB.BIN D:\\BLOB.BIN", settle=4)
        back = Path(td) / "back.bin"
        try:
            xfer.pull(vm, "D:\\BLOB.BIN", back)
            same = hashlib.sha256(back.read_bytes()).digest() == hashlib.sha256(blob.read_bytes()).digest()
        except FileNotFoundError:
            same = False
        report("push (CD) -> guest copy -> pull", same)
    return ok_all
