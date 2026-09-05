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

  /* Jarvis brain — cinematic force graph of the vault. Canvas renderer with
     d3-force physics (when reachable), manual zoom/pan transform state, hover
     neighborhood isolation, and click-to-open in Obsidian. Falls back to a
     compact hand-rolled sim when the d3 CDN is unreachable. ES5 on purpose:
     this file ships inline into single-file artifacts with no build step. */

  var OBSIDIAN_VAULT = 'obsidian-vault';

  function renderGraph(graph) {
    if (!graph || !(graph.nodes && graph.nodes.length)) return;

    // ---- Init: degree map, adjacency (neighborhood sets), top-label set ----
    var rawNodes = graph.nodes, rawEdges = graph.edges || [];
    var deg = {}, adj = {};
    var i, n, e;
    for (i = 0; i < rawNodes.length; i++) {
      n = rawNodes[i];
      if (!deg[n.id]) deg[n.id] = 0;
      if (!adj[n.id]) adj[n.id] = {};
      adj[n.id][n.id] = true; // self, so the hovered node stays lit
    }
    for (i = 0; i < rawEdges.length; i++) {
      e = rawEdges[i];
      var a = e.source, b = e.target;
      if (!deg[a]) deg[a] = 0;
      if (!deg[b]) deg[b] = 0;
      deg[a]++; deg[b]++;
      (adj[a] || (adj[a] = {}))[b] = true;
      (adj[b] || (adj[b] = {}))[a] = true;
    }
    var topLabelSet = {};
    rawNodes.slice().sort(function (x, y) { return deg[y.id] - deg[x.id]; })
      .slice(0, 8).forEach(function (nd) { topLabelSet[nd.id] = true; });

    // Group attractor points: each distinct group gets an angle on a ~260 circle.
    var groups = [];
    rawNodes.forEach(function (nd) { if (groups.indexOf(nd.group || 'hub') === -1) groups.push(nd.group || 'hub'); });
    var attract = {};
    for (i = 0; i < groups.length; i++) {
      var ang = (i / Math.max(1, groups.length)) * Math.PI * 2;
      attract[groups[i]] = { x: Math.cos(ang) * 260, y: Math.sin(ang) * 260 };
    }

    // Sim node objects. Seed positions near the group attractor for fast convergence.
    var nodes = rawNodes.map(function (nd, idx) {
      var g = nd.group || 'hub';
      var at = attract[g] || { x: 0, y: 0 };
      return {
        id: nd.id, label: nd.label != null ? nd.label : String(nd.id), group: g,
        size: Math.max(1, nd.size || 1),
        x: at.x + (Math.random() - 0.5) * 60, y: at.y + (Math.random() - 0.5) * 60,
        vx: 0, vy: 0
      };
    });
    var byId = {};
    nodes.forEach(function (nd) { byId[nd.id] = nd; });
    // Links reference node objects directly so d3.forceLink can bind them.
    var links = [];
    for (i = 0; i < rawEdges.length; i++) {
      e = rawEdges[i];
      if (byId[e.source] && byId[e.target]) links.push({ source: byId[e.source], target: byId[e.target] });
    }

    function radius(nd) { return 3 + Math.sqrt(nd.size) * 1.8; }
    var hasD3 = typeof d3 !== 'undefined' && !!d3.forceSimulation;

    // ---- DOM scaffold (canvas, not SVG — spec §2) ----
    var box = h('div', { class: 'ha-graph' }, h('h3', { text: 'Graph view' }));
    var legend = h('div', { class: 'ha-glegend' });
    groups.forEach(function (g) {
      legend.appendChild(h('span', { class: 'swatch' },
        h('i', { style: 'background:' + (GROUP_COLOR[g] || '#94a3b8') }),
        h('span', { text: g })));
    });
    box.appendChild(legend);
    var stage = h('div', { class: 'ha-gstage' });
    var canvas = document.createElement('canvas');
    var tip = h('div', { class: 'ha-gtip', text: '' });
    var toast = h('div', { class: 'ha-ghost-toast', text: '' });
    stage.appendChild(canvas);
    stage.appendChild(tip);
    stage.appendChild(toast);
    box.appendChild(stage);

    // ---- Zoom/pan transform state (manual, spec §3). screenCSS = world*k + t ----
    var view = { k: 1, tx: 0, ty: 0 };
    function clampK(k) { return Math.max(0.25, Math.min(8, k)); }

    // ---- Canvas sizing (backing store × dpr; CSS height fixed at 560 by .ha-gstage) ----
    var cssW = 960, cssH = 560, dpr = window.devicePixelRatio || 1;
    function resize() {
      var r = stage.getBoundingClientRect();
      if (r.width > 2) cssW = Math.round(r.width);
      cssH = 560;
      canvas.style.width = cssW + 'px';
      canvas.style.height = cssH + 'px';
      dpr = window.devicePixelRatio || 1;
      canvas.width = Math.max(1, Math.round(cssW * dpr));
      canvas.height = Math.max(1, Math.round(cssH * dpr));
    }

    var ctx = null; // set after first resize (canvas must be in DOM)

    function showToast(msg) {
      toast.textContent = msg;
      toast.className = 'ha-ghost-toast on';
      clearTimeout(showToast._t);
      showToast._t = setTimeout(function () { toast.className = 'ha-ghost-toast'; }, 2000);
    }

    // ---- Click → open note in Obsidian (spec §5, NO silent file:// fallback) ----
    function openNote(nd) {
      if (!nd || String(nd.id).indexOf('dangling:') === 0) return;
      var uri = 'obsidian://open?vault=' + encodeURIComponent(OBSIDIAN_VAULT) +
        '&file=' + encodeURIComponent(String(nd.id));
      try {
        var a = document.createElement('a');
        a.href = uri;
        document.body.appendChild(a);
        a.click();
        a.remove();
        showToast("Opening '" + nd.label + "' in Obsidian…");
      } catch (err) { /* custom-scheme nav may be blocked by host — toast already names the attempt */ }
    }

    // ---- Pointer state: explicit ownership so zoom/pan/drag don't fight (spec §3) ----
    var hover = null, mode = null; // mode: 'drag' | 'pan' | null
    var dragNode = null, lastX = 0, lastY = 0, downX = 0, downY = 0;

    function pointer(ev) {
      var rect = canvas.getBoundingClientRect();
      return { mx: ev.clientX - rect.left, my: ev.clientY - rect.top };
    }
    // Screen-space hit test (works under any zoom). Returns node or null.
    function pick(mx, my) {
      var best = null, bestD = 1e9;
      for (var j = 0; j < nodes.length; j++) {
        n = nodes[j];
        var sx = n.x * view.k + view.tx, sy = n.y * view.k + view.ty;
        var d = Math.hypot(sx - mx, sy - my);
        if (d < bestD) { bestD = d; best = n; }
      }
      return (best && bestD <= Math.max(10, radius(best) * view.k + 6)) ? best : null;
    }

    // ---- Draw one frame. Shared by the live and fallback paths. ----
    function draw() {
      if (!ctx) ctx = canvas.getContext('2d');
      var W = cssW, H = cssH;
      // (1)-(3): screen-space background — fill, radial vignette, faint dot grid.
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.fillStyle = '#05070c';
      ctx.fillRect(0, 0, W, H);
      var vg = ctx.createRadialGradient(W / 2, H / 2, 0, W / 2, H / 2, Math.max(W, H) * 0.7);
      vg.addColorStop(0, 'rgba(30,41,66,0.55)');
      vg.addColorStop(1, 'rgba(5,7,12,0)');
      ctx.fillStyle = vg;
      ctx.fillRect(0, 0, W, H);
      if (nodes.length <= 1500) {
        ctx.fillStyle = 'rgba(148,163,184,0.05)';
        for (var gx = 20; gx < W; gx += 40) for (var gy = 20; gy < H; gy += 40) { ctx.fillRect(gx, gy, 1, 1); }
      }

      // World pass: apply zoom transform. screenCSS = world*k + t.
      var k = view.k, tx = view.tx, ty = view.ty;
      ctx.setTransform(dpr * k, 0, 0, dpr * k, dpr * tx, dpr * ty);

      // Edges first (spec §2): alpha modulated by hover neighborhood.
      var litSet = hover ? adj[hover.id] : null;
      ctx.lineWidth = 0.8 / k;
      for (var li = 0; li < links.length; li++) {
        e = links[li];
        var touchesHover = hover && (e.source === hover || e.target === hover);
        var alpha = !hover ? 0.10 : (touchesHover ? 0.5 : 0.03);
        ctx.strokeStyle = 'rgba(148,163,184,' + alpha.toFixed(3) + ')';
        ctx.beginPath();
        ctx.moveTo(e.source.x, e.source.y);
        ctx.lineTo(e.target.x, e.target.y);
        ctx.stroke();
      }

      // Nodes: two-pass glow (A) then core fill (B). Dim non-neighbors on hover.
      for (var pass = 0; pass < 2; pass++) {
        for (i = 0; i < nodes.length; i++) {
          n = nodes[i];
          var lit = !hover || (litSet && litSet[n.id]);
          ctx.globalAlpha = lit ? 1 : 0.08;
          if (pass === 0) {
            ctx.shadowBlur = Math.min(40, 12 + n.size);
            ctx.shadowColor = GROUP_COLOR[n.group] || '#94a3b8';
          } else {
            ctx.shadowBlur = 0;
          }
          ctx.fillStyle = GROUP_COLOR[n.group] || '#94a3b8';
          ctx.beginPath();
          ctx.arc(n.x, n.y, radius(n), 0, Math.PI * 2);
          ctx.fill();
        }
      }
      ctx.globalAlpha = 1;

      // Labels in SCREEN space (reset transform) — sparse per spec §2.
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.font = '11px sans-serif';
      for (i = 0; i < nodes.length; i++) {
        n = nodes[i];
        var showLabel = hover ? (!!litSet && litSet[n.id]) : (topLabelSet[n.id] || k > 2);
        if (!showLabel) continue;
        var sx = n.x * k + tx, sy = n.y * k + ty;
        // Cull off-screen when in zoomed label mode.
        if (k > 2 && (sx < -40 || sx > W + 40 || sy < -16 || sy > H + 16)) continue;
        var lit = !hover || (litSet && litSet[n.id]);
        ctx.globalAlpha = lit ? 0.95 : 0.25;
        ctx.fillStyle = '#e5e7eb';
        ctx.fillText(n.label, sx + radius(n) * k + 3, sy + 4);
      }
      ctx.globalAlpha = 1;
    }

    // ---- Fallback: compact hand-rolled sim when d3 is absent (spec §6). ----
    function fallbackStep() {
      var j, m, dx, dy, dist, f;
      for (i = 0; i < nodes.length; i++) {
        n = nodes[i];
        for (j = i + 1; j < nodes.length; j++) {
          m = nodes[j];
          dx = n.x - m.x; dy = n.y - m.y; dist = Math.sqrt(dx * dx + dy * dy) || 0.01;
          f = 420 / (dist * dist);
          n.vx += dx / dist * f; n.vy += dy / dist * f;
          m.vx -= dx / dist * f; m.vy -= dy / dist * f;
        }
      }
      for (i = 0; i < links.length; i++) {
        e = links[i];
        dx = e.target.x - e.source.x; dy = e.target.y - e.source.y; dist = Math.sqrt(dx * dx + dy * dy) || 0.01;
        f = (dist - 46) * 0.012;
        e.source.vx += dx / dist * f; e.source.vy += dy / dist * f;
        e.target.vx -= dx / dist * f; e.target.vy -= dy / dist * f;
      }
      for (i = 0; i < nodes.length; i++) {
        n = nodes[i];
        var g = attract[n.group] || { x: 0, y: 0 };
        n.vx += (g.x - n.x) * 0.004 + (-n.x) * 0.002;
        n.vy += (g.y - n.y) * 0.004 + (-n.y) * 0.002;
        if (dragNode !== n) { n.vx *= 0.72; n.vy *= 0.72; n.x += n.vx; n.y += n.vy; }
      }
    }

    // ---- Wire up events + start the loop once canvas is measurable. ----
    function onWheel(ev) {
      if (!hasD3) return; // fallback path: no zoom (spec §6)
      ev.preventDefault();
      var p = pointer(ev);
      var factor = Math.pow(2, -ev.deltaY * 0.002);
      var newK = clampK(view.k * factor);
      view.tx = p.mx - (p.mx - view.tx) * (newK / view.k);
      view.ty = p.my - (p.my - view.ty) * (newK / view.k);
      view.k = newK;
    }
    function onDown(ev) {
      var p = pointer(ev);
      downX = p.mx; downY = p.my; lastX = p.mx; lastY = p.my;
      dragNode = pick(p.mx, p.my);
      if (dragNode) { mode = 'drag'; if (hasD3) sim.alphaTarget(0.3); } // fallback: reposition only (spec §6)
      else if (!dragNode && hasD3) { mode = 'pan'; }
    }
    function onMove(ev) {
      var p = pointer(ev);
      if (mode === 'drag' && dragNode) {
        dragNode.x = (p.mx - view.tx) / view.k;
        dragNode.y = (p.my - view.ty) / view.k;
        dragNode.vx = 0; dragNode.vy = 0;
      } else if (mode === 'pan') {
        view.tx += p.mx - lastX; view.ty += p.my - lastY;
        lastX = p.mx; lastY = p.my;
      } else {
        hover = pick(p.mx, p.my);
        tip.style.display = hover ? 'block' : 'none';
        if (hover) {
          var unresolved = String(hover.id).indexOf('dangling:') === 0;
          tip.textContent = hover.label + '  ·  ' + hover.group + '  ·  deg ' + deg[hover.id] +
            (unresolved ? '  ·  unresolved link' : '');
          tip.style.left = (p.mx + 12) + 'px';
          tip.style.top = (p.my + 12) + 'px';
        }
      }
    }
    function onUp(ev) {
      var p = pointer(ev);
      if (mode === 'drag') sim.alphaTarget(0);
      // Click = up with negligible movement.
      if (Math.hypot(p.mx - downX, p.my - downY) < 4 && dragNode) {
        openNote(dragNode);
      } else if (String((pick(p.mx, p.my) || {}).id).indexOf('dangling:') === 0) {
        showToast('Unresolved link');
      }
      mode = null; dragNode = null;
    }

    var sim = null;
    function start() {
      resize();
      window.addEventListener('resize', resize);
      if (hasD3) {
        // d3-force physics with the exact verified v7 API surface.
        sim = d3.forceSimulation(nodes)
          .force('link', d3.forceLink(links).id(function (d) { return d.id; })
            .distance(46)
            .strength(function (l) {
              var idOf = function (x) { return typeof x === 'object' ? x.id : x; };
              return 0.5 / Math.max(deg[idOf(l.source)] || 1, deg[idOf(l.target)] || 1);
            }))
          .force('charge', d3.forceManyBody().theta(0.9)
            .strength(function (nd) { return -18 * (1 + Math.sqrt(nd.size) * 0.4); }))
          .force('collide', d3.forceCollide(radius).iterations(2))
          .force('gx', d3.forceX(function (nd) { return (attract[nd.group] || { x: 0 }).x; }).strength(0.03))
          .force('gy', d3.forceY(function (nd) { return (attract[nd.group] || { y: 0 }).y; }).strength(0.03));

        canvas.addEventListener('wheel', onWheel, { passive: false });
      } else {
        // Settle the hand-rolled sim synchronously before first paint.
        for (var t = 0; t < 150; t++) fallbackStep();
      }
      canvas.addEventListener('mousedown', onDown);
      window.addEventListener('mousemove', onMove);
      window.addEventListener('mouseup', onUp);

      function loop() {
        if (!hasD3) fallbackStep(); // keep the static layout gently alive / responsive to drag
        draw();
        requestAnimationFrame(loop);
      }
      loop();
    }

    // Defer start until the stage has a measurable width (it's appended during render()).
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', function () { setTimeout(start, 0); });
    } else {
      setTimeout(start, 0);
    }

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
