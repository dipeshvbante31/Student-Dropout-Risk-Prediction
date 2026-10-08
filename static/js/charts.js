/* Dependency-free SVG charts. Data comes from JSON blocks rendered by the server from the database/model. */
(function () {
  var NS = 'http://www.w3.org/2000/svg';
  function el(name, attrs, text) {
    var e = document.createElementNS(NS, name);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    if (text !== undefined) e.textContent = text;
    return e;
  }
  function trunc(s, n) { s = String(s); return s.length > n ? s.slice(0, n - 1) + '\u2026' : s; }
  function fmt(v, unit) { return (Math.round(v * 10) / 10) + (unit || ''); }
  function svg(w, h, label) {
    return el('svg', { viewBox: '0 0 ' + w + ' ' + h, class: 'svg-chart', role: 'img', 'aria-label': label || 'chart' });
  }
  function title(node, t) { node.appendChild(el('title', {}, t)); return node; }

  function bar(box, data, unit, label) {
    var W = 560, H = 260, m = { l: 40, r: 10, t: 16, b: 46 };
    var s = svg(W, H, label), max = Math.max.apply(null, data.map(function (d) { return d.value; }).concat([1]));
    var bw = (W - m.l - m.r) / data.length;
    [0, 0.5, 1].forEach(function (f) {
      var y = H - m.b - f * (H - m.t - m.b);
      s.appendChild(el('line', { x1: m.l, x2: W - m.r, y1: y, y2: y, class: 'grid' }));
      s.appendChild(el('text', { x: m.l - 6, y: y + 4, class: 'ct', 'text-anchor': 'end' }, fmt(max * f, '')));
    });
    data.forEach(function (d, i) {
      var h = (d.value / max) * (H - m.t - m.b), x = m.l + i * bw + bw * 0.15, y = H - m.b - h;
      s.appendChild(title(el('rect', { x: x, y: y, width: bw * 0.7, height: Math.max(h, 0), class: 'c-primary' }),
        d.label + ': ' + fmt(d.value, unit) + (d.n !== undefined ? ' (n=' + d.n + ')' : '')));
      s.appendChild(el('text', { x: x + bw * 0.35, y: y - 4, class: 'ct', 'text-anchor': 'middle' }, fmt(d.value, unit)));
      s.appendChild(el('text', { x: x + bw * 0.35, y: H - m.b + 16, class: 'ct', 'text-anchor': 'middle' }, trunc(d.label, Math.max(6, Math.floor(bw / 6)))));
    });
    box.appendChild(s);
  }
  function hbar(box, data, unit, label) {
    var rowH = 28, m = { l: 190, r: 60, t: 8, b: 8 }, W = 560, H = m.t + m.b + rowH * data.length;
    var s = svg(W, H, label), max = Math.max.apply(null, data.map(function (d) { return d.value; }).concat([0.0001]));
    data.forEach(function (d, i) {
      var y = m.t + i * rowH, w = Math.max(0, d.value / max) * (W - m.l - m.r);
      s.appendChild(title(el('text', { x: m.l - 8, y: y + 17, class: 'ct', 'text-anchor': 'end' }, trunc(d.label, 30)), d.label));
      s.appendChild(title(el('rect', { x: m.l, y: y + 4, width: w, height: rowH - 10, class: 'c-primary' }),
        d.label + ': ' + fmt(d.value, unit) + (d.n !== undefined ? ' (n=' + d.n + ')' : '')));
      s.appendChild(el('text', { x: m.l + w + 6, y: y + 17, class: 'ct' }, fmt(d.value, unit)));
    });
    box.appendChild(s);
  }
  function line(box, data, unit, label) {
    var W = 560, H = 240, m = { l: 40, r: 14, t: 16, b: 40 };
    var s = svg(W, H, label), vals = data.map(function (d) { return d.count !== undefined ? d.count : d.value; });
    var max = Math.max.apply(null, vals.concat([1])), step = data.length > 1 ? (W - m.l - m.r) / (data.length - 1) : 0;
    [0, 0.5, 1].forEach(function (f) {
      var y = H - m.b - f * (H - m.t - m.b);
      s.appendChild(el('line', { x1: m.l, x2: W - m.r, y1: y, y2: y, class: 'grid' }));
      s.appendChild(el('text', { x: m.l - 6, y: y + 4, class: 'ct', 'text-anchor': 'end' }, fmt(max * f, '')));
    });
    var pts = data.map(function (d, i) { return [m.l + i * step, H - m.b - (vals[i] / max) * (H - m.t - m.b)]; });
    s.appendChild(el('polyline', { points: pts.map(function (p) { return p.join(','); }).join(' '), class: 'line' }));
    pts.forEach(function (p, i) {
      s.appendChild(title(el('circle', { cx: p[0], cy: p[1], r: 3.5, class: 'c-primary' }), data[i].label + ': ' + vals[i] +
        (data[i].avg !== undefined ? ' predictions, mean risk ' + fmt(data[i].avg * 100, '%') : '')));
      if (data.length <= 12 || i % Math.ceil(data.length / 10) === 0)
        s.appendChild(el('text', { x: p[0], y: H - m.b + 16, class: 'ct', 'text-anchor': 'middle' }, data[i].label));
    });
    box.appendChild(s);
  }
  function donut(box, data, unit, label) {
    var total = data.reduce(function (a, d) { return a + d.value; }, 0);
    if (!total) { box.textContent = 'No data to display.'; return; }
    var s = svg(560, 220, label), cx = 110, cy = 110, r = 80, a0 = -Math.PI / 2;
    data.forEach(function (d, i) {
      var cls = d.key ? 'c-' + d.key.toLowerCase() : 'c-primary';
      if (d.value) {
        var frac = d.value / total, a1 = a0 + frac * 2 * Math.PI;
        if (frac > 0.9999) {
          s.appendChild(title(el('circle', { cx: cx, cy: cy, r: r, class: cls + ' ring' }), d.label + ': ' + d.value));
        } else {
          var big = frac > 0.5 ? 1 : 0;
          var p = ['M', cx + r * Math.cos(a0), cy + r * Math.sin(a0), 'A', r, r, 0, big, 1, cx + r * Math.cos(a1), cy + r * Math.sin(a1)].join(' ');
          s.appendChild(title(el('path', { d: p, class: cls + ' ringstroke', fill: 'none', 'stroke-width': 28 }), d.label + ': ' + d.value));
        }
        a0 = a1;
      }
      s.appendChild(el('rect', { x: 250, y: 70 + i * 28, width: 14, height: 14, class: cls }));
      s.appendChild(el('text', { x: 272, y: 82 + i * 28, class: 'ct' }, d.label + ': ' + d.value + ' (' + Math.round(d.value / total * 100) + '%)'));
    });
    s.appendChild(el('text', { x: cx, y: cy + 5, class: 'ct big', 'text-anchor': 'middle' }, total));
    box.appendChild(s);
  }
  function roc(box, d, unit, label) {
    var S = 300, m = 36, s = svg(340, 330, label);
    var X = function (v) { return m + v * (S - m - 8); }, Y = function (v) { return S - m - v * (S - m - 8) + 8; };
    s.appendChild(el('line', { x1: X(0), y1: Y(0), x2: X(1), y2: Y(1), class: 'grid dash' }));
    s.appendChild(el('line', { x1: X(0), y1: Y(0), x2: X(1), y2: Y(0), class: 'axis' }));
    s.appendChild(el('line', { x1: X(0), y1: Y(0), x2: X(0), y2: Y(1), class: 'axis' }));
    s.appendChild(el('polyline', { points: d.fpr.map(function (f, i) { return X(f) + ',' + Y(d.tpr[i]); }).join(' '), class: 'line' }));
    s.appendChild(el('text', { x: X(0.5), y: S + 14, class: 'ct', 'text-anchor': 'middle' }, 'False positive rate'));
    s.appendChild(el('text', { x: 10, y: Y(0.5), class: 'ct', transform: 'rotate(-90 10 ' + Y(0.5) + ')', 'text-anchor': 'middle' }, 'True positive rate'));
    box.appendChild(s);
  }
  var kinds = { bar: bar, hbar: hbar, line: line, donut: donut, roc: roc };
  window.renderCharts = function () {
    document.querySelectorAll('.chart[data-chart]').forEach(function (box) {
      var src = document.getElementById(box.getAttribute('data-source')), fn = kinds[box.getAttribute('data-chart')];
      box.textContent = '';
      if (!src || !fn) return;
      try {
        var data = JSON.parse(src.textContent);
        if (Array.isArray(data) && !data.length) { box.textContent = 'No data to display.'; return; }
        fn(box, data, box.getAttribute('data-unit') || '', box.getAttribute('aria-label'));
      } catch (e) { box.textContent = 'Chart could not be rendered.'; }
    });
  };
  window.renderCharts();
})();
