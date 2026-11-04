// Aerolith — optional enhancements. Every component works without this file; it adds what CSS
// alone cannot do:
//   - slider / compare: keeps --aer-fill in sync with the native range value
//   - drop zone: [data-aer-over] while files are dragged over an .aer-drop
//   - theme switch: input[data-aer-theme] toggles <html data-theme> and remembers the choice
//   - lens: the rim refraction of .aer-lens (Chromium only: backdrop-filter with an SVG filter)
//   - menus: popovers drop down from their button; [data-aer-menu] opens one at the pointer
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
  var lensId = 0, svgRoot = null;
  function chromium() { return !!(navigator.userAgentData && navigator.userAgentData.brands &&
    navigator.userAgentData.brands.some(function (b) { return /Chromium/.test(b.brand); })); }
  function lensMap(w, h, radius, bevel) {
    // height h(d) = smoothstep(d / bevel) of the distance d to the rounded-rect outline; the
    // gradient of h, scaled to 0..255 around 128, tells feDisplacementMap how far to bend light
    var c = document.createElement("canvas"); c.width = w; c.height = h;
    var g = c.getContext("2d"), img = g.createImageData(w, h), px = img.data;
    var hx = w / 2, hy = h / 2, r = Math.min(radius, hx, hy);
    function height(x, y) {
      var qx = Math.abs(x - hx) - (hx - r), qy = Math.abs(y - hy) - (hy - r);
      var out = Math.hypot(Math.max(qx, 0), Math.max(qy, 0)) + Math.min(Math.max(qx, qy), 0) - r;
      var t = Math.min(Math.max(-out / bevel, 0), 1);
      return t * t * (3 - 2 * t);
    }
    for (var y = 0; y < h; y++) for (var x = 0; x < w; x++) {
      var dx = height(x + 1, y + 0.5) - height(x, y + 0.5), dy = height(x + 0.5, y + 1) - height(x + 0.5, y);
      var k = bevel * 0.75, i = (y * w + x) * 4;
      px[i] = 128 + Math.max(-127, Math.min(127, dx * k * 127));
      px[i + 1] = 128 + Math.max(-127, Math.min(127, dy * k * 127));
      px[i + 2] = 128; px[i + 3] = 255;
    }
    g.putImageData(img, 0, 0);
    return c.toDataURL();
  }
  function lens(el) {
    if (!chromium()) return;
    var NS = "http://www.w3.org/2000/svg";
    if (!svgRoot) {
      svgRoot = document.createElementNS(NS, "svg");
      svgRoot.setAttribute("aria-hidden", "true");
      svgRoot.style.cssText = "position:absolute;width:0;height:0;overflow:hidden";
      document.body.appendChild(svgRoot);
    }
    var id = "aer-lens-" + (++lensId), filter = null;
    function build() {
      var w = Math.round(el.offsetWidth), h = Math.round(el.offsetHeight);
      if (!w || !h) return;
      if (filter) filter.remove();
      filter = document.createElementNS(NS, "filter");
      filter.id = id;
      ["x", "y"].forEach(function (a) { filter.setAttribute(a, "0"); });
      filter.setAttribute("width", w); filter.setAttribute("height", h);
      filter.setAttribute("filterUnits", "userSpaceOnUse");
      filter.setAttribute("color-interpolation-filters", "sRGB");
      var fi = document.createElementNS(NS, "feImage");
      fi.setAttribute("href", lensMap(w, h, 24, Math.min(28, w / 4, h / 4)));
      fi.setAttribute("x", 0); fi.setAttribute("y", 0); fi.setAttribute("width", w); fi.setAttribute("height", h);
      fi.setAttribute("preserveAspectRatio", "none"); fi.setAttribute("result", "map");
      var dm = document.createElementNS(NS, "feDisplacementMap");
      dm.setAttribute("in", "SourceGraphic"); dm.setAttribute("in2", "map"); dm.setAttribute("scale", "36");
      dm.setAttribute("xChannelSelector", "R"); dm.setAttribute("yChannelSelector", "G");
      filter.appendChild(fi); filter.appendChild(dm);
      svgRoot.appendChild(filter);
      el.style.backdropFilter = "url(#" + id + ")";
      el.setAttribute("data-aer-lens", "");
    }
    build();
    if (window.ResizeObserver) {
      var t;
      new ResizeObserver(function () { clearTimeout(t); t = setTimeout(build, 120); }).observe(el);
    }
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

  // ---------------------------------------------------------------- init
  function init(root) {
    root = root || document;
    preload(root);
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
