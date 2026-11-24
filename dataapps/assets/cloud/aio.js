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
    return Math.abs(n) >= 1000 ? abbreviate(n) : n.toFixed(Math.abs(n) < 10 ? 2 : 1);
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
  App.prototype.map = function (body, queryId, o) {
    var self = this;
    this._draw(body, queryId, function (rows) {
      if (!o.markers) { siteMap(body, rows, o, []); return; }
      self.query(o.markers.query).then(function (marks) { siteMap(body, rows, o, marks); },
                                       function () { siteMap(body, rows, o, []); });
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

  // Site map on a 0-100 grid: {label, x, y, size?, color?, format, highlight?, markers?: {query, label, x, y}}.
  // Circles are the rows (e.g. parking spots), sized by `size` and shaded by `color` (red = worse when
  // goodDirection is 'down'); markers are fixed things (e.g. loaders) drawn as labelled squares.
  function siteMap(body, rows, o, marks) {
    var W = Math.min(900, Math.max(420, body.clientWidth || 640)), H = Math.round(W * 0.62), P = 24;
    var X = function (v) { return P + num(v) / 100 * (W - 2 * P); };
    var Y = function (v) { return H - P - num(v) / 100 * (H - 2 * P); };
    var s = svg('svg', { viewBox: '0 0 ' + W + ' ' + H, width: W, style: 'max-width:100%', role: 'img', 'aria-label': 'Site map' });
    s.appendChild(svg('rect', { x: P / 2, y: P / 2, width: W - P, height: H - P, rx: 8, fill: '#f4f1ea', stroke: '#e1dccf' }));
    var key = o.color || o.size;
    var vals = rows.map(function (r) { return num(r[key]); }).filter(function (v) { return v !== null; });
    var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
    var sizes = rows.map(function (r) { return num(r[o.size || key]) || 0; });
    var smax = Math.max.apply(null, sizes.concat([1e-9])), smin = Math.min.apply(null, sizes);
    var bad = (o.goodDirection || 'down') === 'down';
    (marks || []).forEach(function (m) {
      var mx = X(m[o.markers.x]), my = Y(m[o.markers.y]);
      s.appendChild(svg('rect', { x: mx - 7, y: my - 7, width: 14, height: 14, rx: 2, fill: '#24292f' }));
      s.appendChild(svg('text', { x: mx + 10, y: my + 4, 'class': 'aio-axis', 'font-weight': 600 }, m[o.markers.label]));
    });
    rows.forEach(function (r) {
      var v = num(r[key]), t = (v - lo) / Math.max(1e-9, hi - lo), share = bad ? t : 1 - t;
      var red = Math.round(80 + 175 * share), green = Math.round(160 - 110 * share), blue = Math.round(90 - 40 * share);
      var rad = 6 + 12 * ((num(r[o.size || key]) || 0) - smin) / Math.max(1e-9, smax - smin);
      var hot = o.highlight && (r[o.label] === o.highlight);
      var c = svg('circle', { cx: X(r[o.x]), cy: Y(r[o.y]), r: rad.toFixed(1), fill: 'rgb(' + red + ',' + green + ',' + blue + ')',
                              'fill-opacity': 0.85, stroke: hot ? '#24292f' : '#ffffff', 'stroke-width': hot ? 2.5 : 1.5 });
      c.appendChild(svg('title', {}, r[o.label] + ': ' + fmt(v, o.format)));
      s.appendChild(c);
      s.appendChild(svg('text', { x: X(r[o.x]), y: Y(r[o.y]) - rad - 3, 'text-anchor': 'middle', 'class': 'aio-axis' }, r[o.label]));
    });
    body.appendChild(s);
    body.appendChild(el('p', { 'class': 'aio-note' }, 'Green = better, red = worse ' + (o.colorLabel || key) +
      ' (' + fmt(lo, o.format) + ' to ' + fmt(hi, o.format) + '). Squares: ' + ((marks || []).length ? 'fixed equipment.' : 'none.')));
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
