/* Admin pages: dashboard, election, voters, candidates, audit logs, settings. */
(function () {
  'use strict';
  const { $, $$, esc } = NV;
  const tile = (k, v, s, kind) => `<div class="card metric ${kind || ''}"><div class="k">${esc(k)}</div><div class="v">${v}</div><div class="s">${s || ''}</div></div>`;
  const cell = (k, v) => `<div class="cell"><div class="k">${esc(k)}</div><div class="v">${v}</div></div>`;
  const sevBadge = (s) => NV.badge(s, s === 'ERROR' || s === 'CRITICAL' ? 'red' : s === 'WARNING' ? 'amber' : 'blue');

  /* ------------------------------------------------------------ dashboard */
  NV.pages['admin-dashboard'] = async () => {
    let resChart = null, resType = 'bar', statusChart, latChart, lastCands = [];
    const buildRes = (c) => {
      if (resChart) resChart.destroy();
      resChart = resType === 'bar'
        ? NV.charts.bar('c-results', c.map((x) => x.name), [{ label: 'Votes', data: c.map((x) => x.vote_count), backgroundColor: c.map((x) => x.color) }], { plugins: { legend: { display: false } } })
        : NV.charts.doughnut('c-results', c.map((x) => x.name), c.map((x) => x.vote_count), c.map((x) => x.color));
    };
    $$('#res-toggle button').forEach((b) => b.addEventListener('click', () => { $$('#res-toggle button').forEach((x) => x.setAttribute('aria-pressed', x === b)); resType = b.dataset.t; buildRes(lastCands); }));
    const refresh = async () => {
      const [d, n] = await Promise.all([NV.api.get('/api/admin/dashboard'), NV.api.get('/api/admin/network')]);
      const D = d.data, N = D.network, el = D.election, S = n.data.series;
      $('#dash-status').innerHTML = NV.statusBadge(el.status) + ` <span class="small muted">${esc(el.election_name)}</span> <a class="btn btn-sm" href="election.html">Manage</a>`;
      $('#tiles').innerHTML =
        tile('Registered voters', NV.int(el.total_registered), '', 'info') + tile('Votes cast', NV.int(el.total_votes), 'recorded in ledger', 'ok') +
        tile('Turnout', el.turnout_pct + '%', `${el.total_votes} / ${el.total_registered}`, 'ok') + tile('Active connections', N.active_connections, `peak ${N.peak_connections} (in-flight requests)`, 'info') +
        tile('Requests / sec', N.requests_per_second, 'last 10 s', 'info') + tile('Error rate', N.error_rate_pct + '%', `${N.failed} of ${N.total_requests} requests`, N.error_rate_pct > 10 ? 'bad' : N.error_rate_pct > 3 ? 'warn' : 'ok') +
        tile('Avg response time', N.avg_ms + ' ms', `p95 ${N.p95_ms} ms`, 'info') + tile('System health', NV.dot(D.health) + ' ' + D.health.toUpperCase(), '<a href="system-health.html">details</a>', D.health === 'healthy' ? 'ok' : D.health === 'warning' ? 'warn' : 'bad');
      const sig = JSON.stringify(D.candidates.map((c) => c.name));
      if (!resChart || sig !== JSON.stringify(lastCands.map((c) => c.name))) { lastCands = D.candidates; buildRes(lastCands); }
      lastCands = D.candidates;
      NV.charts.set(resChart, D.candidates.map((c) => c.name), [D.candidates.map((c) => c.vote_count)]);
      if (!latChart) latChart = NV.charts.line('c-latency', S.labels, [{ label: 'Avg ms', data: S.avg_ms }]);
      NV.charts.set(latChart, S.labels, [S.avg_ms]);
      if (!statusChart) statusChart = NV.charts.bar('c-status', ['Successful', 'Failed', 'Timeout', 'Rate limited'], [{ label: 'Requests', data: [], backgroundColor: ['#0f7a55', '#b6322a', '#b7791f', '#7a4fd1'] }], { plugins: { legend: { display: false } } });
      NV.charts.set(statusChart, null, [[N.successful, N.failed, N.timeouts, N.rate_limited]]);
      const C = D.concurrency, L = C.lock;
      $('#conc').innerHTML = cell('Threads', C.active_threads) + cell('Active workers', C.worker_pool.active_workers) + cell('Queued requests', C.queued_requests) + cell('Locks acquired', NV.int(L.acquisitions)) + cell('Lock contention', L.contention_pct + '%') + cell('Waiting on lock', L.waiting_now);
      const R = D.rate_limit;
      $('#rl').innerHTML = cell('Rate-limit events', R.sensitive.blocked + R.general.blocked) + cell('Current request rate', N.requests_per_second + '/s') + cell('Blocked requests', N.rate_limited) + cell('Sensitive limit', R.sensitive.limit + '/' + R.sensitive.window_s + 's');
      $('#events').innerHTML = D.events.length ? D.events.map((e) => `<tr><td class="small">${esc(NV.time(e.timestamp))}</td><td>${esc(e.event_type)}</td><td>${sevBadge(e.severity)}</td><td>${esc(e.message)}</td></tr>`).join('') : '<tr><td colspan="4" class="empty">No system events recorded. Everything is quiet.</td></tr>';
      const lg = D.ledger;
      $('#ledger').innerHTML = lg.valid ? `<div class="notice n-ok"><strong>Ledger consistent.</strong> ${lg.votes_checked} votes verified; hash chain intact; tallies match. Head: <span class="rid">${esc(lg.head || '-')}</span></div>` : `<div class="notice n-bad"><strong>Ledger problems detected:</strong><ul>${lg.problems.map((p) => `<li>${esc(p)}</li>`).join('')}</ul></div>`;
    };
    await refresh(); NV.poll(refresh, 3000);
  };

  /* ------------------------------------------------------------ election */
  NV.pages.election = async () => {
    const act = async (action, title, html, label, danger) => {
      if (title && !(await NV.confirm(title, html, label, danger))) return;
      try { const r = await NV.api.post('/api/admin/election/' + action); NV.toast(r.data.message, 'success', r.requestId); await load(); } catch (e) { NV.showError(e); }
    };
    const load = async () => {
      const el = (await NV.api.get('/api/election')).data.election;
      $('#el-state').innerHTML = `<h2>${esc(el.election_name)}</h2><p>${NV.statusBadge(el.status)}</p><dl class="kv"><dt>Started</dt><dd>${esc(NV.time(el.start_time))}</dd><dt>Ended</dt><dd>${esc(NV.time(el.end_time))}</dd><dt>Votes</dt><dd>${el.total_votes} of ${el.total_registered} registered (${el.turnout_pct}%)</dd></dl>`;
      const box = $('#el-actions'); box.innerHTML = '';
      const add = (label, cls, fn) => { const b = document.createElement('button'); b.className = 'btn ' + cls; b.textContent = label; b.addEventListener('click', fn); box.appendChild(b); };
      if (el.status === 'NOT_STARTED') add('Start election', 'btn-primary', () => act('start', 'Start election?', '<p>Voters will be able to cast ballots immediately.</p>', 'Start'));
      if (el.status === 'ACTIVE') add('Pause', '', () => act('pause', 'Pause election?', '<p>Voting is suspended until you resume.</p>', 'Pause'));
      if (el.status === 'PAUSED') add('Resume', 'btn-primary', () => act('resume'));
      if (el.status === 'ACTIVE' || el.status === 'PAUSED') add('End election', 'btn-danger', () => act('end', 'END ELECTION?', '<p><strong>This action cannot be undone.</strong> Results will be published.</p>', 'CONFIRM END ELECTION', true));
      if (el.status === 'ENDED') box.innerHTML = '<span class="muted small">The election has ended. Create a new election to start again.</span>';
    };
    $('#create-form').addEventListener('submit', async (ev) => {
      ev.preventDefault();
      const name = $('#el-name').value.trim(); if (name.length < 3) { NV.toast('Enter an election name (3+ characters).', 'warning'); return; }
      if (!(await NV.confirm('Create new election?', '<p>This <strong>resets every ballot and voter status</strong>. It cannot be undone.</p>', 'Create and reset', true))) return;
      try { const r = await NV.api.post('/api/admin/election/create', { election_name: name }); NV.toast('Election created (not started).', 'success', r.requestId); $('#el-name').value = ''; await load(); } catch (e) { NV.showError(e); }
    });
    await load();
  };

  /* ------------------------------------------------------------ voters */
  NV.pages.voters = async () => {
    const load = async () => {
      const r = (await NV.api.get('/api/admin/voters?limit=200&q=' + encodeURIComponent($('#q').value.trim()))).data;
      $('#vbody').innerHTML = r.voters.length ? r.voters.map((v) => `<tr><td class="rid">${esc(v.voter_id)}</td><td>${esc(v.name)}</td><td>${esc(v.email)}</td><td>${v.has_voted ? NV.badge('Voted', 'green') : NV.badge('Not voted', 'amber')}</td><td>${NV.badge(v.status, v.status === 'active' ? 'green' : 'red')}</td><td class="small">${esc(NV.time(v.last_login))}</td>
        <td class="right"><button class="btn btn-sm" data-id="${esc(v.voter_id)}" data-to="${v.status === 'active' ? 'suspended' : 'active'}">${v.status === 'active' ? 'Suspend' : 'Activate'}</button></td></tr>`).join('') : '<tr><td colspan="7" class="empty">No voters match your search.</td></tr>';
      $('#vcount').textContent = `${r.voters.length} of ${r.total} voters shown`;
      $$('#vbody button').forEach((b) => b.addEventListener('click', async () => {
        if (b.dataset.to === 'suspended' && !(await NV.confirm('Suspend voter ' + b.dataset.id + '?', '<p>They will not be able to log in or vote.</p>', 'Suspend', true))) return;
        try { const x = await NV.api.put('/api/admin/voters/' + encodeURIComponent(b.dataset.id) + '/status', { status: b.dataset.to }); NV.toast(x.data.message, 'success', x.requestId); load(); } catch (e) { NV.showError(e); }
      }));
    };
    $('#vsearch').addEventListener('submit', (e) => { e.preventDefault(); load(); });
    await load();
  };

  /* ------------------------------------------------------------ candidates */
  NV.pages.candidates = async () => {
    let editing = null, locked = false;
    const card = $('#cand-form-card');
    const openForm = (c) => { editing = c; card.classList.remove('hidden'); $('#cf-title').textContent = c ? 'Edit candidate' : 'Add candidate'; $('#cf-name').value = c ? c.name : ''; $('#cf-party').value = c ? c.party : ''; $('#cf-symbol').value = c ? c.symbol : '*'; $('#cf-color').value = c ? c.color : '#2456e6'; $('#cf-desc').value = c ? c.description : ''; $('#cf-err').textContent = ''; $('#cf-name').focus(); };
    const load = async () => {
      const r = (await NV.api.get('/api/admin/candidates')).data; locked = r.locked;
      $('#lock-note').innerHTML = locked ? '<div class="notice n-warn" style="margin-bottom:1rem">An election is running, so candidates cannot be added or removed, and name/party are frozen. Description, symbol and colour can still be edited.</div>' : '';
      $('#add-btn').disabled = locked; $('#add-btn').title = locked ? 'Locked while an election is running' : '';
      $('#cbody').innerHTML = r.candidates.length ? r.candidates.map((c) => `<tr><td><span style="display:inline-grid;place-items:center;width:34px;height:34px;border-radius:8px;background:${esc(c.color)};color:#fff">${esc(c.symbol)}</span></td><td><strong>${esc(c.name)}</strong></td><td>${esc(c.party)}</td><td class="small muted">${esc(c.description)}</td><td>${c.vote_count}</td>
        <td class="right"><button class="btn btn-sm" data-e="${c.id}">Edit</button> <button class="btn btn-sm btn-danger" data-d="${c.id}" ${locked || c.vote_count ? 'disabled title="Not allowed while running or when votes exist"' : ''}>Delete</button></td></tr>`).join('') : '<tr><td colspan="6" class="empty">No candidates yet.</td></tr>';
      $$('#cbody [data-e]').forEach((b) => b.addEventListener('click', () => openForm(r.candidates.find((c) => c.id === +b.dataset.e))));
      $$('#cbody [data-d]').forEach((b) => b.addEventListener('click', async () => {
        if (!(await NV.confirm('Delete candidate?', '<p>This cannot be undone.</p>', 'Delete', true))) return;
        try { const x = await NV.api.del('/api/admin/candidates/' + b.dataset.d); NV.toast(x.data.message, 'success', x.requestId); load(); } catch (e) { NV.showError(e); }
      }));
    };
    $('#add-btn').addEventListener('click', () => openForm(null));
    $('#cf-cancel').addEventListener('click', () => card.classList.add('hidden'));
    $('#cand-form').addEventListener('submit', async (ev) => {
      ev.preventDefault();
      const body = { name: $('#cf-name').value, party: $('#cf-party').value, symbol: $('#cf-symbol').value || '*', color: $('#cf-color').value, description: $('#cf-desc').value };
      try { const x = editing ? await NV.api.put('/api/admin/candidates/' + editing.id, body) : await NV.api.post('/api/admin/candidates', body); NV.toast(editing ? 'Candidate updated.' : 'Candidate created.', 'success', x.requestId); card.classList.add('hidden'); load(); }
      catch (e) { $('#cf-err').textContent = e.message + (e.requestId ? ' (Request ID: ' + e.requestId + ')' : ''); }
    });
    await load();
  };

  /* ------------------------------------------------------------ audit logs */
  NV.pages['audit-logs'] = async () => {
    let offset = 0; const limit = 50; let total = 0; let actionsLoaded = false;
    const statusKind = (s) => (s === 'OK' ? 'green' : s === 'REJECTED' || s === 'DENIED' || s === 'BLOCKED' || s === 'TIMEOUT' ? 'amber' : 'blue');
    const load = async () => {
      const q = new URLSearchParams({ limit, offset, action: $('#f-action').value, user: $('#f-user').value.trim(), severity: $('#f-sev').value, date_from: $('#f-from').value, date_to: $('#f-to').value });
      const r = (await NV.api.get('/api/admin/audit-logs?' + q.toString())).data; total = r.total;
      if (!actionsLoaded) { actionsLoaded = true; $('#f-action').innerHTML = '<option value="">All</option>' + r.actions.map((a) => `<option>${esc(a)}</option>`).join(''); }
      $('#abody').innerHTML = r.logs.length ? r.logs.map((l) => `<tr><td class="small" style="white-space:nowrap">${esc(NV.time(l.timestamp))}</td><td class="rid">${esc(l.user_id || '-')}</td><td><strong>${esc(l.action)}</strong> ${l.severity !== 'INFO' ? sevBadge(l.severity) : ''}</td><td class="rid">${esc(l.request_id || '-')}</td><td class="small">${esc(l.ip_address || '-')}</td><td>${NV.badge(l.status, statusKind(l.status))}</td><td class="small">${esc(l.details || '')}</td></tr>`).join('') : '<tr><td colspan="7" class="empty">No audit entries match these filters.</td></tr>';
      $('#acount').textContent = total ? `${offset + 1}-${Math.min(offset + limit, total)} of ${total}` : '0 entries';
      $('#prev').disabled = offset === 0; $('#next').disabled = offset + limit >= total;
    };
    $('#filters').addEventListener('submit', (e) => { e.preventDefault(); offset = 0; load(); });
    $('#f-reset').addEventListener('click', () => { $('#filters').reset(); offset = 0; load(); });
    $('#refresh').addEventListener('click', load);
    $('#prev').addEventListener('click', () => { offset = Math.max(0, offset - limit); load(); });
    $('#next').addEventListener('click', () => { offset += limit; load(); });
    await load();
  };

  /* ------------------------------------------------------------ settings */
  NV.pages.settings = async () => {
    const s = (await NV.api.get('/api/admin/settings')).data.settings;
    const labels = { host: 'Host', port: 'Port', debug: 'Debug', rate_limit_sensitive: 'Rate limit (login/register/vote)', rate_limit_general: 'Rate limit (other API)', password_hashing: 'Password hashing', session_minutes: 'Session lifetime (min)', lock_timeout_s: 'Vote lock timeout (s)', database: 'Database file' };
    $('#cfg').innerHTML = Object.keys(labels).map((k) => `<dt>${labels[k]}</dt><dd>${esc(s[k])}</dd>`).join('');
    $('#pw-form').addEventListener('submit', async (ev) => {
      ev.preventDefault(); $('#pw-err').textContent = '';
      try { const r = await NV.api.post('/api/admin/change-password', { current_password: $('#cur').value, new_password: $('#new').value }); NV.toast('Password changed.', 'success', r.requestId); $('#pw-form').reset(); }
      catch (e) { $('#pw-err').textContent = e.message; }
    });
  };
})();
