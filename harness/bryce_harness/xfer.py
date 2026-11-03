"""File transfer between host and guest.

guest -> host: the guest saves into D:\\ (the transfer disk). `pull()` takes a point-in-time copy
               of that disk with QEMU's blockdev-backup and reads files out of the copy with mtools.
               The guest has write-behind caching disabled, so a file is on disk once the app's save finishes.
host -> guest: `push()` builds an ISO 9660/Joliet image from host files and inserts it in the
               CD drive (E:\\).  Never write into the transfer disk from the host while the VM runs.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from .vm import VM, RUN

PART_OFFSET = 63 * 512
XFER_NODE = "disk1"
SNAP = RUN / "xfer_snapshot.raw"
PUSH_DIR = RUN / "push"


def snapshot_xfer(vm: VM) -> Path:
    """Copy the live transfer disk (guest D:) to SNAP, consistently, while the VM keeps running."""
    q = vm.qmp()
    size = None
    for b in q.cmd("query-block"):
        if b.get("device") == "ide0-hd1":
            size = b["inserted"]["image"]["virtual-size"]
    if size is None:
        raise RuntimeError("transfer disk not attached")
    SNAP.unlink(missing_ok=True)
    subprocess.run(["qemu-img", "create", "-q", "-f", "raw", str(SNAP), str(size)], check=True)
    node = f"xsnap{int(time.time()*1000)%100000}"
    q.cmd("blockdev-add", **{"driver": "raw", "node-name": node,
                              "file": {"driver": "file", "filename": str(SNAP)}})
    try:
        job = node + "job"
        q.cmd("blockdev-backup", **{"job-id": job, "device": XFER_NODE, "target": node, "sync": "full"})
        end = time.time() + 120
        while time.time() < end:
            jobs = {j["id"]: j for j in q.cmd("query-jobs")}
            j = jobs.get(job)
            if j is None or j["status"] in ("concluded", "null"):
                if j and j.get("error"):
                    raise RuntimeError(j["error"])
                if j:
                    q.cmd("job-dismiss", id=job)
                break
            time.sleep(0.1)
        else:
            raise TimeoutError("blockdev-backup did not finish")
    finally:
        q.cmd("blockdev-del", **{"node-name": node})
    return SNAP


def _mimg(img: Path) -> str:
    return f"{img}@@{PART_OFFSET}"


def _guest_to_mtools(path: str) -> str:
    p = path.replace("\\", "/")
    if len(p) >= 2 and p[1] == ":":
        if p[0].upper() != "D":
            raise ValueError("only files on D: (the transfer disk) can be pulled")
        p = p[2:]
    return "::" + (p if p.startswith("/") else "/" + p)


def ls(vm: VM, guest_dir: str = "D:\\", fresh: bool = True) -> str:
    img = snapshot_xfer(vm) if fresh or not SNAP.exists() else SNAP
    env = dict(os.environ, MTOOLS_SKIP_CHECK="1")
    r = subprocess.run(["mdir", "-i", _mimg(img), _guest_to_mtools(guest_dir)],
                       capture_output=True, text=True, env=env)
    return r.stdout + r.stderr


def pull(vm: VM, guest_path: str, host_dest: str | Path, fresh: bool = True) -> Path:
    """Copy a file (or, with a trailing backslash, a directory) from guest D: to the host."""
    img = snapshot_xfer(vm) if fresh or not SNAP.exists() else SNAP
    host_dest = Path(host_dest)
    env = dict(os.environ, MTOOLS_SKIP_CHECK="1")
    args = ["mcopy", "-n", "-o", "-i", _mimg(img)]
    if guest_path.endswith("\\") or guest_path.endswith("/"):
        host_dest.mkdir(parents=True, exist_ok=True)
        args += ["-s", _guest_to_mtools(guest_path.rstrip("\\/")) + "/*", str(host_dest)]
    else:
        host_dest.parent.mkdir(parents=True, exist_ok=True)
        args += [_guest_to_mtools(guest_path), str(host_dest)]
    r = subprocess.run(args, capture_output=True, text=True, env=env)
    if r.returncode != 0:
        raise FileNotFoundError(f"{guest_path}: {r.stderr.strip()}")
    return host_dest


def make_iso(files: list[str | Path], iso: Path, label: str = "HOSTFILES") -> Path:
    """Build an ISO with the given files/dirs at its root (Joliet names, 8.3 fallbacks)."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "root"
        root.mkdir()
        for f in files:
            f = Path(f)
            dst = root / f.name
            if f.is_dir():
                shutil.copytree(f, dst)
            else:
                shutil.copy2(f, dst)
        iso.parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(["xorriso", "-as", "mkisofs", "-quiet", "-J", "-joliet-long", "-iso-level", "2",
                            "-V", label[:32], "-o", str(iso), str(root)], capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"xorriso failed: {r.stderr}")
    return iso


def push(vm: VM, files: list[str | Path], label: str = "HOSTFILES") -> Path:
    """Put host files on a fresh ISO and insert it as the guest CD (E:)."""
    iso = PUSH_DIR / f"push_{int(time.time())}.iso"
    make_iso(files, iso, label)
    vm.change_cd(None)
    time.sleep(1.0)
    vm.change_cd(iso)
    for old in PUSH_DIR.glob("push_*.iso"):        # keep the last few
        if old != iso and time.time() - old.stat().st_mtime > 3600:
            old.unlink(missing_ok=True)
    return iso
