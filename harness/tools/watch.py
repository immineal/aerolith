#!/usr/bin/env python3
"""Watch the Bryce render pool live in a web browser, view-only, plus a history of finished renders.

    python3 harness/tools/watch.py [--port 6080] [--bind 127.0.0.1] [--displays :77,:78]

Live view: one tile per pool display (`bryce_harness.sheet.POOL`). The page re-fetches each tile's
screenshot every second or two. Frames are taken on request with a plain X11 GetImage (Pillow
ImageGrab) and cached for half a second, so nothing runs while no browser is open.

Render history: the newest finished renders from work/lib (render cache, `<name>_k/_w/_m.bmp` =
over black / over white / mask, grouped by name), work/sheets (older lookdev renders, NTFS archive)
and library/dist/sprites (exported PNG/WebP), newest first. Browsers cannot show BMP, so thumbnails
(JPEG/PNG) and full-size PNGs are made on request with Pillow and kept in a size-bounded in-memory
LRU. The directories are only ever read: one os.scandir every few seconds per directory, and only
while a browser keeps polling; a file is listed only after its size and mtime stopped changing and
its header says it is complete. Only files directly inside those directories are served.

Nothing is ever sent to the X servers, Wine or Bryce: there is no input path at all. The process
lowers its own priority (nice 10). Stdlib plus Pillow only. Stop it with `kill <PID>` (printed on start).
"""
import argparse
import hashlib
import io
import json
import os
import re
import struct
import sys
import threading
import time
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from PIL import Image, ImageGrab

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1]))
ROOT = HERE.parents[2]                      # repository root (harness/tools/watch.py -> ..)


def pool_displays():
    """[(display, label)] from the harness POOL; falls back to every X socket in /tmp/.X11-unix."""
    try:
        from bryce_harness.sheet import POOL
        return [(d, Path(p).name) for d, p in POOL]
    except Exception as e:
        print(f"watch: cannot import POOL ({e}); using all X sockets >= :70", file=sys.stderr)
        nums = sorted(int(m.group(1)) for f in os.listdir("/tmp/.X11-unix") if (m := re.fullmatch(r"X(\d+)", f)))
        return [(f":{n}", "") for n in nums if n >= 70]


class Frames:
    """Per-display JPEG cache (0.5 s) so several browsers or tabs cost one grab, not many."""
    TTL = 0.5

    def __init__(self):
        self.lock = threading.Lock()
        self.cache = {}                       # (display, width) -> (time, bytes)
        self.locks = {}

    def get(self, display, width):
        key = (display, width)
        with self.lock:
            lk = self.locks.setdefault(key, threading.Lock())
        with lk:
            hit = self.cache.get(key)
            if hit and time.time() - hit[0] < self.TTL:
                return hit[1]
            im = ImageGrab.grab(xdisplay=display).convert("RGB")
            if width and width < im.width:
                im = im.resize((width, round(im.height * width / im.width)))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=80)
            self.cache[key] = (time.time(), buf.getvalue())
            return self.cache[key][1]


# ---------------------------------------------------------------- render history

SRC = {                                   # name -> (file extensions, seconds between scans)
    "lib": {"exts": (".bmp", ".png"), "every": 3.0},
    "sheets": {"exts": (".bmp", ".png"), "every": 15.0},       # NTFS archive disk: scan rarely
    "sprites": {"exts": (".png", ".webp"), "every": 15.0},
}
MAX_GROUPS = 120                          # per source, newest first
OLD_ENOUGH = 30.0                         # a file this old needs no second look to count as finished
LABEL_ORDER = {"k": 0, "w": 1, "m": 2}
PNG_SIG = b"\x89PNG\r\n\x1a\n"
RE_PASS = re.compile(r"(.+)_([kwm])\.(?:bmp|png)")
RE_SCALE = re.compile(r"(.+?)(?:@(\d+x))?\.(?:png|webp)")


