/* Chart.js helpers (Chart.js is vendored in static/vendor, so the app works offline). */
(function () {
  'use strict';
  const C = (NV.charts = {});
  const PALETTE = ['#2456e6', '#0f7a55', '#c0562c', '#7a4fd1', '#b7791f', '#b6322a', '#0e8fa8'];
  C.palette = PALETTE;
  if (window.Chart) {
    Chart.defaults.font.family = '"Plex", system-ui, sans-serif';
    Chart.defaults.font.size = 12;
    Chart.defaults.color = '#5a6a85';
    Chart.defaults.animation.duration = 250;
  }
  const base = (extra) => Object.assign({ responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false }, plugins: { legend: { labels: { boxWidth: 10, usePointStyle: true } } } }, extra);
  C.make = (id, type, labels, datasets, opts) => {
    const el = document.getElementById(id);
    return new Chart(el.getContext('2d'), { type, data: { labels, datasets }, options: base(opts) });
  };
  C.line = (id, labels, datasets, opts) => C.make(id, 'line', labels, datasets.map((d, i) => Object.assign({ borderColor: PALETTE[i], backgroundColor: PALETTE[i] + '22', borderWidth: 2, pointRadius: 0, tension: .3, fill: false }, d)), Object.assign({ scales: { x: { ticks: { maxTicksLimit: 6 }, grid: { display: false } }, y: { beginAtZero: true } } }, opts));
  C.bar = (id, labels, datasets, opts) => C.make(id, 'bar', labels, datasets.map((d, i) => Object.assign({ backgroundColor: PALETTE[i], borderRadius: 4 }, d)), Object.assign({ scales: { y: { beginAtZero: true, ticks: { precision: 0 } }, x: { grid: { display: false } } } }, opts));
  C.doughnut = (id, labels, data, colors) => C.make(id, 'doughnut', labels, [{ data, backgroundColor: colors || PALETTE, borderWidth: 2, borderColor: '#fff' }], { cutout: '62%', plugins: { legend: { position: 'bottom', labels: { boxWidth: 10, usePointStyle: true } } } });
  C.set = (chart, labels, datasetsData) => {
    if (labels) chart.data.labels = labels;
    datasetsData.forEach((d, i) => { chart.data.datasets[i].data = d; });
    chart.update('none');
  };
})();
