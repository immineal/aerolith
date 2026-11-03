"""Minimal synchronous QMP (QEMU Machine Protocol) client over a unix socket."""
from __future__ import annotations

import json
import socket
import time


class QMPError(RuntimeError):
    pass


class QMP:
    def __init__(self, path: str, timeout: float = 30.0):
        self.path = path
        self.timeout = timeout
        self.sock: socket.socket | None = None
        self._buf = b""
        self.events: list[dict] = []

    # -- connection -------------------------------------------------------
    def connect(self, retries: int = 50, greeting_timeout: float | None = None) -> "QMP":
        last = None
        for _ in range(retries):
            try:
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.settimeout(self.timeout)
                s.connect(self.path)
                self.sock = s
                break
            except OSError as e:  # socket not there yet
                last = e
                time.sleep(0.1)
        else:
            raise QMPError(f"cannot connect to {self.path}: {last}")
        if greeting_timeout:
            self.sock.settimeout(greeting_timeout)
        try:
            greeting = self._read_msg()
        except (socket.timeout, TimeoutError):
            self.close()
            raise QMPError(f"{self.path}: busy (another client is connected)")
        self.sock.settimeout(self.timeout)
        if "QMP" not in greeting:
            raise QMPError(f"unexpected greeting {greeting}")
        self.cmd("qmp_capabilities")
        return self

    def close(self):
        if self.sock:
            self.sock.close()
            self.sock = None

    def __enter__(self):
        return self.connect()

    def __exit__(self, *a):
        self.close()

    # -- protocol ---------------------------------------------------------
    def _read_msg(self) -> dict:
        while b"\n" not in self._buf:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise QMPError("QMP socket closed")
            self._buf += chunk
        line, self._buf = self._buf.split(b"\n", 1)
        return json.loads(line)

    def cmd(self, execute: str, **arguments):
        msg = {"execute": execute}
        if arguments:
            msg["arguments"] = arguments
        self.sock.sendall(json.dumps(msg).encode() + b"\n")
        while True:
            resp = self._read_msg()
            if "event" in resp:
                self.events.append(resp)
                continue
            if "error" in resp:
                raise QMPError(f"{execute}: {resp['error'].get('desc')}")
            return resp.get("return")

    def hmp(self, command: str) -> str:
        """Run a human-monitor command (savevm/loadvm/info ...)."""
        return self.cmd("human-monitor-command", **{"command-line": command})

    def wait_event(self, name: str, timeout: float = 60.0) -> dict:
        end = time.time() + timeout
        for i, ev in enumerate(self.events):
            if ev["event"] == name:
                return self.events.pop(i)
        old = self.sock.gettimeout()
        try:
            while time.time() < end:
                self.sock.settimeout(max(0.1, end - time.time()))
                try:
                    ev = self._read_msg()
                except socket.timeout:
                    break
                if ev.get("event") == name:
                    return ev
                self.events.append(ev)
        finally:
            self.sock.settimeout(old)
        raise QMPError(f"timeout waiting for event {name}")
