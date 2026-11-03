// Aerolith — optional enhancements. Every component works without this file; it adds what CSS
// alone cannot do:
//   - slider / compare: keeps --aer-fill in sync with the native range value
//   - drop zone: [data-aer-over] while files are dragged over an .aer-drop
//   - theme switch: input[data-aer-theme] toggles <html data-theme> and remembers the choice
//   - lens: the rim refraction of .aer-lens (Chromium only: backdrop-filter with an SVG filter)
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

  // ---------------------------------------------------------------- init
  function init(root) {
    root = root || document;
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
