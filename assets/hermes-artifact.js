/* Hermes Interactive Artifacts — universal renderer.
   Reads the inline JSON payload written by tools/refresh.py and renders
   summary cards, charts (Chart.js if the CDN is reachable), and
   filterable/sortable tables. No build step, no fetches, no framework. */
(function () {
  'use strict';
  /* Vivid, full-opacity palette per Jason's chart preferences. */
  var PALETTE = ['#3b82f6', '#ef4444', '#22c55e', '#eab308', '#a855f7', '#06b6d4'];

  function h(tag, attrs) {
    var node = document.createElement(tag);
    attrs = attrs || {};
    Object.keys(attrs).forEach(function (k) {
      if (k === 'text') node.textContent = attrs[k];
      else if (k === 'class') node.className = attrs[k];
      else node.setAttribute(k, attrs[k]);
    });
    for (var i = 2; i < arguments.length; i++) {
      if (arguments[i]) node.appendChild(arguments[i]);
    }
    return node;
  }

  function payload() {
    return JSON.parse(document.getElementById('hermes-artifact-data').textContent);
  }

  function renderCards(d) {
    var wrap = h('div', { class: 'ha-cards' });
    (d.summary || []).forEach(function (c) {
      wrap.appendChild(h('div', { class: 'ha-card' + (c.tone ? ' tone-' + c.tone : '') },
        h('div', { class: 'label', text: c.label }),
        h('div', { class: 'value', text: String(c.value) })));
    });
    return wrap;
  }

  function renderChart(chart) {
    var box = h('div', { class: 'ha-chart' }, h('h3', { text: chart.title }));
    if (typeof Chart === 'undefined') {
      box.appendChild(h('div', { class: 'ha-notes',
        text: 'Chart.js CDN unreachable — values remain in tables/notes.' }));
      return box;
    }
    var canvas = h('canvas');
    box.appendChild(h('div', { class: 'box' }, canvas));
    var datasets = (chart.series || []).map(function (s, i) {
      return {
        label: s.label,
        data: s.data,
        backgroundColor: PALETTE[i % PALETTE.length],
        borderColor: PALETTE[i % PALETTE.length],
        borderWidth: 2, tension: 0.35, pointRadius: 2,
        fill: chart.type === 'line'
      };
    });
    new Chart(canvas.getContext('2d'), {
      type: chart.type,
      data: { labels: chart.labels || [], datasets: datasets },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { position: 'top', labels: { boxWidth: 12 } } }
      }
    });
    return box;
  }

  function renderTable(table) {
    var wrap = h('div', { class: 'ha-tablewrap' }, h('h3', { text: table.title }));
    var filter = h('input', { class: 'ha-filter', placeholder: 'Filter...' });
    var tbl = h('table');
    var headRow = h('tr');
    var thead = h('thead'), tbody = h('tbody');
    (table.columns || []).forEach(function (c) {
      headRow.appendChild(h('th', { text: c }));
    });
    thead.appendChild(headRow);
    tbl.appendChild(thead);
    tbl.appendChild(tbody);
    var rows = table.rows || [];

    function fill(list) {
      tbody.textContent = '';
      list.forEach(function (r) {
        var tr = h('tr');
        (table.columns || []).forEach(function (_, i) {
          tr.appendChild(h('td', { text: r[i] == null ? '' : String(r[i]) }));
        });
        tbody.appendChild(tr);
      });
    }
    fill(rows);
    filter.addEventListener('input', function () {
      var q = filter.value.toLowerCase();
      fill(rows.filter(function (r) {
        return r.some(function (cell) {
          return String(cell == null ? '' : cell).toLowerCase().indexOf(q) !== -1;
        });
      }));
    });
    var sortDir = {};
    headRow.addEventListener('click', function (e) {
      var idx = Array.prototype.indexOf.call(headRow.children, e.target);
      if (idx < 0) return;
      sortDir[idx] = !sortDir[idx];
      fill(rows.slice().sort(function (a, b) {
        var x = a[idx], y = b[idx];
        var nx = parseFloat(x), ny = parseFloat(y);
        var cmp = (!isNaN(nx) && !isNaN(ny)) ? nx - ny
          : String(x).localeCompare(String(y));
        return sortDir[idx] ? cmp : -cmp;
      }));
    });
    wrap.appendChild(filter);
    wrap.appendChild(tbl);
    return wrap;
  }

  var GROUP_COLOR = {
    construction: '#f59e0b',
    development: '#3b82f6',
    trading: '#22c55e',
    hub: '#eab308',
    daily: '#a855f7',
    inbox: '#ef4444',
    dangling: '#94a3b8',
    templates: '#06b6d4',
    attachments: '#64748b'
  };

  function renderGraph(graph) {
    var box = h('div', { class: 'ha-graph' }, h('h3', { text: 'Graph view' }));
    var legend = h('div', { class: 'ha-glegend' });
    var groups = {};
    (graph.nodes || []).forEach(function (n) { groups[n.group || 'hub'] = true; });
    Object.keys(groups).forEach(function (g) {
      legend.appendChild(h('span', { class: 'swatch' },
        h('i', { style: 'background:' + (GROUP_COLOR[g] || '#94a3b8') }),
        h('span', { text: g })));
    });
    box.appendChild(legend);
    var stage = h('div', { class: 'ha-gstage' });
    var canvas = h('canvas');
    var tip = h('div', { class: 'ha-gtip', text: '' });
    stage.appendChild(canvas);
    stage.appendChild(tip);
    box.appendChild(stage);

    var nodes = (graph.nodes || []).map(function (n, i) {
      return {
        id: n.id, label: n.label || n.id, group: n.group || 'hub',
        size: Math.max(1, n.size || 1),
        x: Math.cos(i) * 80, y: Math.sin(i) * 80, vx: 0, vy: 0
      };
    });
    var index = {};
    nodes.forEach(function (n) { index[n.id] = n; });
    var links = [];
    (graph.edges || []).forEach(function (e) {
      if (index[e.source] && index[e.target]) {
        links.push({ a: index[e.source], b: index[e.target] });
      }
    });
    var groupList = Object.keys(groups);
    var attract = {};
    groupList.forEach(function (g, i) {
      var ang = (i / Math.max(1, groupList.length)) * Math.PI * 2;
      attract[g] = { x: Math.cos(ang) * 220, y: Math.sin(ang) * 220 };
    });

    var drag = null, hover = null, raf = 0;
    function resize() {
      var r = stage.getBoundingClientRect();
      var dpr = window.devicePixelRatio || 1;
      canvas.width = Math.max(1, r.width * dpr);
      canvas.height = Math.max(1, 560 * dpr);
      canvas.style.width = r.width + 'px';
      canvas.style.height = '560px';
    }
    resize();
    window.addEventListener('resize', resize);

    function step() {
      var i, j, n, m, dx, dy, dist, f, k;
      for (i = 0; i < nodes.length; i++) {
        n = nodes[i];
        for (j = i + 1; j < nodes.length; j++) {
          m = nodes[j];
          dx = n.x - m.x; dy = n.y - m.y;
          dist = Math.sqrt(dx * dx + dy * dy) || 0.01;
          f = 420 / (dist * dist);
          n.vx += dx / dist * f; n.vy += dy / dist * f;
          m.vx -= dx / dist * f; m.vy -= dy / dist * f;
        }
      }
      for (i = 0; i < links.length; i++) {
        k = links[i];
        dx = k.b.x - k.a.x; dy = k.b.y - k.a.y;
        dist = Math.sqrt(dx * dx + dy * dy) || 0.01;
        f = (dist - 46) * 0.012;
        k.a.vx += dx / dist * f; k.a.vy += dy / dist * f;
        k.b.vx -= dx / dist * f; k.b.vy -= dy / dist * f;
      }
      for (i = 0; i < nodes.length; i++) {
        n = nodes[i];
        var g = attract[n.group];
        if (g) { n.vx += (g.x - n.x) * 0.004; n.vy += (g.y - n.y) * 0.004; }
        n.vx += -n.x * 0.002; n.vy += -n.y * 0.002;
        n.vx *= 0.72; n.vy *= 0.72;
        if (drag !== n) { n.x += n.vx; n.y += n.vy; }
      }
    }

    function draw() {
      var ctx = canvas.getContext('2d');
      var dpr = window.devicePixelRatio || 1;
      var w = canvas.width, h = canvas.height;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      var cssW = w / dpr, cssH = h / dpr;
      ctx.fillStyle = '#0b0f14';
      ctx.fillRect(0, 0, cssW, cssH);
      ctx.save();
      ctx.translate(cssW / 2, cssH / 2);
      ctx.strokeStyle = 'rgba(148,163,184,0.22)';
      ctx.lineWidth = 0.8;
      var i;
      for (i = 0; i < links.length; i++) {
        ctx.beginPath();
        ctx.moveTo(links[i].a.x, links[i].a.y);
        ctx.lineTo(links[i].b.x, links[i].b.y);
        ctx.stroke();
      }
      for (i = 0; i < nodes.length; i++) {
        var n = nodes[i];
        var r = 2.4 + Math.sqrt(n.size) * 1.6;
        ctx.beginPath();
        ctx.fillStyle = GROUP_COLOR[n.group] || '#94a3b8';
        ctx.globalAlpha = n === hover || n === drag ? 1 : 0.92;
        ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
        ctx.fill();
        if (n.size >= 4 || n === hover) {
          ctx.fillStyle = '#e5e7eb';
          ctx.globalAlpha = 0.9;
          ctx.font = '11px sans-serif';
          ctx.fillText(n.label, n.x + r + 3, n.y + 3);
        }
        ctx.globalAlpha = 1;
      }
      ctx.restore();
    }

    function loop() {
      var s;
      for (s = 0; s < 2; s++) step();
      draw();
      raf = requestAnimationFrame(loop);
    }
    loop();

    function pick(ev) {
      var rect = canvas.getBoundingClientRect();
      var x = ev.clientX - rect.left - rect.width / 2;
      var y = ev.clientY - rect.top - rect.height / 2;
      var best = null, bestD = 14, i, n, d;
      for (i = 0; i < nodes.length; i++) {
        n = nodes[i];
        d = Math.hypot(n.x - x, n.y - y);
        if (d < bestD) { bestD = d; best = n; }
      }
      return best;
    }
    canvas.addEventListener('mousemove', function (ev) {
      hover = pick(ev);
      tip.style.display = hover ? 'block' : 'none';
      if (hover) {
        tip.textContent = hover.label + '  ·  ' + hover.group + '  ·  deg ' + hover.size;
        tip.style.left = (ev.clientX - canvas.getBoundingClientRect().left + 12) + 'px';
        tip.style.top = (ev.clientY - canvas.getBoundingClientRect().top + 12) + 'px';
      }
      if (drag) {
        var rect = canvas.getBoundingClientRect();
        drag.x = ev.clientX - rect.left - rect.width / 2;
        drag.y = ev.clientY - rect.top - rect.height / 2;
        drag.vx = 0; drag.vy = 0;
      }
    });
    canvas.addEventListener('mousedown', function (ev) { drag = pick(ev); });
    window.addEventListener('mouseup', function () { drag = null; });
    return box;
  }

  function render(root) {
    var d = payload();
    root.textContent = '';
    root.appendChild(h('h1', { text: d.title || d.artifact_id }));
    root.appendChild(h('div', { class: 'ha-sub', text: 'Generated '
      + d.generated_at + (d.source && d.source.note ? ' - ' + d.source.note : '') }));
    if ((d.summary || []).length) root.appendChild(renderCards(d));
    if (d.graph && (d.graph.nodes || []).length) root.appendChild(renderGraph(d.graph));
    (d.charts || []).forEach(function (c) { root.appendChild(renderChart(c)); });
    (d.tables || []).forEach(function (t) { root.appendChild(renderTable(t)); });
    if ((d.notes || []).length) {
      var ul = h('ul', { class: 'ha-notes' });
      d.notes.forEach(function (n) { ul.appendChild(h('li', { text: n })); });
      root.appendChild(ul);
    }
  }

  window.HermesArtifact = { render: render };
  document.addEventListener('DOMContentLoaded', function () {
    render(document.getElementById('app'));
  });
})();
