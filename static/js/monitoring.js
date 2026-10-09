/* Network monitor + system health. All numbers come from /api/admin/* (real server state). */
(function () {
  'use strict';
  const { $, esc } = NV;
  const tile = (k, v, s, kind) => `<div class="card metric ${kind || ''}"><div class="k">${esc(k)}</div><div class="v" style="font-size:1.35rem">${v}</div><div class="s">${s || ''}</div></div>`;
  const cell = (k, v) => `<div class="cell"><div class="k">${esc(k)}</div><div class="v">${v}</div></div>`;

  NV.pages['network-monitor'] = async () => {
    const delaySeg = NV.seg('#delay-seg'), toSeg = NV.seg('#to-seg');
    let ch = {};
    const refresh = async () => {
      const r = (await NV.api.get('/api/admin/network')).data, N = r.snapshot, S = r.series, C = r.concurrency, RL = r.rate_limit;
      $('#srv-status').innerHTML = `<span class="badge b-green"><span class="dot green"></span> ONLINE</span>`;
      $('#net-tiles').innerHTML =
        tile('Server status', '<span class="dot green"></span> ' + N.status, 'up ' + N.uptime_s + ' s', 'ok') + tile('Host', esc(N.host), '', 'info') + tile('Port', N.port, '', 'info') + tile('Protocol', esc(N.protocol), '', 'info') +
        tile('Active connections', N.active_connections, `peak ${N.peak_connections}, in-flight requests`, 'info') + tile('Requests / second', N.requests_per_second, 'last 10 s', 'info') +
        tile('Successful requests', NV.int(N.successful), 'status below 400', 'ok') + tile('Failed requests', NV.int(N.failed), `${N.server_errors} server errors (5xx)`, N.failed ? 'warn' : 'ok') +
        tile('Timeouts', N.timeouts, 'from the network lab', N.timeouts ? 'warn' : 'ok') + tile('Average response', N.avg_ms + ' ms', '', 'info') +
        tile('Fastest / slowest', `${N.fastest_ms} / ${N.slowest_ms} ms`, '', 'info') + tile('Error rate', N.error_rate_pct + '%', 'failed / total', N.error_rate_pct > 10 ? 'bad' : N.error_rate_pct > 3 ? 'warn' : 'ok') +
        tile('Network reliability', N.reliability_pct + '%', 'requests without 5xx or timeout', 'ok');
      if (!ch.rps) {
        ch.rps = NV.charts.line('n-rps', S.labels, [{ label: 'req/s', data: S.rps }], { plugins: { legend: { display: false } } });
        ch.ms = NV.charts.line('n-ms', S.labels, [{ label: 'avg ms', data: S.avg_ms }], { plugins: { legend: { display: false } } });
        ch.sf = NV.charts.bar('n-sf', S.labels, [{ label: 'Successful', data: S.ok, backgroundColor: '#0f7a55' }, { label: 'Failed', data: S.err, backgroundColor: '#b6322a' }], { scales: { x: { stacked: true, ticks: { maxTicksLimit: 6 } }, y: { stacked: true, beginAtZero: true, ticks: { precision: 0 } } } });
        ch.codes = NV.charts.bar('n-codes', [], [{ label: 'Responses', data: [] }], { plugins: { legend: { display: false } } });
        ch.conn = NV.charts.line('n-conn', S.labels, [{ label: 'in-flight', data: S.inflight, stepped: true }], { plugins: { legend: { display: false } } });
        ch.err = NV.charts.line('n-err', S.labels, [{ label: 'error %', data: S.error_rate, borderColor: '#b6322a' }], { plugins: { legend: { display: false } } });
      }
      NV.charts.set(ch.rps, S.labels, [S.rps]); NV.charts.set(ch.ms, S.labels, [S.avg_ms]); NV.charts.set(ch.sf, S.labels, [S.ok, S.err]);
      NV.charts.set(ch.conn, S.labels, [S.inflight]); NV.charts.set(ch.err, S.labels, [S.error_rate]);
      const codes = Object.keys(N.status_codes); ch.codes.data.datasets[0].backgroundColor = codes.map((c) => (+c < 300 ? '#0f7a55' : +c < 400 ? '#2456e6' : +c < 500 ? '#b7791f' : '#b6322a'));
      NV.charts.set(ch.codes, codes, [codes.map((c) => N.status_codes[c])]);
      $('#perf').innerHTML = cell('P50 latency', N.p50_ms + ' ms') + cell('P95 latency', N.p95_ms + ' ms') + cell('P99 latency', N.p99_ms + ' ms') + cell('Active threads', C.active_threads) + cell('Completed tasks', NV.int(C.worker_pool.completed)) +
        cell('Rate-limit events', RL.sensitive.blocked + RL.general.blocked) + cell('Sensitive window', `${RL.sensitive.current_window_requests}/${RL.sensitive.limit}`) + cell('Blocked (429)', N.rate_limited);
      $('#recent').innerHTML = N.recent.length ? N.recent.map((x) => `<tr><td class="small">${x.time}</td><td class="small">${esc(x.method)} ${esc(x.path)}</td><td>${NV.badge(x.status, x.status < 400 ? 'green' : x.status < 500 ? 'amber' : 'red')}</td><td>${x.ms}</td><td class="rid">${esc(x.request_id)}</td></tr>`).join('') : '<tr><td colspan="5" class="empty">No requests yet.</td></tr>';
    };
    const run = async (burst) => {
      const out = $('#net-out'); out.innerHTML = '<span class="spinner"></span> running real HTTP requests...';
      $('#run-net').disabled = $('#run-burst').disabled = true;
      try {
        const r = (await NV.api.post('/api/admin/network-test', { delay_ms: +delaySeg.get(), timeout_ms: +toSeg.get(), burst }, { timeout: 30000 })).data.result;
        const kind = { OK: 'green', DELAYED: 'amber', TIMEOUT: 'red', ERROR: 'red' };
        out.innerHTML = `<div class="result-grid">${cell('Normal request', r.normal.ms + ' ms')}${cell('Simulated request', r.simulated.ms + ' ms')}${cell('Server delay', r.delay_ms + ' ms')}${cell('Client timeout', r.timeout_ms + ' ms')}</div>
          <p style="margin-top:.8rem">Status: ${NV.badge(r.simulated.status, kind[r.simulated.status])} <strong>${esc(r.verdict)}</strong></p><p class="small">Request ID: <span class="rid">${esc(r.simulated.request_id)}</span></p>
          ${r.burst ? `<div class="notice n-info small">Burst: ${r.burst.requests} concurrent requests via ${r.burst.workers} workers, ${r.burst.ok} OK, average ${r.burst.avg_ms} ms, max ${r.burst.max_ms} ms. Watch the charts above react.</div>` : ''}<p class="hint">${esc(r.label)}</p>`;
      } catch (e) { out.innerHTML = ''; NV.showError(e); }
      $('#run-net').disabled = $('#run-burst').disabled = false; refresh();
    };
    $('#run-net').addEventListener('click', () => run(0)); $('#run-burst').addEventListener('click', () => run(100));
    await refresh(); NV.poll(refresh, 2000);
  };

  NV.pages['system-health'] = async () => {
    const hist = { cpu: [], mem: [], thr: [], t: [] }; let ch = {};
    const refresh = async () => {
      const h = (await NV.api.get('/api/admin/system-health')).data, S = h.system;
      $('#overall').innerHTML = `<span class="badge b-${h.overall === 'healthy' ? 'green' : h.overall === 'warning' ? 'amber' : 'red'}">${NV.dot(h.overall)} ${h.overall.toUpperCase()}</span>`;
      const lbl = { healthy: 'Healthy', warning: 'Warning', critical: 'Critical' };
      $('#comps').innerHTML = h.components.map((c) => `<div class="comp">${NV.dot(c.state)}<span class="n">${esc(c.name)}</span><span class="badge b-${c.state === 'healthy' ? 'green' : c.state === 'warning' ? 'amber' : 'red'}">${lbl[c.state]}</span><span class="note">${esc(c.note)}</span></div>`).join('');
      const up = S.uptime_s >= 3600 ? Math.floor(S.uptime_s / 3600) + ' h ' + Math.floor((S.uptime_s % 3600) / 60) + ' m' : Math.floor(S.uptime_s / 60) + ' m ' + (S.uptime_s % 60) + ' s';
      $('#sys').innerHTML = cell('CPU (process)', S.cpu_pct === null ? 'n/a' : S.cpu_pct + '%') + cell('Memory', S.memory_mb === null ? 'n/a' : S.memory_mb + ' MB') + cell('Uptime', up) + cell('Database size', S.db_size_kb + ' KB') + cell('Active threads', S.active_threads) + cell('Request queue', S.request_queue);
      $('#lasts').innerHTML = `<dl class="kv"><dt>Last error</dt><dd>${h.last_error ? esc(h.last_error.event_type + ': ' + h.last_error.message) + ' <span class="muted small">(' + esc(NV.time(h.last_error.timestamp)) + ')</span>' : 'none recorded'}</dd><dt>Last successful vote</dt><dd>${h.last_successful_vote ? esc(h.last_successful_vote.transaction_id) + ' <span class="muted small">(' + esc(NV.time(h.last_successful_vote.timestamp)) + ')</span>' : 'none yet'}</dd></dl>${h.psutil_available ? '' : '<p class="hint">Install psutil to see CPU and memory.</p>'}`;
      hist.t.push(new Date().toLocaleTimeString()); hist.cpu.push(S.cpu_pct || 0); hist.mem.push(S.memory_mb || 0); hist.thr.push(S.active_threads);
      Object.keys(hist).forEach((k) => hist[k].length > 40 && hist[k].shift());
      if (!ch.cpu) { ch.cpu = NV.charts.line('h-cpu', hist.t, [{ label: 'CPU %', data: hist.cpu }], { plugins: { legend: { display: false } } }); ch.mem = NV.charts.line('h-mem', hist.t, [{ label: 'MB', data: hist.mem, borderColor: '#7a4fd1' }], { plugins: { legend: { display: false } } }); ch.thr = NV.charts.line('h-thr', hist.t, [{ label: 'threads', data: hist.thr, borderColor: '#0f7a55', stepped: true }], { plugins: { legend: { display: false } } }); }
      NV.charts.set(ch.cpu, hist.t, [hist.cpu]); NV.charts.set(ch.mem, hist.t, [hist.mem]); NV.charts.set(ch.thr, hist.t, [hist.thr]);
    };
    $('#verify-btn').addEventListener('click', async () => {
      const r = (await NV.api.get('/api/admin/ledger-verify')).data.ledger;
      $('#verify-out').innerHTML = r.valid ? `<div class="notice n-ok"><strong>Ledger valid.</strong> ${r.votes_checked} votes re-hashed, chain intact, tallies match. Head <span class="rid">${esc(r.head || '-')}</span></div>` : `<div class="notice n-bad"><strong>Problems:</strong><ul>${r.problems.map((p) => `<li>${esc(p)}</li>`).join('')}</ul></div>`;
    });
    await refresh(); NV.poll(refresh, 3000);
  };
})();