def parse_name(src, name):
    """(group name, label) for a file, or None. lib/sheets: `<name>_k|w|m.bmp`; sprites: `<name>@2x.png`."""
    if src == "sprites":
        m = RE_SCALE.fullmatch(name)
        return (m[1], m[2] or "1x") if m else None
    m = RE_PASS.fullmatch(name)
    return (m[1], m[2]) if m else (os.path.splitext(name)[0], "")


def probe(path, size):
    """(width, height) if the file looks complete, else None. Reads the header and, for PNG, the last 12 bytes."""
    try:
        with open(path, "rb") as f:
            head = f.read(64)
            if head[:2] == b"BM":
                if len(head) < 30:
                    return None
                fsz, off = struct.unpack_from("<II", head, 2)
                dib, = struct.unpack_from("<I", head, 14)
                if fsz and size < fsz:
                    return None
                if dib >= 40:
                    w, h, _pl, bpp, comp = struct.unpack_from("<iiHHI", head, 18)
                    if comp in (0, 3) and w > 0 and h != 0 and bpp:
                        if size < off + ((w * bpp + 31) // 32 * 4) * abs(h):
                            return None             # pixel data not all there yet
            elif head[:8] == PNG_SIG:
                f.seek(-12, os.SEEK_END)
                if f.read(12)[4:8] != b"IEND":
                    return None
            elif head[:4] == b"RIFF" and head[8:12] == b"WEBP":
                if struct.unpack_from("<I", head, 4)[0] + 8 > size:
                    return None
            else:
                return None
            f.seek(0)
            with Image.open(f) as im:
                return im.size
    except Exception:
        return None


class Snap:
    __slots__ = ("groups", "index", "t", "missing")

    def __init__(self, groups, index, missing=False):
        self.groups, self.index, self.t, self.missing = groups, index, time.monotonic(), missing


class Gallery:
    """Newest finished renders per source. One scanner thread per directory, awake only while a
    browser polls; handlers just read the latest snapshot."""
    IDLE_AFTER = 30.0                     # no request for this long -> scanners sleep, zero filesystem access

    def __init__(self, dirs):
        self.dirs = dirs                  # src -> directory path (str)
        self.snap = {}                    # src -> Snap
        self.prev = {}                    # src -> {name: (size, mtime_ns)} from the previous scan
        self.meta = {}                    # (src, name) -> (size, mtime_ns, (w, h) | None)
        self.last_req = 0.0
        self.wake = {s: threading.Event() for s in dirs}
        self.fresh = {s: threading.Event() for s in dirs}
        for s in dirs:
            threading.Thread(target=self.loop, args=(s,), daemon=True, name=f"scan-{s}").start()

    def touch(self, srcs, wait=0.0):
        """Called by every request: keeps the scanners awake; waits (bounded) if a snapshot is stale or missing."""
        now = time.monotonic()
        self.last_req = now
        pending = []
        for s in srcs:
            sn = self.snap.get(s)
            if sn is None or now - sn.t > 2 * SRC[s]["every"] + 1:
                self.fresh[s].clear()
                pending.append(s)
        for e in self.wake.values():
            e.set()
        end = now + wait
        for s in pending:
            self.fresh[s].wait(max(0.0, end - time.monotonic()))

    def loop(self, src):
        every = SRC[src]["every"]
        while True:
            if time.monotonic() - self.last_req > self.IDLE_AFTER:
                self.wake[src].clear()
                if time.monotonic() - self.last_req > self.IDLE_AFTER:   # re-check: a request may have raced the clear
                    self.wake[src].wait()
            try:
                self.scan(src)
            except Exception as e:
                print(f"watch: scan {src} failed: {e}", file=sys.stderr, flush=True)
            time.sleep(every)

    def check(self, src, name, size, mt):
        key = (src, name)
        m = self.meta.get(key)
        if m and m[0] == size and m[1] == mt:
            return m[2]
        dims = probe(os.path.join(self.dirs[src], name), size)
        if len(self.meta) > 6000:
            self.meta.clear()
        self.meta[key] = (size, mt, dims)
        return dims

    def mark_bad(self, src, name, size, mt):
        self.meta[(src, name)] = (size, mt, None)

    def scan(self, src):
        cfg, now = SRC[src], time.time()
        ents = []
        try:
            with os.scandir(self.dirs[src]) as it:
                for e in it:
                    if not e.name.lower().endswith(cfg["exts"]):
                        continue                      # name test first: no stat for .brc/.hash
                    try:
                        if not e.is_file(follow_symlinks=False):
                            continue
                        st = e.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    ents.append((e.name, st.st_size, st.st_mtime_ns))
        except OSError:
            self.snap[src] = Snap([], {}, missing=True)
            self.fresh[src].set()
            return
        prev = self.prev.get(src, {})
        self.prev[src] = {n: (sz, mt) for n, sz, mt in ents}
        ents.sort(key=lambda e: e[2], reverse=True)
        groups = {}
        for name, size, mt in ents:
            p = parse_name(src, name)
            if p is None or size == 0:
                continue
            gname, label = p
            if gname not in groups and len(groups) >= MAX_GROUPS:
                continue
            # finished = unchanged since the previous scan (or old); then structurally complete
            if prev.get(name) != (size, mt) and now - mt / 1e9 < OLD_ENOUGH:
                continue
            dims = self.check(src, name, size, mt)
            if dims is None:
                continue
            groups.setdefault(gname, []).append(
                {"file": name, "label": label, "v": mt // 1000, "w": dims[0], "h": dims[1], "size": size, "_mt": mt})
        out, index = [], {}
        for gname, items in groups.items():
            if src == "sprites":                      # scale variants: show @2x (or the first), link the rest
                items.sort(key=lambda i: int(i["label"][:-1] or 1))
                best = next((i for i in items if i["label"] == "2x"), items[0])
                items = [best] + [i for i in items if i is not best]
                shown, more = items[:1], items[1:]
            else:
                items.sort(key=lambda i: (LABEL_ORDER.get(i["label"], 9), i["file"]))
                shown, more = items, []
            for i in items:
                index[i["file"]] = (i["size"], i["_mt"])
            out.append({"src": src, "name": gname, "mt": max(i["_mt"] for i in items) / 1e9,
                        "items": [{k: v for k, v in i.items() if k != "_mt"} for i in shown],
                        "more": [{k: v for k, v in i.items() if k != "_mt"} for i in more]})
        out.sort(key=lambda g: -g["mt"])
        self.snap[src] = Snap(out, index)
        self.fresh[src].set()

    def listing(self, which, n):
        srcs = list(self.dirs) if which == "all" else [which]
        groups, missing = [], []
        for s in srcs:
            sn = self.snap.get(s)
            if sn is None or sn.missing:
                missing.append(s)
            if sn is not None:
                groups.extend(sn.groups)
        groups.sort(key=lambda g: -g["mt"])
        return groups[:n], missing

    def entry(self, src, name):
        sn = self.snap.get(src)
        return sn.index.get(name) if sn else None


class NotFound(Exception):
    pass


class Retry(Exception):
    pass


class Images:
    """Thumbnails and full-size views, made with Pillow on request, kept in a byte-bounded LRU
    keyed by (source, file, mtime, size, kind, width). One conversion at a time."""
    WIDTHS = (160, 240, 320, 480)
    MAX_ITEM = 16 << 20                   # bigger results are served but not cached
    MAX_RAW = 32 << 20                    # PNG/WebP passed through unchanged only up to this size

    def __init__(self, gallery, max_bytes=64 << 20, max_items=4000):
        self.g, self.max_bytes, self.max_items = gallery, max_bytes, max_items
        self.cache, self.bytes = OrderedDict(), 0
        self.lock, self.gen = threading.Lock(), threading.Lock()

    def _get(self, key):
        with self.lock:
            hit = self.cache.get(key)
            if hit:
                self.cache.move_to_end(key)
            return hit

    def _put(self, key, val):
        if len(val[1]) > self.MAX_ITEM:
            return
        with self.lock:
            if key in self.cache:
                self.bytes -= len(self.cache[key][1])
            self.cache[key] = val
            self.cache.move_to_end(key)
            self.bytes += len(val[1])
            while self.cache and (self.bytes > self.max_bytes or len(self.cache) > self.max_items):
                _, old = self.cache.popitem(last=False)
                self.bytes -= len(old[1])

    def get(self, kind, src, name, width=240):
        """(content type, bytes). Raises NotFound (not a listed file) or Retry (changed or unreadable right now)."""
        ent = self.g.entry(src, name)
        if ent is None:
            raise NotFound(name)
        size, mt = ent
        path = os.path.join(self.g.dirs[src], name)
        raw = kind == "full" and name.lower().endswith((".png", ".webp"))
        width = next((w for w in self.WIDTHS if w >= width), self.WIDTHS[-1]) if kind == "thumb" else 0
        key = (src, name, mt, size, kind, width)
        hit = self._get(key)
        if hit:
            return hit
        with self.gen:
            hit = self._get(key)
            if hit:
                return hit
            try:
                st = os.stat(path)
                if (st.st_size, st.st_mtime_ns) != (size, mt):
                    raise Retry("changed")
                if raw:
                    if size > self.MAX_RAW:
                        raise Retry("too large")
                    with open(path, "rb") as f:
                        val = ("image/webp" if name.lower().endswith(".webp") else "image/png", f.read())
                else:
                    val = self._convert(path, kind, width)
                st = os.stat(path)
                if (st.st_size, st.st_mtime_ns) != (size, mt):
                    raise Retry("changed while reading")
            except Retry:
                raise
            except Exception as e:            # truncated, corrupt, vanished: do not list it until it changes
                self.g.mark_bad(src, name, size, mt)
                raise Retry(str(e))
            self._put(key, val)
            return val

    @staticmethod
    def _convert(path, kind, width):
        with Image.open(path) as im:
            im.load()                         # raises on a truncated file
            alpha = im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info
            im = im.convert("RGBA" if alpha else "RGB") if im.mode not in ("RGB", "RGBA", "L") else im
            buf = io.BytesIO()
            if kind == "thumb":
                im.thumbnail((width, width))
                if alpha:
                    im.save(buf, "PNG", compress_level=3)
                    return "image/png", buf.getvalue()
                im.convert("RGB").save(buf, "JPEG", quality=82)
                return "image/jpeg", buf.getvalue()
            im.save(buf, "PNG", compress_level=1)        # full size: fast PNG, lossless
            return "image/png", buf.getvalue()


PAGE = r"""<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Bryce pool</title>
<style>
 body{margin:0;background:#15171a;color:#cfd3d8;font:13px system-ui,sans-serif}
 header{display:flex;gap:1em;align-items:center;flex-wrap:wrap;padding:8px 12px;background:#1d2024;position:sticky;top:0;z-index:2}
 header b{font-size:14px} select,button{background:#2a2e34;color:inherit;border:1px solid #444;border-radius:3px;padding:2px 6px}
 #grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(440px,1fr));gap:8px;padding:8px}
 .tile{background:#000;border:1px solid #333;cursor:zoom-in}.tile.big{grid-column:1/-1;cursor:zoom-out}
 .tile div{display:flex;justify-content:space-between;padding:3px 8px;background:#1d2024}
 .tile img{display:block;width:100%;height:auto;min-height:120px}.tile.down img{opacity:.25}
 .tile.down .st{color:#e0866a}.st{color:#7fbf8a}
 .bar{display:flex;gap:1em;align-items:center;flex-wrap:wrap;padding:8px 12px;background:#1d2024;border-top:1px solid #000}
 .bar b{font-size:14px}.bar .grow{flex:1}.bar #hs{color:#8d939b}
 #hgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:8px;padding:8px}
 .card{background:#1d2024;border:1px solid #333;min-width:0}
 .card .hd,.card .ft{display:flex;justify-content:space-between;gap:.6em;padding:3px 8px;align-items:baseline}
 .card .nm{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:600}
 .card .ft{color:#8d939b;font-size:12px}.card .ft a{color:#8fb4d9}
 .chip{font-size:11px;padding:0 5px;border-radius:8px;background:#2a2e34;color:#aab}
 .row{display:flex;gap:2px;background:#000}
 .row a{flex:1 1 0;min-width:0;position:relative;display:block;cursor:zoom-in}
 .row img{display:block;width:100%;aspect-ratio:1/1;object-fit:contain;background:#000}
 .row img.err{opacity:.2}
 .row i{position:absolute;left:3px;bottom:2px;font:10px system-ui;color:#fff;background:#0009;padding:0 3px;border-radius:2px}
 .sprites .row img,#lbi.alpha{background:repeating-conic-gradient(#3a3d42 0 25%,#2a2c30 0 50%) 0 0/16px 16px}
 #lb{position:fixed;inset:0;z-index:5;background:#0b0c0e;display:flex;flex-direction:column}
 #lb[hidden]{display:none}
 #lbbar{display:flex;gap:1em;align-items:center;padding:6px 12px;background:#1d2024}
 #lbbar span{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}#lbbar a{color:#8fb4d9}
 #lbw{flex:1;min-height:0;overflow:auto;display:flex;cursor:zoom-in}#lbw.z{cursor:zoom-out}
 #lbi{margin:auto;max-width:100%;max-height:100%}#lbw.z #lbi{max-width:none;max-height:none}
 #lbw.ld #lbi{visibility:hidden}
</style>
<header><b>Bryce pool</b><span>view only</span>
 <label>view <select id=view><option value=both>live + renders<option value=live>live displays<option value=renders>render history</select></label>
 <label>refresh <select id=iv><option value=1000>1 s<option value=2000 selected>2 s<option value=5000>5 s<option value=0>paused</select></label>
 <span>click a tile for full size</span></header>
<section id=live><div id=grid></div></section>
<section id=hist>
 <div class=bar><b>Recent renders</b>
  <label>source <select id=src><option value=all>all<option value=lib>work/lib<option value=sheets>work/sheets<option value=sprites>sprites</select></label>
  <label>show <select id=cnt><option>24<option selected>48<option>96</select></label>
  <span class=grow></span><span id=hs>...</span></div>
 <div id=hgrid></div>
</section>
<div id=lb hidden><div id=lbbar><span id=lbt></span><a id=lbo target=_blank rel=noopener>open in tab</a><button id=lbx>close (Esc)</button></div>
 <div id=lbw><img id=lbi alt=""></div></div>
<script>
const $=id=>document.getElementById(id);
const grid=$('grid'), iv=$('iv'), view=$('view');
const live=$('live'), hist=$('hist');
function applyView(){live.hidden=view.value==='renders'; hist.hidden=view.value==='live';
  try{localStorage.setItem('watchView',view.value)}catch(e){} histTick()}
try{view.value=localStorage.getItem('watchView')||'both'}catch(e){}

// ---- live displays
fetch('displays.json').then(r=>r.json()).then(list=>list.forEach(d=>{
  const t=document.createElement('div'); t.className='tile';
  t.innerHTML=`<div><span>${d.display} ${d.label}</span><span class=st>...</span></div><img alt="">`;
  const img=t.querySelector('img'), st=t.querySelector('.st');
  t.onclick=()=>{t.classList.toggle('big'); tick(true)};
  grid.append(t);
  let busy=false, timer;
  function tick(now){
    clearTimeout(timer);
    if(document.hidden||live.hidden){timer=setTimeout(tick,1000); return}   // nothing to show: do not grab frames
    if(busy) return; busy=true;
    const w=t.classList.contains('big')?0:Math.round(480*devicePixelRatio);
    const n=new Image();
    n.onload=()=>{img.src=n.src; t.classList.remove('down'); st.textContent=new Date().toLocaleTimeString(); done()};
    n.onerror=()=>{t.classList.add('down'); st.textContent='display not available'; done(5000)};
    n.src=`frame/${d.display.slice(1)}.jpg?w=${w}&t=${Date.now()}`;
  }
  function done(min){busy=false; const ms=+iv.value; timer=setTimeout(tick, Math.max(min||0, ms||1000));}
  iv.addEventListener('change',()=>{clearTimeout(timer); if(+iv.value) tick()});
  tick();
}));

// ---- render history
const LBL={k:'black',w:'white',m:'mask'}, srcSel=$('src'), cntSel=$('cnt'), hs=$('hs'), hgrid=$('hgrid');
const cards=new Map(); let lastOrder='', htimer, hbusy=false;
function h(tag,attrs,...kids){const e=document.createElement(tag);
  for(const k in attrs||{}) e.setAttribute(k,attrs[k]); e.append(...kids); return e}
const url=(kind,s,f,v,w)=>`${kind}/${s}/${encodeURIComponent(f)}?v=${v}`+(w?`&w=${w}`:'');
function when(t){const d=new Date(t*1000), same=d.toDateString()===new Date().toDateString();
  return same?d.toLocaleTimeString():d.toLocaleString([],{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'})}
function age(t){const s=Math.max(0,Math.round(Date.now()/1000-t));
  return s<90?`${s} s ago`:s<5400?`${Math.round(s/60)} min ago`:s<172800?`${Math.round(s/3600)} h ago`:`${Math.round(s/86400)} d ago`}
function thumb(img,u){let n=0;   // a file that was half-written answers 503: try again a few times
  img.onerror=()=>{if(n++<4) setTimeout(()=>{img.src=u+'&r='+n},5000*n); else img.classList.add('err')}; img.src=u}
function mkCard(g){
  const row=h('div',{class:'row'});
  for(const it of g.items){
    const full=url('full',g.src,it.file,it.v), a=h('a',{href:full,title:`${it.file}\n${it.w}×${it.h}`});
    const img=h('img',{alt:it.file,loading:'lazy'}); thumb(img,url('thumb',g.src,it.file,it.v,240));
    a.append(img); if(it.label) a.append(h('i',{},LBL[it.label]||it.label));
    a._d={src:g.src,full,title:`${g.name} · ${it.label?(LBL[it.label]||it.label)+' · ':''}${it.w}×${it.h} · ${when(g.mt)}`};
    a.onclick=ev=>{ev.preventDefault(); openLb(a)};
    row.append(a);
  }
  const ft=h('div',{class:'ft'},h('span',{class:'age','data-t':g.mt},age(g.mt)),h('span',{},when(g.mt)));
  if(g.more.length){const m=h('span',{},'also ');
    g.more.forEach(it=>m.append(h('a',{href:url('full',g.src,it.file,it.v),target:'_blank',rel:'noopener'},it.label+' ')));
    ft.append(m)}
  return h('div',{class:'card '+g.src},h('div',{class:'hd'},h('span',{class:'nm',title:g.name},g.name),h('span',{class:'chip'},g.src)),row,ft);
}
function sig(g){return g.items.concat(g.more).map(i=>i.file+':'+i.v).join('|')}
function renderHist(j){
  const keep=new Set(), els=[];
  for(const g of j.groups){
    const k=g.src+'/'+g.name, s=sig(g); keep.add(k);
    let c=cards.get(k); if(!c||c.sig!==s){c={el:mkCard(g),sig:s,k}; cards.set(k,c)}
    els.push(c);
  }
  for(const k of [...cards.keys()]) if(!keep.has(k)) cards.delete(k);
  const order=els.map(c=>c.k+'#'+c.sig).join('\n');
  if(order!==lastOrder){hgrid.replaceChildren(...els.map(c=>c.el)); lastOrder=order}
  hs.textContent=`${j.groups.length} renders, newest first`+(j.missing.length?` (not found: ${j.missing.join(', ')})`:'');
}
async function histTick(){
  clearTimeout(htimer);
  if(document.hidden||hist.hidden){htimer=setTimeout(histTick,1000); return}
  if(hbusy) return; hbusy=true;
  try{
    const r=await fetch(`renders.json?src=${srcSel.value}&n=${cntSel.value}`,{cache:'no-cache'});
    if(!r.ok) throw new Error('HTTP '+r.status);
    renderHist(await r.json());
  }catch(e){hs.textContent='history unavailable: '+e.message}
  hbusy=false; htimer=setTimeout(histTick,4000);
}
setInterval(()=>{if(!document.hidden&&!hist.hidden)
  document.querySelectorAll('#hgrid .age').forEach(e=>e.textContent=age(+e.dataset.t))},5000);
view.addEventListener('change',applyView); srcSel.addEventListener('change',histTick); cntSel.addEventListener('change',histTick);

// ---- click to enlarge (full size PNG; click the image for 1:1; arrows step through the thumbnails)
const lb=$('lb'), lbw=$('lbw'), lbi=$('lbi'); let cur=null;
function openLb(a){
  cur=a; const d=a._d; lbw.classList.remove('z'); lbw.classList.add('ld'); lbi.className=d.src==='sprites'?'alpha':'';
  lbi.onload=()=>lbw.classList.remove('ld'); lbi.onerror=()=>{lbw.classList.remove('ld'); $('lbt').textContent=d.title+' (not available)'};
  lbi.src=d.full; $('lbt').textContent=d.title; $('lbo').href=d.full; lb.hidden=false;
}
function step(n){const all=[...document.querySelectorAll('#hgrid .row a')], i=all.indexOf(cur);
  if(i>=0&&all[i+n]) openLb(all[i+n])}
lbw.onclick=ev=>{if(ev.target===lbi) lbw.classList.toggle('z'); else lb.hidden=true};
$('lbx').onclick=()=>{lb.hidden=true};
addEventListener('keydown',ev=>{if(lb.hidden) return;
  if(ev.key==='Escape') lb.hidden=true; else if(ev.key==='ArrowRight') step(1); else if(ev.key==='ArrowLeft') step(-1)});
document.addEventListener('visibilitychange',()=>{if(!document.hidden) histTick()});
applyView();
</script>"""


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        if isinstance(sys.exc_info()[1], (BrokenPipeError, ConnectionResetError)):
            return                                     # the browser navigated away mid-response
        super().handle_error(request, client_address)


def make_handler(displays, frames, gallery, images, port):
    allowed = {d: label for d, label in displays}
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, code, ctype, body, cache="no-store", extra=()):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", cache)
            self.send_header("X-Content-Type-Options", "nosniff")
            for k, v in extra:
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            # only answer to our own host name: blocks DNS-rebinding reads of the screenshots
            if self.headers.get("Host", "") not in hosts and not ARGS.any_host:
                return self.send(403, "text/plain", b"bad host")
            u = urlparse(self.path)
            if u.path in ("/", "/index.html"):
                return self.send(200, "text/html; charset=utf-8", PAGE.encode())
            if u.path == "/displays.json":
                body = json.dumps([{"display": d, "label": l} for d, l in displays]).encode()
                return self.send(200, "application/json", body)
            m = re.fullmatch(r"/frame/(\d+)\.jpg", u.path)
            if m and f":{m.group(1)}" in allowed:
                try:
                    w = int(parse_qs(u.query).get("w", ["0"])[0])
                    return self.send(200, "image/jpeg", frames.get(f":{m.group(1)}", max(0, min(w, 4000))))
                except Exception:                      # display gone or not started yet
                    return self.send(503, "text/plain", b"display not available")
            if u.path == "/renders.json":
                q = parse_qs(u.query)
                which = q.get("src", ["all"])[0]
                if which != "all" and which not in gallery.dirs:
                    return self.send(404, "text/plain", b"unknown source")
                try:
                    n = max(1, min(int(q.get("n", ["48"])[0]), MAX_GROUPS))
                except ValueError:
                    n = 48
                gallery.touch(list(gallery.dirs) if which == "all" else [which], wait=3.0)
                groups, missing = gallery.listing(which, n)
                body = json.dumps({"groups": groups, "missing": missing}, separators=(",", ":")).encode()
                etag = '"' + hashlib.md5(body).hexdigest() + '"'     # unchanged list -> 304, nothing re-sent
                if self.headers.get("If-None-Match") == etag:
                    return self.send(304, "application/json", b"", extra=[("ETag", etag)])
                return self.send(200, "application/json", body, cache="no-cache", extra=[("ETag", etag)])
            m = re.fullmatch(r"/(thumb|full)/([a-z]+)/([^/]+)", u.path)
            if m and m.group(2) in gallery.dirs:
                kind, src, name = m.group(1), m.group(2), unquote(m.group(3))
                if "/" in name or "\\" in name or "\0" in name or name.startswith("."):
                    return self.send(404, "text/plain", b"not found")
                gallery.touch([src])
                try:
                    w = int(parse_qs(u.query).get("w", ["240"])[0])
                except ValueError:
                    w = 240
                try:
                    ctype, body = images.get(kind, src, name, max(1, min(w, 4000)))
                except NotFound:
                    return self.send(404, "text/plain", b"not found")
                except Retry:                          # half-written or replaced right now: try again shortly
                    return self.send(503, "text/plain", b"not ready", extra=[("Retry-After", "5")])
                return self.send(200, ctype, body, cache="private, max-age=3600")
            self.send(404, "text/plain", b"not found")

    return H


def main():
    global ARGS
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--port", type=int, default=6080)
    ap.add_argument("--bind", default="127.0.0.1")
    ap.add_argument("--displays", help="comma separated, e.g. :77,:78 (default: harness POOL)")
    ap.add_argument("--any-host", action="store_true", help="skip the Host header check (needed behind a proxy)")
    ap.add_argument("--lib", default=str(ROOT / "work" / "lib"), help="render cache directory (read only)")
    ap.add_argument("--sheets", default=str(ROOT / "work" / "sheets"), help="older lookdev renders (read only)")
    ap.add_argument("--sprites", default=str(ROOT / "library" / "dist" / "sprites"), help="exported sprites (read only)")
    ARGS = ap.parse_args()
    try:
        os.nice(10)                                    # never compete with the renders for CPU
    except OSError:
        pass
    displays = ([(d, "") for d in ARGS.displays.split(",")] if ARGS.displays else pool_displays())
    gallery = Gallery({"lib": ARGS.lib, "sheets": ARGS.sheets, "sprites": ARGS.sprites})
    handler = make_handler(displays, Frames(), gallery, Images(gallery), ARGS.port)
    srv = Server((ARGS.bind, ARGS.port), handler)
    print(f"Watching {' '.join(d for d, _ in displays)} (view only)", flush=True)
    print(f"History: {', '.join(f'{k}={v}' for k, v in gallery.dirs.items())}", flush=True)
    print(f"URL: http://{ARGS.bind}:{ARGS.port}/   PID: {os.getpid()}   stop: kill {os.getpid()}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
