/* AIO data app runtime for Tableau Cloud data apps.
 *
 * Every app AIO builds loads this file, then src/queries.js (window.AIO_QUERIES: the VizQL Data
 * Service queries AIO checked against the datasource before publishing), then src/app.js, which calls
 * AIO.start({...}). The app only describes its page; this file talks to the Extensions API, applies
 * the filter bar to every query, and draws the charts (SVG, no libraries, so it runs in the sandbox).
 */
(function () {
  'use strict';

  var SVGNS = 'http://www.w3.org/2000/svg';
  var PALETTE = ['#1f6feb', '#e8710a', '#1a7f37', '#8250df', '#cf222e', '#0a7ea4', '#bf8700', '#57606a'];

  function el(tag, attrs, text) {
    var n = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) { n.setAttribute(k, attrs[k]); });
    if (text != null) n.textContent = text;
    return n;
  }

  function svg(tag, attrs, text) {
    var n = document.createElementNS(SVGNS, tag);
    Object.keys(attrs || {}).forEach(function (k) { n.setAttribute(k, attrs[k]); });
    if (text != null) n.textContent = text;
    return n;
  }

  function num(v) {
    var n = typeof v === 'number' ? v : parseFloat(v);
    return isFinite(n) ? n : null;
  }

  function isNumeric(v) {
    return typeof v === 'number' ? isFinite(v) : (typeof v === 'string' && /^\s*-?\d+(\.\d+)?\s*$/.test(v));
  }

  // Format a value: percent (0.62 -> 62.0%), number, currency, or a unit suffix ("min")
  function fmt(v, kind) {
    var n = num(v);
    if (n === null) return '–';
    if (kind === 'percent') return (n * 100).toFixed(1) + '%';
    if (kind === 'currency') return '$' + abbreviate(n);
    if (kind && kind !== 'number') return n.toFixed(n < 100 ? 1 : 0) + ' ' + kind;
    return Math.abs(n) >= 1000 ? abbreviate(n) : n.toFixed(Math.abs(n) < 10 ? 2 : (Math.abs(n) >= 100 ? 0 : 1));
  }

  function abbreviate(n) {
    var a = Math.abs(n);
    if (a >= 1e9) return (n / 1e9).toFixed(1) + 'B';
    if (a >= 1e6) return (n / 1e6).toFixed(1) + 'M';
    if (a >= 1e3) return (n / 1e3).toFixed(1) + 'K';
    return n.toFixed(a < 10 ? 2 : 0);
  }

  // Month label from a date value ("2026-11-01T00:00:00" -> "Nov 26")
  function label(v) {
    var s = String(v);
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s);
    if (!m) return s;
    var names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    return names[parseInt(m[2], 10) - 1] + ' ' + m[1].slice(2);
  }

  function sortBy(rows, key, dir) {
    return rows.slice().sort(function (a, b) {
      var x = a[key], y = b[key];
      // Numbers compare as numbers; anything else (dates like "2026-11-01T00:00:00") as text
      var c = (isNumeric(x) && isNumeric(y)) ? Number(x) - Number(y) : String(x).localeCompare(String(y));
      return dir === 'desc' ? -c : c;
    });
  }

  function App(root, opts, ds) {
    this.root = root;
    this.opts = opts;
    this.ds = ds;
    this.filters = {};          // field caption -> selected value ('' = all)
    this.cache = {};
  }

  // Run a registered query with the filter bar applied; resolves to its rows
  App.prototype.query = function (id) {
    var q = (window.AIO_QUERIES || {})[id];
    if (!q) return Promise.reject(new Error('Unknown query "' + id + '"'));
    var self = this;
    var filters = (q.filters || []).slice();
    Object.keys(this.filters).forEach(function (field) {
      if (self.filters[field]) {
        filters.push({ field: { fieldCaption: field }, filterType: 'SET', values: [self.filters[field]] });
      }
    });
    var body = { fields: q.fields };
    if (filters.length) body.filters = filters;
    var key = JSON.stringify(body);
    if (!this.cache[key]) {
      this.cache[key] = this.ds.queryAsync(body).then(function (res) {
        return res && Array.isArray(res.data) ? res.data : [];
      });
    }
    return this.cache[key];
  };

  // A titled section: the headline states the finding, the text adds one line. Returns its body element.
  App.prototype.section = function (headline, text, opts) {
    var s = el('section', { 'class': 'aio-section' + (opts && opts.half ? ' aio-half' : '') });
    s.appendChild(el('h2', {}, headline));
    if (text) s.appendChild(el('p', { 'class': 'aio-text' }, text));
    var body = el('div', { 'class': 'aio-body' });
    s.appendChild(body);
    (this.grid || this.root).appendChild(s);
    return body;
  };

  // Put the next sections side by side
  App.prototype.row = function (fn) {
    var row = el('div', { 'class': 'aio-row' });
    this.root.appendChild(row);
    var prev = this.grid;
    this.grid = row;
    fn();
    this.grid = prev;
  };

  // KPI tiles: [{label, query, field, format, trend: {query, x, y}, goodDirection: 'up'|'down'}]
  App.prototype.kpis = function (tiles) {
    var self = this;
    var strip = el('div', { 'class': 'aio-kpis' });
    this.root.appendChild(strip);
    tiles.forEach(function (t) {
      var tile = el('div', { 'class': 'aio-kpi' });
      tile.appendChild(el('div', { 'class': 'aio-kpi-label' }, t.label));
      var value = el('div', { 'class': 'aio-kpi-value' }, '…');
      tile.appendChild(value);
      var spark = el('div', { 'class': 'aio-kpi-spark' });
      tile.appendChild(spark);
      strip.appendChild(tile);
      self.query(t.query).then(function (rows) {
        value.textContent = rows.length ? fmt(rows[0][t.field], t.format) : '–';
      }, function (e) { value.textContent = '–'; tile.title = e.message; });
      if (t.trend) {
        self.query(t.trend.query).then(function (rows) {
          sparkline(spark, sortBy(rows, t.trend.x), t.trend.y, t.goodDirection || 'up');
        }, function () {});
      }
    });
  };

  App.prototype.bar = function (body, queryId, o) { this._draw(body, queryId, function (rows) { bars(body, rows, o); }); };
  App.prototype.line = function (body, queryId, o) { this._draw(body, queryId, function (rows) { lines(body, rows, o); }); };
  App.prototype.dumbbell = function (body, queryId, o) { this._draw(body, queryId, function (rows) { dumbbell(body, rows, o); }); };
  // Site map: the main query's rows (e.g. parking spots) plus optional extra layers, each its own query
  App.prototype.map = function (body, queryId, o) {
    var self = this;
    this._draw(body, queryId, function (rows) {
      var layers = ['markers', 'routes', 'trucks'];
      Promise.all(layers.map(function (k) {
        return o[k] ? self.query(o[k].query).then(null, function () { return []; }) : Promise.resolve([]);
      })).then(function (res) { siteMap(body, rows, o, res[0], res[1], res[2]); });
    });
  };
  App.prototype.table = function (body, queryId, o) { this._draw(body, queryId, function (rows) { table(body, rows, o); }); };

  // Draw from a query result once it arrives; any error or empty result shows in the section
  App.prototype._draw = function (body, queryId, draw) {
    body.textContent = 'Loading…';
    this.query(queryId).then(function (rows) {
      body.textContent = '';
      if (!rows.length) { body.appendChild(el('p', { 'class': 'aio-note' }, 'No data for these filters.')); return; }
      draw(rows);
    }, function (e) {
      body.textContent = '';
      body.appendChild(el('p', { 'class': 'aio-error' }, 'Query failed: ' + (e.message || e)));
    });
  };

  // Horizontal bars: {x: dimension, y: measure, format, sort: 'desc'|'asc', highlight: value}
  function bars(body, rows, o) {
    rows = sortBy(rows, o.y, o.sort || 'desc');
    var vals = rows.map(function (r) { return num(r[o.y]) || 0; });
    var max = Math.max.apply(null, vals.concat([0])), min = Math.min.apply(null, vals.concat([0]));
    rows.forEach(function (r, i) {
      var row = el('div', { 'class': 'aio-bar-row' });
      row.appendChild(el('span', { 'class': 'aio-bar-label', title: r[o.x] }, r[o.x]));
      var track = el('div', { 'class': 'aio-bar-track' });
      var fill = el('div', { 'class': 'aio-bar-fill' + (o.highlight && r[o.x] === o.highlight ? ' aio-hot' : '') });
      fill.style.width = (100 * (vals[i] - Math.min(0, min)) / Math.max(1e-9, max - Math.min(0, min))) + '%';
      track.appendChild(fill);
      row.appendChild(track);
      row.appendChild(el('span', { 'class': 'aio-bar-val' }, fmt(vals[i], o.format)));
      body.appendChild(row);
    });
  }

  // Line chart over time: {x: date field, y: measure, series: optional dimension, format}
  function lines(body, rows, o) {
    var W = Math.max(480, body.clientWidth || 720), H = o.height || 240, L = 52, R = 160, T = 12, B = 28;
    var xs = [];
    rows.forEach(function (r) { if (xs.indexOf(String(r[o.x])) < 0) xs.push(String(r[o.x])); });
    xs.sort();
    var groups = {};
    rows.forEach(function (r) {
      var g = o.series ? String(r[o.series]) : (o.label || o.y);
      (groups[g] = groups[g] || {})[String(r[o.x])] = num(r[o.y]);
    });
    var all = rows.map(function (r) { return num(r[o.y]); }).filter(function (v) { return v !== null; });
    var lo = Math.min.apply(null, all), hi = Math.max.apply(null, all);
    var pad = (hi - lo) * 0.08 || Math.abs(hi) * 0.05 || 1;
    lo -= pad; hi += pad;
    var X = function (i) { return L + i * (W - L - R) / Math.max(1, xs.length - 1); };
    var Y = function (v) { return T + (hi - v) / (hi - lo) * (H - T - B); };
    var s = svg('svg', { viewBox: '0 0 ' + W + ' ' + H, width: '100%', role: 'img', 'aria-label': o.y + ' over time' });
    for (var k = 0; k <= 3; k++) {
      var v = lo + (hi - lo) * k / 3;
      s.appendChild(svg('line', { x1: L, x2: W - R, y1: Y(v), y2: Y(v), 'class': 'aio-grid' }));
      s.appendChild(svg('text', { x: L - 6, y: Y(v) + 4, 'text-anchor': 'end', 'class': 'aio-axis' }, fmt(v, o.format)));
    }
    var step = Math.max(1, Math.ceil(xs.length / 8));
    xs.forEach(function (x, i) {
      if (i % step === 0 || i === xs.length - 1) {
        s.appendChild(svg('text', { x: X(i), y: H - 8, 'text-anchor': 'middle', 'class': 'aio-axis' }, label(x)));
      }
    });
    var ends = [];
    Object.keys(groups).sort().forEach(function (g, gi) {
      var color = o.highlight ? (g === o.highlight ? PALETTE[4] : '#9aa4ae') : PALETTE[gi % PALETTE.length];
      var pts = [], last = null;
      xs.forEach(function (x, i) {
        var v = groups[g][x];
        if (v !== null && v !== undefined) { pts.push(X(i).toFixed(1) + ',' + Y(v).toFixed(1)); last = [X(i), Y(v), v]; }
      });
      s.appendChild(svg('polyline', { points: pts.join(' '), fill: 'none', stroke: color, 'stroke-width': g === o.highlight ? 3 : 2 }));
      if (last) {
        s.appendChild(svg('circle', { cx: last[0], cy: last[1], r: 3, fill: color }));
        ends.push({ x: last[0], y: last[1], text: g + ' ' + fmt(last[2], o.format), color: color });
      }
    });
    // End labels: spread apart so lines that finish close together stay readable
    ends.sort(function (a, b) { return a.y - b.y; });
    for (var e = 1; e < ends.length; e++) ends[e].y = Math.max(ends[e].y, ends[e - 1].y + 13);
    var over = ends.length ? ends[ends.length - 1].y - (H - B) : 0;
    ends.forEach(function (lab) {
      s.appendChild(svg('text', { x: lab.x + 6, y: lab.y - Math.max(0, over) + 4, 'class': 'aio-series', fill: lab.color }, lab.text));
    });
    body.appendChild(s);
  }

  // Before/after per category: {x: dimension, from: measure, to: measure, format, fromLabel, toLabel}
  function dumbbell(body, rows, o) {
    rows = rows.slice().sort(function (a, b) { return (num(a[o.to]) - num(a[o.from])) - (num(b[o.to]) - num(b[o.from])); });
    var all = [];
    rows.forEach(function (r) { all.push(num(r[o.from]), num(r[o.to])); });
    all = all.filter(function (v) { return v !== null; });
    var lo = Math.min.apply(null, all), hi = Math.max.apply(null, all), pad = (hi - lo) * 0.1 || 1;
    lo -= pad; hi += pad;
    var W = Math.min(720, Math.max(360, body.clientWidth || 400)), rowH = 30, L = 150, R = 70, H = rows.length * rowH + 30;
    var X = function (v) { return L + 44 + (v - lo) / (hi - lo) * (W - L - R - 44); };
    // Drawn at the card's own width (capped), so text stays at its CSS size on a full-width card
    var s = svg('svg', { viewBox: '0 0 ' + W + ' ' + H, width: W, style: 'max-width:100%', role: 'img' });
    rows.forEach(function (r, i) {
      var y = 18 + i * rowH, a = num(r[o.from]), b = num(r[o.to]);
      s.appendChild(svg('text', { x: L - 8, y: y + 4, 'text-anchor': 'end', 'class': 'aio-axis' }, r[o.x]));
      s.appendChild(svg('line', { x1: X(a), x2: X(b), y1: y, y2: y, stroke: '#c9d1d9', 'stroke-width': 3 }));
      s.appendChild(svg('circle', { cx: X(a), cy: y, r: 5, fill: '#9aa4ae' }));
      s.appendChild(svg('circle', { cx: X(b), cy: y, r: 6, fill: PALETTE[0] }));
      // The current value sits beside its own dot, on the side away from the earlier one
      var right = b >= a;
      s.appendChild(svg('text', { x: X(b) + (right ? 10 : -10), y: y + 4, 'text-anchor': right ? 'start' : 'end',
                                  'class': 'aio-axis' }, fmt(b, o.format)));
    });
    var ly = H - 6;
    s.appendChild(svg('circle', { cx: L, cy: ly - 4, r: 4, fill: '#9aa4ae' }));
    s.appendChild(svg('text', { x: L + 8, y: ly, 'class': 'aio-axis' }, o.fromLabel || 'Before'));
    s.appendChild(svg('circle', { cx: L + 120, cy: ly - 4, r: 4, fill: PALETTE[0] }));
    s.appendChild(svg('text', { x: L + 128, y: ly, 'class': 'aio-axis' }, o.toLabel || 'Now'));
    body.appendChild(s);
  }

  // Site map on a 0-100 grid.
  //   rows (the main query): the places, e.g. parking spots: {label, x, y, size?, color?, zone?}
  //     circles sized by `size`, shaded by `color` (green = better, red = worse; goodDirection 'down' = lower is better);
  //     `zone` draws a labelled lot outline around the places that share it
  //   markers: {query, label, x, y} fixed equipment (e.g. loaders), drawn as labelled squares
  //   routes:  {query, fromX, fromY, toX, toY, weight?, color?} lines between two places (e.g. spot -> loader),
  //            width by `weight` (e.g. cycles), shaded by `color` (e.g. queue wait) like the places
  //   trucks:  {query, id, x, y, date?} moving things: one dot each at their latest position (latest `date` wins)
  function siteMap(body, rows, o, marks, routes, trucks) {
    var W = Math.min(980, Math.max(460, body.clientWidth || 700)), H = Math.round(W * 0.64), P = 28;
    var X = function (v) { return P + num(v) / 100 * (W - 2 * P); };
    var Y = function (v) { return H - P - num(v) / 100 * (H - 2 * P); };
    var bad = (o.goodDirection || 'down') === 'down';
    function shade(v, lo, hi) {
      var t = (num(v) - lo) / Math.max(1e-9, hi - lo), share = bad ? t : 1 - t;
      share = Math.max(0, Math.min(1, share));
      return 'rgb(' + Math.round(70 + 185 * share) + ',' + Math.round(165 - 115 * share) + ',' + Math.round(95 - 45 * share) + ')';
    }
    function range(list, k) {
      var v = list.map(function (r) { return num(r[k]); }).filter(function (x) { return x !== null; });
      return v.length ? [Math.min.apply(null, v), Math.max.apply(null, v)] : [0, 1];
    }
    var s = svg('svg', { viewBox: '0 0 ' + W + ' ' + H, width: W, style: 'max-width:100%', role: 'img', 'aria-label': 'Site map' });
    // Aerial ground, drawn: hill-shaded dirt (two noise layers lit from the north-west) with scrub patches.
    // Seeded, so the same data always draws the same site.
    var seed = 0;
    String(o.title || (rows[0] && rows[0][o.label]) || 'site').split('').forEach(function (ch) { seed = (seed * 31 + ch.charCodeAt(0)) >>> 0; });
    function rnd() { seed = (seed + 0x6D2B79F5) >>> 0; var t = seed; t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }
    var uid = 'aio' + Math.floor(rnd() * 1e9);
    var defs = svg('defs');
    defs.innerHTML = '' +
      '<filter id="' + uid + 'g" x="0" y="0" width="100%" height="100%">' +
      '<feTurbulence type="fractalNoise" baseFrequency="0.006" numOctaves="5" seed="' + Math.floor(rnd() * 99) + '" result="h"/>' +
      '<feDiffuseLighting in="h" surfaceScale="16" lighting-color="#fff4e2" result="lit"><feDistantLight azimuth="235" elevation="38"/></feDiffuseLighting>' +
      '<feTurbulence type="fractalNoise" baseFrequency="0.018" numOctaves="4" seed="' + Math.floor(rnd() * 99) + '" result="c"/>' +
      '<feColorMatrix in="c" type="matrix" values="0.30 0 0 0 0.50  0.26 0 0 0 0.41  0.18 0 0 0 0.29  0 0 0 0 1" result="soil"/>' +
      '<feBlend in="soil" in2="lit" mode="multiply" result="ground"/>' +
      '<feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="1" seed="5" result="grain"/>' +
      '<feColorMatrix in="grain" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 0.12 0" result="grainA"/>' +
      '<feComposite in="grainA" in2="ground" operator="over"/></filter>' +
      '<filter id="' + uid + 'v" x="0" y="0" width="100%" height="100%">' +
      '<feTurbulence type="fractalNoise" baseFrequency="0.035" numOctaves="4" seed="' + Math.floor(rnd() * 99) + '"/>' +
      '<feColorMatrix type="matrix" values="0 0 0 0 0.26  0 0 0 0 0.31  0 0 0 0 0.17  0 0 0 -14 5.9"/></filter>' +
      '<filter id="' + uid + 'r" x="0" y="0" width="100%" height="100%">' +
      '<feTurbulence type="fractalNoise" baseFrequency="0.7" numOctaves="2" seed="9"/>' +
      '<feColorMatrix type="matrix" values="0 0 0 0 0.62  0 0 0 0 0.58  0 0 0 0 0.52  0 0 0 0.35 0"/></filter>' +
      '<clipPath id="' + uid + 'c"><rect x="4" y="4" width="' + (W - 8) + '" height="' + (H - 8) + '" rx="10"/></clipPath>';
    s.appendChild(defs);
    var scene = svg('g', { 'clip-path': 'url(#' + uid + 'c)' });
    s.appendChild(scene);
    scene.appendChild(svg('rect', { x: 0, y: 0, width: W, height: H, fill: '#a08d6c' }));
    scene.appendChild(svg('rect', { x: 0, y: 0, width: W, height: H, filter: 'url(#' + uid + 'g)' }));
    var scrub = svg('rect', { x: 0, y: 0, width: W, height: H, filter: 'url(#' + uid + 'v)', opacity: 0.6 });
    scene.appendChild(scrub);
    // A wobbly closed shape (pit bench, dump), smooth through jittered points
    function blob(cx0, cy0, rx0, ry0, jit, phase) {
      var pts = [], n = 56, a1 = phase, a2 = phase * 1.7, a3 = phase * 2.3;
      for (var i = 0; i < n; i++) {
        var th = 2 * Math.PI * i / n;
        var f2 = 1 + jit * (Math.sin(3 * th + a1) * 0.5 + Math.sin(5 * th + a2) * 0.3 + Math.sin(8 * th + a3) * 0.2);
        pts.push([cx0 + rx0 * f2 * Math.cos(th), cy0 + ry0 * f2 * Math.sin(th)]);
      }
      var d2 = '';
      pts.forEach(function (q, i) {
        var nq = pts[(i + 1) % n], mxq = (q[0] + nq[0]) / 2, myq = (q[1] + nq[1]) / 2;
        d2 += (i ? ' Q' + q[0].toFixed(1) + ',' + q[1].toFixed(1) + ' ' : 'M' + mxq.toFixed(1) + ',' + myq.toFixed(1) + ' Q' + nq[0].toFixed(1) + ',' + nq[1].toFixed(1) + ' ') + mxq.toFixed(1) + ',' + myq.toFixed(1);
      });
      return d2 + 'Z';
    }
    function halo(x, y, txt, attrs) {   // a label that stays readable on the imagery
      var t3 = svg('text', Object.assign({ x: x, y: y, 'font-size': 11, 'font-weight': 600, fill: '#1f2328', 'pointer-events': 'none',
        stroke: 'rgba(255,255,255,0.85)', 'stroke-width': 3, 'paint-order': 'stroke', 'stroke-linejoin': 'round' }, attrs || {}), txt);
      return t3;
    }
    function pathD(pts) { return pts.map(function (q, i) { return (i ? 'L' : 'M') + q[0].toFixed(1) + ',' + q[1].toFixed(1); }).join(''); }
    function dist(p1, p2) { return Math.hypot(p1[0] - p2[0], p1[1] - p2[1]); }
    var loaderPts = (marks || []).map(function (m) { return [X(m[o.markers.x]), Y(m[o.markers.y])]; });
    var pitR = null;
    // Lot outlines around the places in each zone; each lot's gate is the edge facing the equipment
    var gates = {}, lots = [];
    var ex = loaderPts.length ? loaderPts.reduce(function (t, q) { return t + q[0]; }, 0) / loaderPts.length : W / 2;
    var ey = loaderPts.length ? loaderPts.reduce(function (t, q) { return t + q[1]; }, 0) / loaderPts.length : H / 2;
    if (o.zone) {
      var zones = {};
      rows.forEach(function (r) { (zones[r[o.zone]] = zones[r[o.zone]] || []).push(r); });
      Object.keys(zones).forEach(function (z) {
        var xs = zones[z].map(function (r) { return X(r[o.x]); }), ys = zones[z].map(function (r) { return Y(r[o.y]); });
        var x0 = Math.min.apply(null, xs) - 26, x1 = Math.max.apply(null, xs) + 26;
        var y0 = Math.min.apply(null, ys) - 40, y1 = Math.max.apply(null, ys) + 22;
        lots.push({ z: z, x0: x0, x1: x1, y0: y0, y1: y1 });
        var gx = Math.max(x0 + 14, Math.min(x1 - 14, ex));
        gates[z] = [gx, ey > (y0 + y1) / 2 ? y1 : y0];
      });
    }
    // The pit: benches between the loaders, kept clear of every lot
    if (loaderPts.length >= 2) {
      var clear = lots.reduce(function (m, L) {
        var dx = Math.max(L.x0 - ex, 0, ex - L.x1), dy = Math.max(L.y0 - ey, 0, ey - L.y1);
        return Math.min(m, Math.hypot(dx, dy));
      }, 1e9);
      var spread = loaderPts.reduce(function (m, q) { return Math.max(m, dist(q, [ex, ey])); }, 0);
      var pr = Math.max(40, Math.min(clear + 18, spread * 0.85));
      pitR = [pr * 1.4, pr * 0.9];
      var phase = rnd() * 6;
      // Open pit: terraced benches, each a lit crest over a shadowed face, darker and greyer toward the floor
      for (var bn = 0; bn < 8; bn++) {
        var f = 1 - bn / 9, tone = bn / 8;
        var r0 = Math.round(170 - 70 * tone), g0 = Math.round(152 - 62 * tone), b0 = Math.round(126 - 46 * tone);
        scene.appendChild(svg('path', { d: blob(ex + bn * 1.6, ey + bn * 1.1, pr * f * 1.4, pr * f * 0.9, 0.09, phase),
                                        fill: 'rgb(' + r0 + ',' + g0 + ',' + b0 + ')', stroke: 'rgba(240,228,205,0.55)', 'stroke-width': 1.6 }));
        scene.appendChild(svg('path', { d: blob(ex + bn * 1.6 + 1.5, ey + bn * 1.1 + 2, pr * f * 1.4 - 3, pr * f * 0.9 - 3, 0.09, phase),
                                        fill: 'none', stroke: 'rgba(40,30,20,0.25)', 'stroke-width': 2 }));
      }
      scene.appendChild(svg('path', { d: blob(ex + 13, ey + 9, pr * 0.18, pr * 0.11, 0.2, phase + 1),
                                      fill: '#3f6f73', stroke: '#2e5458', 'stroke-width': 1, opacity: 0.9 }));
      // Waste dumps: flat-topped piles in the open ground away from the lots and the pit
      var cands = [];
      for (var gx2 = 0.1; gx2 <= 0.9; gx2 += 0.1) for (var gy2 = 0.12; gy2 <= 0.88; gy2 += 0.12) {
        var q2 = [W * gx2, H * gy2], free = dist(q2, [ex, ey]) - pr * 1.5;
        lots.forEach(function (L) { free = Math.min(free, Math.hypot(Math.max(L.x0 - q2[0], 0, q2[0] - L.x1), Math.max(L.y0 - q2[1], 0, q2[1] - L.y1)) - 30); });
        loaderPts.forEach(function (lp) { free = Math.min(free, dist(q2, lp) - 40); });
        cands.push([free, q2]);
      }
      var picked = [];
      cands.sort(function (a3, b4) { return b4[0] - a3[0]; }).forEach(function (cnd) {
        if (picked.length < 2 && picked.every(function (pk) { return dist(pk[1], cnd[1]) > Math.min(160, cnd[0] * 2.2); })) picked.push(cnd);
      });
      picked.forEach(function (cnd, i) {
        if (cnd[0] < 20) return;
        var dr = Math.min(70, cnd[0] * 0.8), ph = rnd() * 6;
        for (var lv = 0; lv < 4; lv++) {
          var k2 = 1 - lv * 0.2, c0 = 178 + lv * 10;
          scene.appendChild(svg('path', { d: blob(cnd[1][0], cnd[1][1] - lv * 2, dr * k2 * 1.3, dr * k2 * 0.8, 0.12, ph),
                                          fill: 'rgb(' + c0 + ',' + (c0 - 8) + ',' + (c0 - 22) + ')', stroke: 'rgba(60,50,40,0.25)', 'stroke-width': 1.2 }));
        }
        scene.appendChild(halo(cnd[1][0] - 24, cnd[1][1] + 4, i ? 'Waste Dump 2' : 'Waste Dump 1', { 'font-weight': 500, fill: '#57606a' }));
      });
    }
    lots.forEach(function (L) {
      var hot = o.highlight && L.z === o.highlight, w2 = L.x1 - L.x0, h2 = L.y1 - L.y0;
      // Gravel pad, a pad edge berm, two shop roofs and the alert outline on the culprit lot
      scene.appendChild(svg('rect', { x: L.x0 - 3, y: L.y0 - 3, width: w2 + 6, height: h2 + 6, rx: 6, fill: 'rgba(90,75,55,0.35)' }));
      scene.appendChild(svg('rect', { x: L.x0, y: L.y0, width: w2, height: h2, rx: 5, fill: '#b9b0a0' }));
      scene.appendChild(svg('rect', { x: L.x0, y: L.y0, width: w2, height: h2, rx: 5, filter: 'url(#' + uid + 'r)' }));
      for (var bx3 = L.x0 + 10; bx3 < L.x1 - 6; bx3 += 14) {
        scene.appendChild(svg('line', { x1: bx3, y1: L.y0 + 16, x2: bx3, y2: L.y1 - 6, stroke: 'rgba(255,255,255,0.45)', 'stroke-width': 1 }));
      }
      var roofX = L.x1 + 8 + rnd() * 6, roofY = L.y0 + 4;
      if (roofX + 26 < W - 8) {
        scene.appendChild(svg('rect', { x: roofX + 3, y: roofY + 3, width: 24, height: 16, fill: 'rgba(0,0,0,0.3)' }));
        scene.appendChild(svg('rect', { x: roofX, y: roofY, width: 24, height: 16, fill: '#dfe3e6', stroke: '#9aa4ae', 'stroke-width': 0.8 }));
        scene.appendChild(svg('rect', { x: roofX + 3, y: roofY + 22, width: 16, height: 11, fill: 'rgba(0,0,0,0.3)' }));
        scene.appendChild(svg('rect', { x: roofX, y: roofY + 19, width: 16, height: 11, fill: '#c9cdd1', stroke: '#9aa4ae', 'stroke-width': 0.8 }));
      }
      if (hot) {
        scene.appendChild(svg('rect', { x: L.x0 - 6, y: L.y0 - 6, width: w2 + 12, height: h2 + 12, rx: 8, fill: 'rgba(207,34,46,0.10)',
                                        stroke: '#ff4d4f', 'stroke-width': 2.5, 'stroke-dasharray': '7 4' }));
      }
      scene.appendChild(halo(L.x0 + 2, L.y0 - 9, L.z, { 'font-size': 12, 'font-weight': 700, fill: hot ? '#a40e26' : '#1f2328' }));
    });
    // Haul-road network: lot gates and loaders, each joined to its two nearest neighbours (plus whatever keeps the
    // network in one piece), every road a gentle curve. Routes take the shortest way along it.
    var net = Object.keys(gates).map(function (z) { return gates[z]; }).concat(loaderPts);
    if (!net.length) net = rows.map(function (r) { return [X(r[o.x]), Y(r[o.y])]; });
    var edges = {};
    function edgeKey(i, j) { return i < j ? i + '-' + j : j + '-' + i; }
    net.forEach(function (q, i) {
      net.map(function (q2, j) { return [j, dist(q, q2)]; }).filter(function (e) { return e[0] !== i; })
        .sort(function (e1, e2) { return e1[1] - e2[1]; }).slice(0, 2).forEach(function (e) { edges[edgeKey(i, e[0])] = 1; });
    });
    var inTree = [0], restNodes = net.map(function (_, i) { return i; }).slice(1);   // spanning tree: no island is left out
    while (restNodes.length) {
      var best = null;
      inTree.forEach(function (i) { restNodes.forEach(function (j) { var d = dist(net[i], net[j]); if (!best || d < best[2]) best = [i, j, d]; }); });
      edges[edgeKey(best[0], best[1])] = 1;
      inTree.push(best[1]); restNodes.splice(restNodes.indexOf(best[1]), 1);
    }
    var geom = {}, adj = net.map(function () { return []; });
    Object.keys(edges).forEach(function (k, n) {
      var ij = k.split('-').map(Number), A = net[ij[0]], B = net[ij[1]], len = dist(A, B);
      var mx2 = (A[0] + B[0]) / 2, my2 = (A[1] + B[1]) / 2, side = n % 2 ? 1 : -1;
      var bx2 = mx2 + side * (-(B[1] - A[1]) / Math.max(1e-9, len)) * len * 0.14;
      var by2 = my2 + side * ((B[0] - A[0]) / Math.max(1e-9, len)) * len * 0.14;
      if (pitR) {   // a road that would cross the pit swings round its rim instead
        var tt = Math.max(0, Math.min(1, ((ex - A[0]) * (B[0] - A[0]) + (ey - A[1]) * (B[1] - A[1])) / Math.max(1e-9, len * len)));
        var px3 = A[0] + tt * (B[0] - A[0]), py3 = A[1] + tt * (B[1] - A[1]);
        var dpx = (px3 - ex) / (pitR[0] * 1.1), dpy = (py3 - ey) / (pitR[1] * 1.1);
        if (Math.hypot(dpx, dpy) < 1) {
          var nx = px3 - ex, ny = py3 - ey, nl = Math.hypot(nx, ny);
          if (nl < 1) { nx = -(B[1] - A[1]); ny = B[0] - A[0]; nl = len; }
          bx2 = ex + nx / nl * pitR[0] * 2.3; by2 = ey + ny / nl * pitR[1] * 2.3;
        }
      }
      var pts = [];
      for (var t = 0; t <= 1.0001; t += 1 / 14) {
        pts.push([(1 - t) * (1 - t) * A[0] + 2 * (1 - t) * t * bx2 + t * t * B[0], (1 - t) * (1 - t) * A[1] + 2 * (1 - t) * t * by2 + t * t * B[1]]);
      }
      geom[k] = pts;
      adj[ij[0]].push([ij[1], len]); adj[ij[1]].push([ij[0], len]);
    });
    function nearestNode(q) { var bi = 0; net.forEach(function (n2, i) { if (dist(n2, q) < dist(net[bi], q)) bi = i; }); return bi; }
    function shortest(a2, b3) {   // Dijkstra over the road network
      var d = net.map(function () { return Infinity; }), prev = net.map(function () { return -1; }), done2 = {};
      d[a2] = 0;
      for (;;) {
        var u = -1;
        d.forEach(function (v, i) { if (!done2[i] && v < Infinity && (u < 0 || v < d[u])) u = i; });
        if (u < 0 || u === b3) break;
        done2[u] = 1;
        adj[u].forEach(function (e) { if (d[u] + e[1] < d[e[0]]) { d[e[0]] = d[u] + e[1]; prev[e[0]] = u; } });
      }
      var path = [];
      for (var v2 = b3; prev[v2] >= 0; v2 = prev[v2]) path.unshift(edgeKey(prev[v2], v2));
      return path;
    }
    // Traffic is summed per road, so a shared road gets as thick as the cycles on it, shaded by their wait
    var traffic = {};
    function addPiece(key, pts, w, cval, route) {
      var t2 = traffic[key] = traffic[key] || { pts: pts, w: 0, cw: 0, n: 0, routes: [] };
      t2.w += w; if (cval !== null) { t2.cw += w * cval; t2.n += w; }
      if (route) t2.routes.push(route);
    }
    function placeAt(x, y) {
      return rows.filter(function (r) { return Math.abs(X(r[o.x]) - x) < 0.5 && Math.abs(Y(r[o.y]) - y) < 0.5; })[0];
    }
    if (o.routes && routes.length) {
      var R = o.routes;
      routes.forEach(function (r) {
        var from = [X(r[R.fromX]), Y(r[R.fromY])], to = [X(r[R.toX]), Y(r[R.toY])];
        var w = R.weight ? (num(r[R.weight]) || 0) : 1, cval = R.color ? num(r[R.color]) : null;
        var place = placeAt(from[0], from[1]), z = place && o.zone ? place[o.zone] : null;
        var start = z && gates[z] ? gates[z] : from;
        if (start !== from) addPiece('lane:' + from, [from, start], w, cval, r);
        shortest(nearestNode(start), nearestNode(to)).forEach(function (k) { addPiece(k, geom[k], w, cval, r); });
      });
    }
    // Road surface first (every road, used or not), then the traffic on top
    Object.keys(geom).forEach(function (k) {
      scene.appendChild(svg('path', { d: pathD(geom[k]), fill: 'none', stroke: 'rgba(80,65,45,0.45)', 'stroke-width': 16, 'stroke-linecap': 'round' }));
    });
    Object.keys(traffic).filter(function (k) { return k.indexOf('lane:') === 0; }).concat(Object.keys(geom)).forEach(function (k) {
      var pts2 = geom[k] || traffic[k].pts, wide = geom[k] ? 12 : 5;
      scene.appendChild(svg('path', { d: pathD(pts2), fill: 'none', stroke: '#d8c9a6', 'stroke-width': wide, 'stroke-linecap': 'round' }));
      if (geom[k]) scene.appendChild(svg('path', { d: pathD(pts2), fill: 'none', stroke: 'rgba(150,130,100,0.5)', 'stroke-width': 1, 'stroke-dasharray': '6 9' }));
    });
    var tk = Object.keys(traffic), tw = tk.map(function (k) { return traffic[k].w; }), hits = [];
    var wmax = Math.max.apply(null, tw.concat([1e-9]));
    var cavg = tk.map(function (k) { return traffic[k].n ? traffic[k].cw / traffic[k].n : null; }).filter(function (v) { return v !== null; });
    var clo = Math.min.apply(null, cavg), chi = Math.max.apply(null, cavg);
    tk.sort(function (a, b2) {   // calm roads first, the worst on top
      var d = traffic[a].cw / Math.max(1e-9, traffic[a].n) - traffic[b2].cw / Math.max(1e-9, traffic[b2].n);
      return bad ? d : -d;
    }).forEach(function (k) {
      var t = traffic[k], v = t.n ? t.cw / t.n : null;
      scene.appendChild(svg('path', { d: pathD(t.pts), fill: 'none', stroke: o.routes.color ? shade(v, clo, chi) : '#57606a',
                                  'stroke-width': (1.5 + 5 * t.w / wmax).toFixed(1), 'stroke-opacity': 0.9,
                                  'stroke-linecap': 'round', 'stroke-linejoin': 'round' }));
      hits.push([k, t]);
    });
    // Equipment
    (marks || []).forEach(function (m) {
      var mx = X(m[o.markers.x]), my = Y(m[o.markers.y]), rot = Math.atan2(ey - my, ex - mx) * 180 / Math.PI;
      // A loader from above: tracks, a turning body and a boom reaching toward the pit
      var ex2 = svg('g', { 'data-marker': (marks || []).indexOf(m), transform: 'translate(' + mx + ',' + my + ') rotate(' + rot.toFixed(0) + ')' });
      ex2.appendChild(svg('rect', { x: -10, y: -9, width: 20, height: 18, rx: 2, fill: 'rgba(0,0,0,0.35)', transform: 'translate(2,2)' }));
      ex2.appendChild(svg('rect', { x: -10, y: -9, width: 20, height: 4, fill: '#2b2b2b' }));
      ex2.appendChild(svg('rect', { x: -10, y: 5, width: 20, height: 4, fill: '#2b2b2b' }));
      ex2.appendChild(svg('rect', { x: -8, y: -6, width: 14, height: 12, rx: 2, fill: '#f2b705', stroke: '#6b5200', 'stroke-width': 0.8 }));
      ex2.appendChild(svg('rect', { x: 4, y: -2, width: 16, height: 4, fill: '#d99e00' }));
      ex2.appendChild(svg('rect', { x: 19, y: -4, width: 5, height: 8, rx: 1, fill: '#3a3a3a' }));
      s.appendChild(ex2);
      s.appendChild(halo(mx + 14, my - 10, m[o.markers.label]));
    });
    // Places
    var key = o.color || o.size, cr2 = range(rows, key), sr = range(rows, o.size || key);
    rows.forEach(function (r) {
      var rad = 7 + 11 * ((num(r[o.size || key]) || 0) - sr[0]) / Math.max(1e-9, sr[1] - sr[0]);
      rad = Math.max(6, rad * 0.75);
      var circle = svg('circle', { 'data-place': rows.indexOf(r), cx: X(r[o.x]), cy: Y(r[o.y]), r: rad.toFixed(1), fill: shade(r[key], cr2[0], cr2[1]),
                                   'fill-opacity': 0.55, stroke: shade(r[key], cr2[0], cr2[1]), 'stroke-width': 2.5 });
      s.appendChild(circle);
      s.appendChild(halo(X(r[o.x]), Y(r[o.y]) - rad - 4, r[o.label], { 'text-anchor': 'middle', 'font-size': 10, 'font-weight': 500 }));
    });
    // Moving things: latest position each, spread around the place they're at
    var count = 0;
    if (o.trucks && trucks.length) {
      var T = o.trucks, latest = {};
      trucks.forEach(function (t) {
        var id = t[T.id], prev = latest[id];
        if (!prev || (T.date && String(t[T.date]) > String(prev[T.date]))) latest[id] = t;
      });
      var at = {};
      Object.keys(latest).sort().forEach(function (id) {
        var t = latest[id], k = t[T.x] + ',' + t[T.y], n = at[k] = (at[k] || 0) + 1;
        var ang = n * 2.4, dist = 12 + 4 * Math.floor(n / 6);
        var tx = X(t[T.x]) + Math.cos(ang) * dist, ty = Y(t[T.y]) + Math.sin(ang) * dist;
        var dot = svg('g', { transform: 'translate(' + tx.toFixed(1) + ',' + ty.toFixed(1) + ') rotate(' + ((n * 47) % 180 - 90) + ')' });
        dot.appendChild(svg('rect', { x: -5, y: -3, width: 11, height: 7, rx: 1, fill: 'rgba(0,0,0,0.35)', transform: 'translate(1.5,1.5)' }));
        dot.appendChild(svg('rect', { x: -6, y: -4, width: 10, height: 8, rx: 1, fill: '#f5c400', stroke: '#7a6000', 'stroke-width': 0.6 }));
        dot.appendChild(svg('rect', { x: 4, y: -3.5, width: 3.5, height: 7, rx: 0.8, fill: '#3a3a3a' }));
        dot.appendChild(svg('title', {}, id + (T.date ? ' · last cycle ' + label(t[T.date]) : '')));
        s.appendChild(dot);
        count++;
      });
    }
    // Tooltips: an HTML card that follows the pointer (built with text nodes, never HTML from the data)
    var wrap = el('div', { 'class': 'aio-map' }), tip = el('div', { 'class': 'aio-tip' });
    wrap.appendChild(s); wrap.appendChild(tip);
    body.appendChild(wrap);
    function fieldLines(row, fields) {
      return (fields || []).filter(function (f) { return row[f.field] !== undefined && row[f.field] !== null; })
        .map(function (f) { return [f.label || f.field, fmt(row[f.field], f.format)]; });
    }
    function show(evt, title, lines, groups) {
      tip.textContent = '';
      tip.appendChild(el('div', { 'class': 'aio-tip-title' }, title));
      (lines || []).forEach(function (ln) {
        var d3 = el('div', { 'class': 'aio-tip-row' });
        d3.appendChild(el('span', {}, ln[0])); d3.appendChild(el('b', {}, ln[1]));
        tip.appendChild(d3);
      });
      (groups || []).forEach(function (g) {
        tip.appendChild(el('div', { 'class': 'aio-tip-sub' }, g[0]));
        if (!g[1].length) return;
        var line = el('div', { 'class': 'aio-tip-inline' });
        g[1].forEach(function (ln, i) {
          if (i) line.appendChild(document.createTextNode(' · '));
          line.appendChild(document.createTextNode(short(ln[0]) + ' '));
          line.appendChild(el('b', {}, ln[1]));
        });
        tip.appendChild(line);
      });
      tip.style.display = 'block';
      move(evt);
    }
    function move(evt) {
      var box = wrap.getBoundingClientRect(), x = evt.clientX - box.left + 14, y = evt.clientY - box.top + 14;
      if (x + tip.offsetWidth > box.width) x = Math.max(0, x - tip.offsetWidth - 28);
      if (y + tip.offsetHeight > box.height) y = Math.max(0, y - tip.offsetHeight - 28);
      tip.style.left = x + 'px'; tip.style.top = y + 'px';
    }
    function hide() { tip.style.display = 'none'; }
    function short(lbl) { return String(lbl).replace(/^avg\.?\s+/i, '').replace(/\s*\((min|l|tonnes|t)\)\s*$/i, '').toLowerCase(); }
    function avgLabel(lbl) { return /^avg/i.test(lbl) ? lbl : 'Avg ' + lbl; }
    function hover(node, build) {
      node.addEventListener('mouseenter', function (e) { var c = build(); show(e, c[0], c[1], c[2]); });
      node.addEventListener('mousemove', move);
      node.addEventListener('mouseleave', hide);
    }
    var R2 = o.routes || {};
    function routeName(r) {
      var a = R2.fromLabel ? r[R2.fromLabel] : '', b = R2.toLabel ? r[R2.toLabel] : '';
      return (a || b) ? (a + ' → ' + b) : 'Route';
    }
    // Roads: the traffic on this road, then the busiest routes that use it with their own numbers
    hits.forEach(function (h) {
      var k = h[0], t = h[1], v = t.n ? t.cw / t.n : null;
      var hit = svg('path', { d: pathD(t.pts), fill: 'none', stroke: 'transparent', 'stroke-width': 16, 'stroke-linecap': 'round',
                              'class': 'aio-hit' });
      hit.addEventListener('mouseenter', function () { hit.setAttribute('stroke', 'rgba(255,255,255,0.35)'); });
      hit.addEventListener('mouseleave', function () { hit.setAttribute('stroke', 'transparent'); });
      hover(hit, function () {
        var head = [[(R2.weightLabel || 'Cycles') + ' on this road', fmt(t.w, R2.weightFormat || 'number')]];
        if (v !== null) head.push([avgLabel(R2.colorLabel || R2.color), fmt(v, R2.colorFormat || o.format)]);
        var groups = t.routes.slice().sort(function (a, b) { return (num(b[R2.weight]) || 0) - (num(a[R2.weight]) || 0); })
          .slice(0, 4).map(function (r) {
            var ls = fieldLines(r, R2.tooltip);
            var shown = (R2.tooltip || []).map(function (f) { return f.field; });
            if (!ls.length && R2.color) ls.push([R2.colorLabel || R2.color, fmt(r[R2.color], R2.colorFormat || o.format)]);
            if (R2.weight && shown.indexOf(R2.weight) < 0) ls.push([R2.weightLabel || 'Cycles', fmt(r[R2.weight], R2.weightFormat || 'number')]);
            return [routeName(r), ls];
          });
        if (t.routes.length > 4) groups.push(['+ ' + (t.routes.length - 4) + ' more routes on this road', []]);
        return [k.indexOf('lane:') === 0 ? 'Lot lane' : 'Haul road', head, groups];
      });
      // Under the loaders and the places, so their own tooltips win where they overlap a road
      s.insertBefore(hit, s.querySelector('g[data-marker]') || s.querySelector('circle[data-place]'));
    });
    // Places and equipment: their own numbers
    Array.prototype.forEach.call(s.querySelectorAll('circle[data-place]'), function (c2, i) {
      var r = rows[Number(c2.getAttribute('data-place'))];
      hover(c2, function () {
        var ls = [[o.colorLabel || key, fmt(r[key], o.format)]].concat(fieldLines(r, o.tooltip));
        if (o.zone) ls.unshift(['Zone', r[o.zone]]);
        return [r[o.label], ls];
      });
    });
    Array.prototype.forEach.call(s.querySelectorAll('g[data-marker]'), function (g2) {
      var m = (marks || [])[Number(g2.getAttribute('data-marker'))];
      hover(g2, function () { return [m[o.markers.label], fieldLines(m, o.markers.tooltip)]; });
    });
    var parts = ['Rings: ' + (o.colorLabel || key) + ', green better, red worse (' + fmt(cr2[0], o.format) + ' to ' + fmt(cr2[1], o.format) + ')'];
    if ((marks || []).length) parts.push('yellow machines: loaders');
    if (o.routes && routes.length) parts.push('roads: haul routes, thicker = more ' + (o.routes.weightLabel || 'traffic') + (o.routes.color ? ', shaded by ' + (o.routes.colorLabel || o.routes.color) : ''));
    if (count) parts.push(count + ' trucks: where each ' + (o.trucks.noun || 'truck') + ' was last');
    body.appendChild(el('p', { 'class': 'aio-note' }, parts.join(' · ') + '.'));
  }

  // Table: {columns: [{field, label, format}], sort: field, dir, limit}
  function table(body, rows, o) {
    if (o.sort) rows = sortBy(rows, o.sort, o.dir || 'desc');
    if (o.limit) rows = rows.slice(0, o.limit);
    var t = el('table', { 'class': 'aio-table' });
    var head = el('tr');
    o.columns.forEach(function (c) { head.appendChild(el('th', {}, c.label || c.field)); });
    t.appendChild(head);
    rows.forEach(function (r) {
      var tr = el('tr');
      o.columns.forEach(function (c) { tr.appendChild(el('td', {}, c.format ? fmt(r[c.field], c.format) : String(r[c.field]))); });
      t.appendChild(tr);
    });
    body.appendChild(t);
  }

  function sparkline(box, rows, key, good) {
    var vals = rows.map(function (r) { return num(r[key]); }).filter(function (v) { return v !== null; });
    if (vals.length < 2) return;
    var W = 100, H = 34, lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
    var pts = vals.map(function (v, i) {
      return (i * W / (vals.length - 1)).toFixed(1) + ',' + (H - 3 - (v - lo) / Math.max(1e-9, hi - lo) * (H - 6)).toFixed(1);
    });
    var rising = vals[vals.length - 1] >= vals[0];
    var color = (rising === (good === 'up')) ? '#1a7f37' : '#cf222e';
    var s = svg('svg', { viewBox: '0 0 ' + W + ' ' + H, width: W, height: H, 'aria-hidden': 'true' });
    s.appendChild(svg('polyline', { points: pts.join(' '), fill: 'none', stroke: color, 'stroke-width': 2 }));
    box.appendChild(s);
  }

  // Filter bar: one dropdown per dimension; a change re-renders the page with the filter applied
  function filterBar(app, fields, rerender) {
    var bar = el('div', { 'class': 'aio-filters' });
    fields.forEach(function (field) {
      var wrap = el('label', { 'class': 'aio-filter' });
      wrap.appendChild(el('span', {}, field));
      var sel = el('select');
      sel.appendChild(el('option', { value: '' }, 'All'));
      wrap.appendChild(sel);
      bar.appendChild(wrap);
      app.ds.queryAsync({ fields: [{ fieldCaption: field }] }).then(function (res) {
        (res.data || []).map(function (r) { return r[field]; }).filter(function (v) { return v != null; })
          .sort().forEach(function (v) { sel.appendChild(el('option', { value: v }, v)); });
        sel.value = app.filters[field] || '';
      });
      sel.addEventListener('change', function () { app.filters[field] = sel.value; rerender(); });
    });
    return bar;
  }

  function start(opts) {
    var root = document.getElementById('app');
    function fail(msg) { root.textContent = ''; root.appendChild(el('p', { 'class': 'aio-error' }, 'Live query unavailable: ' + msg)); }
    if (!window.tableau || !tableau.extensions) { fail('Extensions API not loaded'); return; }
    if (opts.brand) document.documentElement.style.setProperty('--aio-brand', opts.brand);
    tableau.extensions.initializeAsync().then(function () {
      return tableau.extensions.workbook.getAllDataSourcesAsync();
    }).then(function (list) {
      var ds = list.filter(function (d) { return d.name === window.AIO_DATASOURCE; })[0] || list[0];
      if (!ds) throw new Error('no datasource in the workbook');
      var app = new App(root, opts, ds);
      var page = el('div', { 'class': 'aio-page' });
      function render() {
        page.textContent = '';
        app.root = page;
        opts.render(app);
      }
      root.textContent = '';
      var header = el('header', { 'class': 'aio-header' });
      header.appendChild(el('h1', {}, opts.title));
      if (opts.subtitle) header.appendChild(el('p', {}, opts.subtitle));
      root.appendChild(header);
      if (opts.filters && opts.filters.length) root.appendChild(filterBar(app, opts.filters, render));
      root.appendChild(page);
      render();
    }).catch(function (e) { fail((e && (e.message || e.errorCode)) || String(e)); });
  }

  window.AIO = { start: start, fmt: fmt };
})();
