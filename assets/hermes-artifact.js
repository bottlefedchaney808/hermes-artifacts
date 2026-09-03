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

  function render(root) {
    var d = payload();
    root.textContent = '';
    root.appendChild(h('h1', { text: d.title || d.artifact_id }));
    root.appendChild(h('div', { class: 'ha-sub', text: 'Generated '
      + d.generated_at + (d.source && d.source.note ? ' - ' + d.source.note : '') }));
    if ((d.summary || []).length) root.appendChild(renderCards(d));
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
