// Aerolith — optional enhancements. Every component works without this file; it adds what CSS
// alone cannot do:
//   - slider / compare: keeps --aer-fill in sync with the native range value
//   - drop zone: [data-aer-over] while files are dragged over an .aer-drop
//   - theme switch: input[data-aer-theme] toggles <html data-theme> and remembers the choice
//   - lens: the rim refraction of .aer-lens (Chromium; Firefox too with data-aer-lens-backdrop);
//     data-aer-drag makes it movable
//   - menus: popovers drop down from their button; [data-aer-menu] opens one at the pointer
//   - segmented: the selected chip slides between items
//   - preload: sprites of closed dialogs and popovers load with the page
(function () {
  "use strict";
  var KEY = "aerolith-theme";

  function syncRange(input) {
    var min = +input.min || 0, max = input.max === "" ? 100 : +input.max, v = +input.value;
    var f = max > min ? (v - min) / (max - min) : 0;
    input.parentElement.style.setProperty("--aer-fill", String(f));
  }

  function once(el, key) {
    if (el.dataset[key]) return false;
    el.dataset[key] = "1";
    return true;
  }

  // ---------------------------------------------------------------- theme
  function stored() { try { return localStorage.getItem(KEY); } catch (e) { return null; } }
  function applyTheme(t) {
    var root = document.documentElement;
    if (t) root.setAttribute("data-theme", t); else root.removeAttribute("data-theme");
    document.querySelectorAll("input[data-aer-theme]").forEach(function (i) { i.checked = isDark(); });
  }
  function isDark() {
    var t = document.documentElement.getAttribute("data-theme");
    if (t) return t === "dark";
    return window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches;
  }

  // ---------------------------------------------------------------- lens: displacement map from the bevel profile
  // Two ways to bend what is behind the rim:
  //  - data-aer-lens-backdrop="<selector>": the lens carries a copy of that element, lined up with the
  //    original, and bends the copy with filter: url(). Chromium and Firefox.
  //  - otherwise, Chromium only: backdrop-filter: url(). Safari shows plain glass either way.
  // data-aer-drag makes the lens movable (pointer, touch, arrow keys) inside its parent.
  var lensId = 0, svgRoot = null, PAD = 2;
  // Lens geometry, same as the rendered sprite (catalog.py): superellipse corners (n = 4) of radius
  // LENS_R, a convex edge 1-(1-t)^4 over LENS_BEVEL px. Light comes straight down, refracts at the
  // curved top and the flat bottom (IOR 1.5), then travels LIFT px to the page under the glass.
  var LENS_R = 32, LENS_BEVEL = 30, GLASS = 20, BASE = 4, LIFT = 24, IOR = 1.5;
  var DISPERSION = [0.9, 1, 1.16];       // red, green, blue: blue bends most
  function chromium() { return !!(navigator.userAgentData && navigator.userAgentData.brands &&
    navigator.userAgentData.brands.some(function (b) { return /Chromium/.test(b.brand); })); }
  function bend(d, bevel) {               // px of sideways shift at depth d (px in from the outline)
    var t = Math.min(Math.max(d / bevel, 0), 1), u = 1 - t;
    var z = GLASS * (1 - u * u * u * u), slope = GLASS * 4 * u * u * u / bevel;
    var ti = Math.atan(slope), dl = ti - Math.asin(Math.sin(ti) / IOR);
    return (z + BASE) * Math.tan(dl) + LIFT * Math.tan(Math.asin(Math.min(1, IOR * Math.sin(dl))));
  }
  function lensMap(w, h, W, H, q) {
    // W x H map (lens centred) at q px per CSS px. R and G hold the inward shift as a fraction of the
    // largest one (128 = none); returns the map and that largest shift in px. One lookup table, then
    // a few multiplications per pixel: cheap enough to redo on every resize.
    var R = Math.min(LENS_R, w / 2, h / 2), bevel = Math.min(LENS_BEVEL, R);
    var STEP = 16, lut = new Float32Array(Math.ceil(bevel * STEP) + 2), max = bend(0, bevel);
    for (var k = 0; k < lut.length; k++) lut[k] = bend(k / STEP, bevel) / max;
    var cw = Math.round(W * q), ch = Math.round(H * q);
    var c = document.createElement("canvas"); c.width = cw; c.height = ch;
    var g = c.getContext("2d"), img = g.createImageData(cw, ch), px = img.data;
    var hx = w / 2, hy = h / 2, ex = hx - R, ey = hy - R;
    for (var Y = 0; Y < ch; Y++) {
      var y = (Y + 0.5) / q - H / 2, ay = Math.abs(y), qy = ay - ey;
      for (var X = 0; X < cw; X++) {
        var x = (X + 0.5) / q - W / 2, ax = Math.abs(x), qx = ax - ex, d, ux = 0, uy = 0;
        if (qx > 0 && qy > 0) {               // corner: superellipse, n = 4
          var x3 = qx * qx * qx, y3 = qy * qy * qy, L = Math.sqrt(Math.sqrt(x3 * qx + y3 * qy));
          d = R - L;
          var gl = Math.hypot(x3, y3); ux = -x3 / gl; uy = -y3 / gl;
        } else if (qx > qy) { d = R - qx; ux = -1; }
        else { d = R - qy; uy = -1; }
        if (x < 0) ux = -ux;
        if (y < 0) uy = -uy;
        var m = 0;
        if (d > 0 && d < bevel) { var f = d * STEP, k0 = f | 0; m = lut[k0] + (lut[k0 + 1] - lut[k0]) * (f - k0); }
        var i = (Y * cw + X) * 4;
        px[i] = 128 + Math.round(127 * m * ux); px[i + 1] = 128 + Math.round(127 * m * uy);
        px[i + 2] = 128; px[i + 3] = 255;
      }
    }
    g.putImageData(img, 0, 0);
    return { url: c.toDataURL(), max: max };
  }
  function lens(el) {
    if (el.hasAttribute("data-aer-drag")) drag(el);
    // WebKit (Safari, every iOS browser) misplaces SVG filters on HTML: plain glass there
    var sel = el.getAttribute("data-aer-lens-backdrop"), gecko = CSS.supports("-moz-appearance", "none");
    var src = sel && (chromium() || gecko) ? document.querySelector(sel) : null;
    if (!src && !chromium()) return;
    var NS = "http://www.w3.org/2000/svg";
    if (!svgRoot) {
      svgRoot = document.createElementNS(NS, "svg");
      svgRoot.setAttribute("aria-hidden", "true");
      svgRoot.style.cssText = "position:absolute;width:0;height:0;overflow:hidden";
      document.body.appendChild(svgRoot);
    }
    var id = "aer-lens-" + (++lensId), filter = null, view = null, copy = null, ox = 0, oy = 0;
    if (src) {
      // the copy: same element, same classes, no ids, no lens inside, lined up with the original
      view = document.createElement("div");
      view.className = "aer-lens-view"; view.setAttribute("aria-hidden", "true"); view.inert = true;
      copy = src.cloneNode(true);
      copy.removeAttribute("id");
      copy.querySelectorAll("[id]").forEach(function (n) { n.removeAttribute("id"); });
      copy.querySelectorAll(".aer-lens").forEach(function (n) { n.remove(); });
      view.appendChild(copy);
      el.insertBefore(view, el.firstChild);
      el.setAttribute("data-aer-lens-view", "");
    }
    function sync() {                       // line the copy up with the original
      if (!copy) return;
      var cs = getComputedStyle(src), a = src.getBoundingClientRect(), b = el.getBoundingClientRect();
      var st = copy.style;
      st.position = "absolute"; st.margin = "0"; st.boxSizing = "border-box"; st.transform = "none"; st.translate = "none";
      st.width = src.offsetWidth + "px"; st.height = src.offsetHeight + "px";
      st.left = (a.left - b.left + ox) + "px"; st.top = (a.top - b.top + oy) + "px";
      ["color", "fontFamily", "fontSize", "fontWeight", "lineHeight", "letterSpacing"].forEach(function (p) { st[p] = cs[p]; });
    }
    function build() {
      var w = Math.round(el.offsetWidth), h = Math.round(el.offsetHeight);
      if (!w || !h) return;
      if (filter) filter.remove();
      var pad = view ? PAD : 0, W = w + 2 * pad, H = h + 2 * pad;
      var map = lensMap(w, h, W, H, Math.min(2, window.devicePixelRatio || 1));
      if (view) {
        ox = pad; oy = pad;
        var vs = view.style;
        vs.left = -pad + "px"; vs.top = -pad + "px"; vs.width = W + "px"; vs.height = H + "px";
      }
      // map -> three displacements (red, green, blue bend by different amounts) -> recombined
      filter = document.createElementNS(NS, "filter");
      filter.id = id;
      var attrs = { x: 0, y: 0, width: W, height: H, filterUnits: "userSpaceOnUse", primitiveUnits: "userSpaceOnUse",
                    "color-interpolation-filters": "sRGB" };
      for (var a in attrs) filter.setAttribute(a, attrs[a]);
      function prim(tag, at) {
        var n = document.createElementNS(NS, tag);
        for (var a in at) n.setAttribute(a, at[a]);
        filter.appendChild(n);
      }
      prim("feImage", { href: map.url, x: 0, y: 0, width: W, height: H, preserveAspectRatio: "none", result: "map" });
      ["r", "g", "b"].forEach(function (ch, k) {
        prim("feDisplacementMap", { in: "SourceGraphic", in2: "map", scale: (2 * map.max * DISPERSION[k]).toFixed(2),
                                    xChannelSelector: "R", yChannelSelector: "G", result: "d" + ch });
        var m = ["0 0 0 0 0", "0 0 0 0 0", "0 0 0 0 0"]; m[k] = ["1 0 0 0 0", "0 1 0 0 0", "0 0 1 0 0"][k];
        prim("feColorMatrix", { in: "d" + ch, type: "matrix", values: m.join(" ") + " 0 0 0 1 0", result: ch });
      });
      prim("feComposite", { in: "r", in2: "g", operator: "arithmetic", k2: 1, k3: 1, result: "rg" });
      prim("feComposite", { in: "rg", in2: "b", operator: "arithmetic", k2: 1, k3: 1 });
      svgRoot.appendChild(filter);
      if (view) { sync(); view.style.filter = "url(#" + id + ")"; }
      else el.style.backdropFilter = "url(#" + id + ")";
      el.setAttribute("data-aer-lens", "");
    }
    el._aerLensSync = sync;
    build();
    if (window.ResizeObserver) {
      var t;
      new ResizeObserver(function () { clearTimeout(t); t = setTimeout(build, 120); }).observe(el);
      if (src) new ResizeObserver(sync).observe(src);
    }
    addEventListener("resize", sync);
  }
  function drag(el) {
    var x = 0, y = 0, start = null;
    if (!el.hasAttribute("tabindex")) el.tabIndex = 0;
    function moveTo(nx, ny) {
      var box = el.parentElement.getBoundingClientRect(), r = el.getBoundingClientRect();
      var bx = r.left - x, by = r.top - y;          // where it sits without the shift
      x = Math.round(clamp(nx, box.left - bx, box.right - r.width - bx));
      y = Math.round(clamp(ny, box.top - by, box.bottom - r.height - by));
      el.style.translate = x + "px " + y + "px";
      if (el._aerLensSync) el._aerLensSync();
    }
    el.addEventListener("pointerdown", function (e) {
      if (e.button !== 0 || e.target.closest("a, button, input, select, textarea")) return;
      start = { px: e.clientX, py: e.clientY, x: x, y: y };
      el.setPointerCapture(e.pointerId); el.setAttribute("data-aer-dragging", "");
      e.preventDefault();
    });
    el.addEventListener("pointermove", function (e) {
      if (start) moveTo(start.x + e.clientX - start.px, start.y + e.clientY - start.py);
    });
    ["pointerup", "pointercancel", "lostpointercapture"].forEach(function (t) {
      el.addEventListener(t, function () { start = null; el.removeAttribute("data-aer-dragging"); });
    });
    el.addEventListener("keydown", function (e) {
      var d = e.shiftKey ? 40 : 10, k = { ArrowLeft: [-d, 0], ArrowRight: [d, 0], ArrowUp: [0, -d], ArrowDown: [0, d] }[e.key];
      if (!k) return;
      e.preventDefault(); moveTo(x + k[0], y + k[1]);
    });
    if (window.ResizeObserver) new ResizeObserver(function () { moveTo(x, y); }).observe(el.parentElement);
  }

  // ---------------------------------------------------------------- menus: placed like a context menu
  // A [popover].aer-popover opened by a popovertarget button drops down from that button (or opens
  // above it when there is no room); [data-aer-menu="id"] on any element opens that popover at the
  // pointer on right-click or long-press. Either way it stays 8 px inside the window.
  var invoker = null;
  function clamp(v, lo, hi) { return Math.max(lo, Math.min(v, hi)); }
  function place(pop, at) {
    var M = 8, vw = document.documentElement.clientWidth, vh = window.innerHeight;
    var w = pop.offsetWidth, h = pop.offsetHeight, left, top;
    if (at.nodeType) {
      var r = at.getBoundingClientRect();
      left = r.left; top = r.bottom + 6;
      if (top + h > vh - M && r.top - 6 - h >= M) top = r.top - 6 - h;
      if (left + w > vw - M) left = r.right - w;
    } else {
      left = at.x; top = at.y;
      if (left + w > vw - M) left = at.x - w;
      if (top + h > vh - M) top = at.y - h;
    }
    pop.style.left = clamp(left, M, vw - M - w) + "px";
    pop.style.top = clamp(top, M, vh - M - h) + "px";
  }
  function openAt(pop, at) {
    pop.style.position = "fixed"; pop.style.inset = "auto"; pop.style.margin = "0";
    pop._aerAt = at;
    if (!pop.matches(":popover-open")) pop.showPopover(); else place(pop, at);
  }
  function bindPopover(pop) {
    function close() { if (pop.matches(":popover-open")) pop.hidePopover(); }
    // before it shows: anchor it, so it never flashes at the window's corner
    pop.addEventListener("beforetoggle", function (e) {
      if (e.newState !== "open") return;
      if (!pop._aerAt && invoker && invoker.getAttribute("popovertarget") === pop.id) pop._aerAt = invoker;
      if (!pop._aerAt) return;
      pop.style.position = "fixed"; pop.style.inset = "auto"; pop.style.margin = "0";
      place(pop, pop._aerAt);                  // size unknown yet: a first guess
    });
    pop.addEventListener("toggle", function (e) {
      if (e.newState === "open") {
        if (pop._aerAt) place(pop, pop._aerAt);   // measured: flip or clamp if needed
        addEventListener("resize", close);
        addEventListener("scroll", close, { capture: true, passive: true });
      } else {
        pop._aerAt = null;
        removeEventListener("resize", close);
        removeEventListener("scroll", close, { capture: true });
      }
    });
    // picking an item closes the menu
    pop.addEventListener("click", function (e) {
      if (e.target.closest(".aer-menu > a, .aer-menu > button") && pop.matches(":popover-open")) pop.hidePopover();
    });
  }
  function bindContext(el) {
    var pop = document.getElementById(el.getAttribute("data-aer-menu"));
    if (!pop || !pop.showPopover) return;
    var timer = 0, start = null, pending = null, down = false;
    el.addEventListener("contextmenu", function (e) {
      e.preventDefault();
      var at = { x: e.clientX, y: e.clientY };
      // Linux and macOS fire contextmenu on mouse-down, phones while the finger is down. Opened
      // then, the release would light-dismiss the menu, so it opens when the button or finger lifts.
      if (down) pending = at; else openAt(pop, at);
    });
    el.addEventListener("pointerdown", function (e) {
      if (e.pointerType === "mouse" && e.button !== 2) return;
      down = true;
      if (e.pointerType !== "touch") return;
      start = { x: e.clientX, y: e.clientY };
      clearTimeout(timer);
      timer = setTimeout(function () { pending = start; }, 500);    // iOS sends no contextmenu
    });
    el.addEventListener("pointermove", function (e) {
      if (start && Math.hypot(e.clientX - start.x, e.clientY - start.y) > 10) { clearTimeout(timer); start = null; }
    });
    function release() {
      if (!down) return;
      down = false; clearTimeout(timer); start = null;
      if (pending) { var at = pending; pending = null; setTimeout(function () { openAt(pop, at); }, 0); }
    }
    addEventListener("pointerup", release, true);         // on the window: the pointer may have left el
    addEventListener("pointercancel", release, true);
  }
  document.addEventListener("click", function (e) {
    var b = e.target.closest && e.target.closest("[popovertarget]");
    if (b) invoker = b;
  }, true);

  // ---------------------------------------------------------------- sprites of things that start hidden
  // A closed dialog or popover is not rendered, so its sprites would load only when it first opens
  // (one empty frame). One off-screen probe fetches them with the page (.aer-preload in the CSS).
  function preload(root) {
    if (document.querySelector(".aer-preload") || !root.querySelector(".aer-dialog, .aer-popover, .aer-toaster")) return;
    var i = document.createElement("i");
    i.className = "aer-preload"; i.setAttribute("aria-hidden", "true");
    document.body.appendChild(i);
  }

  // ---------------------------------------------------------------- segmented: one pill that slides
  // Without this every selected item draws its own chip. With it, one .aer-seg-pill under the items
  // carries the chip and CSS moves it. It follows radio changes, aria-current / -selected / -pressed
  // (MutationObserver), form resets and size changes; a size change snaps instead of sliding.
  function selected(c) {
    var i = c.querySelector("input");
    if (i) return i.checked;
    var a = c.getAttribute("aria-current");
    return (a !== null && a !== "false") || c.getAttribute("aria-selected") === "true" ||
      c.getAttribute("aria-pressed") === "true";
  }
  function slide(seg) {
    var pill = document.createElement("span"), shown = false;
    pill.className = "aer-seg-pill"; pill.setAttribute("aria-hidden", "true");
    seg.appendChild(pill);                      // last, so a fieldset's legend stays first
    seg.setAttribute("data-aer-slide", "");
    function place(snap) {
      var c = null;
      for (var k = 0; k < seg.children.length; k++) {
        var e = seg.children[k];
        if (e !== pill && selected(e)) { c = e; break; }
      }
      if (!c || !c.offsetWidth) { pill.style.opacity = "0"; shown = false; return; }
      if (snap || !shown) seg.removeAttribute("data-aer-ready");
      pill.style.opacity = "";
      pill.style.transform = "translate(" + c.offsetLeft + "px, " + c.offsetTop + "px)";
      pill.style.width = c.offsetWidth + "px"; pill.style.height = c.offsetHeight + "px";
      if (snap || !shown) { void pill.offsetWidth; seg.setAttribute("data-aer-ready", ""); }   // reflow, then animate again
      shown = true;
    }
    seg._aerPlace = place;
    seg.addEventListener("change", function () { place(); });
    if (window.MutationObserver)
      new MutationObserver(function () { place(); }).observe(seg, { subtree: true, attributes: true,
        attributeFilter: ["aria-current", "aria-selected", "aria-pressed"] });
    var form = seg.closest && seg.closest("form");
    if (form) form.addEventListener("reset", function () { setTimeout(place, 0); });
    if (window.ResizeObserver) {
      var ro = new ResizeObserver(function () { place(true); });
      ro.observe(seg);
      for (var k = 0; k < seg.children.length; k++) if (seg.children[k] !== pill) ro.observe(seg.children[k]);
    }
    place(true);
  }

  // ---------------------------------------------------------------- init
  // Calling init again re-places the segmented pills, e.g. after setting input.checked from script.
  function init(root) {
    root = root || document;
    preload(root);
    root.querySelectorAll(".aer-segmented").forEach(function (s) {
      if (once(s, "aerSlide")) slide(s); else if (s._aerPlace) s._aerPlace();
    });
    root.querySelectorAll(".aer-popover[popover]").forEach(function (p) { if (once(p, "aerBound")) bindPopover(p); });
    root.querySelectorAll("[data-aer-menu]").forEach(function (el) { if (once(el, "aerCtxBound")) bindContext(el); });
    root.querySelectorAll(".aer-slider > input[type=range], .aer-compare > input[type=range]").forEach(function (input) {
      if (!once(input, "aerBound")) return;
      input.parentElement.setAttribute("data-aer-ready", "");
      input.addEventListener("input", function () { syncRange(input); });
      syncRange(input);
    });
    root.querySelectorAll(".aer-drop").forEach(function (zone) {
      if (!once(zone, "aerBound")) return;
      var depth = 0;
      zone.addEventListener("dragenter", function () { depth++; zone.setAttribute("data-aer-over", ""); });
      zone.addEventListener("dragleave", function () { if (--depth <= 0) { depth = 0; zone.removeAttribute("data-aer-over"); } });
      zone.addEventListener("drop", function () { depth = 0; zone.removeAttribute("data-aer-over"); });
    });
    root.querySelectorAll("input[data-aer-theme]").forEach(function (input) {
      if (!once(input, "aerBound")) return;
      input.checked = isDark();
      input.addEventListener("change", function () {
        var t = input.checked ? "dark" : "light";
        try { localStorage.setItem(KEY, t); } catch (e) {}
        applyTheme(t);
      });
    });
    root.querySelectorAll(".aer-lens").forEach(function (el) { if (once(el, "aerBound")) lens(el); });
  }

  if (stored()) applyTheme(stored());
  window.Aerolith = { init: init, setTheme: function (t) { try { localStorage.setItem(KEY, t); } catch (e) {} applyTheme(t); } };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", function () { init(); });
  else init();
})();
