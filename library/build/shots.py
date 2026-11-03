"""Screenshot the showcase page in Chromium / Firefox / WebKit, light + dark, at a given DPR."""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

LIB = Path(__file__).resolve().parents[1]
OUT = LIB / "work" / "shots"


def main(page_path="index.html", dpr=2, engines=("chromium", "firefox", "webkit"), width=1100, base=None):
    OUT.mkdir(parents=True, exist_ok=True)
    import functools, http.server, threading
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(LIB))
    handler.log_message = lambda *a: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = (base or f"http://127.0.0.1:{srv.server_address[1]}/") + page_path
    shots = []
    with sync_playwright() as p:
        for eng in engines:
            b = getattr(p, eng).launch()
            for scheme in ("light", "dark"):
                ctx = b.new_context(viewport={"width": width, "height": 900}, device_scale_factor=dpr,
                                    color_scheme=scheme)
                pg = ctx.new_page()
                errs = []
                pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
                pg.on("requestfailed", lambda r: errs.append("FAILED " + r.url))
                pg.goto(url)
                pg.wait_for_load_state("networkidle")
                f = OUT / f"{Path(page_path).stem}_{eng}_{scheme}@{dpr}x.png"
                pg.screenshot(path=str(f), full_page=True)
                shots.append(f)
                if errs:
                    print(eng, scheme, errs[:5])
                ctx.close()
            b.close()
    srv.shutdown()
    return shots


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    opt = dict(a[2:].split("=", 1) for a in sys.argv[1:] if a.startswith("--") and "=" in a)
    for f in main(*(args[:1] or ["index.html"]), dpr=int(opt.get("dpr", 2)),
                  engines=tuple(opt.get("engines", "chromium,firefox,webkit").split(",")),
                  width=int(opt.get("width", 1100)), base=opt.get("base")):
        print(f)
