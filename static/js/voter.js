/* Public + voter pages: home, login, register, dashboard, voting, receipt, results. */
(function () {
  'use strict';
  const { $, esc } = NV;
  const safeNext = (def) => { const n = new URLSearchParams(location.search).get('next'); return /^[a-z0-9-]+\.html$/.test(n || '') ? n : def; };

  function setBusy(btn, busy, label) { btn.disabled = busy; btn.dataset.l = btn.dataset.l || btn.textContent; btn.innerHTML = busy ? '<span class="spinner"></span> ' + (label || 'Please wait...') : btn.dataset.l; }
  function loginErr(e, box) {
    let msg = e.message;
    if (e.status === 429 && e.extra.retry_after) msg = `Too many requests. Please wait ${e.extra.retry_after} seconds before trying again.`;
    box.innerHTML = esc(msg) + (e.requestId ? ` <span class="rid">(Request ID: ${esc(e.requestId)})</span>` : '');
  }

  NV.pages.index = async () => {
    try {
      const el = (await NV.api.get('/api/election')).data.election;
      $('#h-name').textContent = el.election_name; $('#h-status').innerHTML = NV.statusBadge(el.status);
      $('#h-reg').textContent = NV.int(el.total_registered); $('#h-votes').textContent = NV.int(el.total_votes); $('#h-turn').textContent = el.turnout_pct + '%';
      $('#h-tail').innerHTML = el.ledger_tail.length ? el.ledger_tail.map((r) => `<div class="row"><span>${esc(r.transaction_id)}</span><span>${esc(r.hash)}...</span></div>`).join('') : '<div class="row"><span>No votes yet</span><span></span></div>';
    } catch (e) { $('#h-name').textContent = 'Server unreachable'; }
  };

  NV.pages.login = () => {
    $('#login-form').addEventListener('submit', async (ev) => {
      ev.preventDefault();
      const btn = $('#submit-btn'), box = $('#form-msg'); box.textContent = '';
      if (!$('#voter_id').value.trim() || !$('#password').value) { box.textContent = 'Enter your Voter ID and password.'; return; }
      setBusy(btn, true, 'Signing in...');
      try { await NV.api.post('/api/auth/login', { voter_id: $('#voter_id').value.trim(), password: $('#password').value }); location.href = safeNext('voter-dashboard.html'); }
      catch (e) { loginErr(e, box); setBusy(btn, false); }
    });
  };

  NV.pages['admin-login'] = () => {
    $('#admin-form').addEventListener('submit', async (ev) => {
      ev.preventDefault();
      const btn = $('#submit-btn'), box = $('#form-msg'); box.textContent = '';
      setBusy(btn, true, 'Signing in...');
      try { await NV.api.post('/api/auth/admin-login', { username: $('#username').value.trim(), password: $('#password').value }); location.href = safeNext('admin-dashboard.html'); }
      catch (e) { loginErr(e, box); setBusy(btn, false); }
    });
  };

  NV.pages.register = () => {
    const form = $('#reg-form'), fields = ['voter_id', 'name', 'email', 'password', 'confirm_password'];
    const showErr = (f, m) => { const el = form.querySelector(`[data-for="${f}"]`); if (el) el.textContent = m || ''; };
    form.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      fields.forEach((f) => showErr(f, '')); $('#form-msg').textContent = '';
      const d = {}; fields.forEach((f) => (d[f] = $('#' + f).value));
      let bad = false;
      if (!/^[A-Za-z0-9_-]{3,20}$/.test(d.voter_id.trim())) { showErr('voter_id', 'Use 3-20 letters, digits, - or _.'); bad = true; }
      if (d.name.trim().length < 2) { showErr('name', 'Enter your full name.'); bad = true; }
      if (!/^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$/.test(d.email.trim())) { showErr('email', 'Enter a valid email address.'); bad = true; }
      if (d.password.length < 8 || !/[A-Za-z]/.test(d.password) || !/\d/.test(d.password)) { showErr('password', 'At least 8 characters with a letter and a digit.'); bad = true; }
      if (d.password !== d.confirm_password) { showErr('confirm_password', 'Passwords do not match.'); bad = true; }
      if (bad) return;
      d.voter_id = d.voter_id.trim(); d.name = d.name.trim(); d.email = d.email.trim();
      const btn = $('#submit-btn'); setBusy(btn, true, 'Registering...');
      try { await NV.api.post('/api/auth/register', d); NV.toast('Registration successful. Please log in.', 'success'); setTimeout(() => (location.href = 'login.html'), 900); }
      catch (e) { loginErr(e, $('#form-msg')); setBusy(btn, false); }
    });
  };

  NV.pages['voter-dashboard'] = async () => {
    const r = (await NV.api.get('/api/voter/profile')).data, p = r.profile, el = r.election;
    $('#welcome').textContent = 'Welcome, ' + p.name;
    $('#el-box').innerHTML = `<dl class="kv"><dt>Election</dt><dd>${esc(el.election_name)}</dd><dt>Status</dt><dd>${NV.statusBadge(el.status)}</dd><dt>Turnout</dt><dd>${el.total_votes} of ${el.total_registered} (${el.turnout_pct}%)</dd></dl>`;
    if (p.has_voted) {
      $('#vote-box').innerHTML = `<p>${NV.badge('VOTED', 'green')} Your ballot is recorded.</p><dl class="kv"><dt>Transaction</dt><dd class="rid">${esc(p.transaction_id)}</dd><dt>Time</dt><dd>${esc(NV.time(p.timestamp))}</dd></dl><a class="btn" href="vote-status.html" style="margin-top:.8rem">View receipt</a>`;
    } else if (el.status === 'ACTIVE') {
      $('#vote-box').innerHTML = `<p>${NV.badge('NOT YET VOTED', 'amber')}</p><a class="btn btn-primary btn-lg" href="voting.html">CAST YOUR VOTE</a>`;
    } else {
      $('#vote-box').innerHTML = `<p>${NV.badge('NOT YET VOTED', 'amber')}</p><div class="notice n-warn">Voting is not open right now (election is ${esc(el.status.replace('_', ' '))}).</div>`;
    }
  };

  const dupCard = (tx, ts) => `<div class="receipt dup" role="status"><h2>VOTING COMPLETED</h2><p>You have already cast your vote. You cannot vote again.</p>
    <dl class="kv"><dt>Transaction</dt><dd class="rid">${esc(tx || '-')}</dd><dt>Time</dt><dd>${esc(NV.time(ts))}</dd><dt>Status</dt><dd>VERIFIED</dd></dl></div>`;

  NV.pages.voting = async () => {
    const area = $('#vote-area');
    const [cands, prof] = await Promise.all([NV.api.get('/api/candidates'), NV.api.get('/api/voter/profile')]);
    const p = prof.data.profile, el = prof.data.election;
    if (p.has_voted) { area.innerHTML = dupCard(p.transaction_id, p.timestamp); return; }
    if (el.status !== 'ACTIVE') { area.innerHTML = `<div class="notice n-warn">Voting is not open right now (election is ${esc(el.status.replace('_', ' '))}).</div>`; return; }
    let chosen = null;
    area.innerHTML = `<div class="cand-grid" role="group" aria-label="Candidates">${cands.data.candidates.map((c) => `<button type="button" class="cand" aria-pressed="false" data-id="${c.id}">
      <span class="sym" style="background:${esc(c.color)}" aria-hidden="true">${esc(c.symbol)}</span><span class="nm">${esc(c.name)}</span><span class="pt">${esc(c.party)}</span><span class="ds">${esc(c.description)}</span><span class="pick">Select</span></button>`).join('')}</div>
      <div class="btn-row" style="margin-top:1.2rem"><button class="btn btn-primary btn-lg" id="continue" disabled>Review and confirm</button></div>`;
    const cards = NV.$$('.cand', area), cont = $('#continue');
    cards.forEach((b) => b.addEventListener('click', () => { chosen = cands.data.candidates.find((c) => c.id === +b.dataset.id); cards.forEach((x) => { x.setAttribute('aria-pressed', x === b); x.querySelector('.pick').textContent = x === b ? 'Selected' : 'Select'; }); cont.disabled = false; }));
    cont.addEventListener('click', async () => {
      const ok = await NV.modal({
        title: 'Are you sure you want to cast your vote?',
        html: `<p>Candidate: <strong>${esc(chosen.name)}</strong><br>Party: ${esc(chosen.party)}</p><div class="notice n-warn"><strong>IMPORTANT:</strong> your vote cannot be changed after submission.</div>`,
        buttons: [{ label: 'CANCEL', value: false }, { label: 'CONFIRM VOTE', value: true, cls: 'btn-primary' }],
      });
      if (ok) submitVote(area, chosen);
    });
  };

  /* CN CONCEPT: client-side reliability. The SAME request id is reused on every retry, so the
     server can recognise duplicates (idempotency) and never records two votes. */
  async function submitVote(area, cand) {
    const rid = NV.reqId();
    const show = (msg) => (area.innerHTML = `<div class="card processing" role="status"><span class="spinner"></span><div><strong>PROCESSING...</strong><div class="muted small">${msg}</div><div class="rid muted">Request ID: ${esc(rid)}</div></div></div>`);
    show('Sending your vote securely...');
    for (let attempt = 0; ; attempt++) {
      try {
        const r = await NV.api.post('/api/vote', { candidate_id: cand.id, request_id: rid }, { requestId: rid, timeout: 8000 });
        const d = r.data;
        area.innerHTML = `<div class="receipt" role="status"><h2>VOTE SUCCESSFUL</h2>${d.replayed ? '<div class="notice n-info" style="margin-bottom:1rem">The server recognised your retry (same Request ID) and returned the original result. No second vote was created.</div>' : ''}
          <dl class="kv"><dt>Transaction ID</dt><dd class="rid">${esc(d.transaction_id)}</dd><dt>Request ID</dt><dd class="rid">${esc(d.request_id)}</dd><dt>Timestamp</dt><dd>${esc(NV.time(d.timestamp))}</dd><dt>Status</dt><dd>${esc(d.status.toUpperCase())}</dd><dt>Receipt code</dt><dd class="rid">${esc(d.receipt || '-')}</dd><dt>Round trip</dt><dd>${r.ms} ms</dd></dl>
          <div class="btn-row" style="margin-top:1rem"><a class="btn" href="vote-status.html">View receipt</a><a class="btn" href="voter-dashboard.html">Dashboard</a></div></div>`;
        return;
      } catch (e) {
        if ((e.code === 'TIMEOUT' || e.code === 'NETWORK') && attempt < 2) { show(`No response from the server. Retrying with the same Request ID (attempt ${attempt + 2} of 3)...`); await NV.sleep(1200 * (attempt + 1)); continue; }
        if (e.code === 'ALREADY_VOTED') { area.innerHTML = dupCard(e.extra.transaction_id, e.extra.voted_at); return; }
        area.innerHTML = `<div class="notice n-bad" role="alert"><strong>Voting request failed.</strong><p>${esc(e.message)}</p><p><strong>Your vote may not have been recorded</strong> unless a receipt is shown.</p><p class="rid">Request ID: ${esc(e.requestId || rid)}</p>
          <div class="btn-row"><a class="btn" href="voting.html">Try again</a><a class="btn" href="vote-status.html">Check my receipt</a></div></div>`;
        return;
      }
    }
  }

  NV.pages['vote-status'] = async () => {
    const box = $('#status-box');
    if (NV.me && NV.me.authenticated && NV.me.user.role === 'voter') {
      try {
        const st = (await NV.api.get('/api/vote/status')).data;
        box.innerHTML = st.has_voted
          ? `<div class="receipt"><h2>Vote recorded</h2><dl class="kv"><dt>Transaction ID</dt><dd class="rid">${esc(st.transaction_id)}</dd><dt>Request ID</dt><dd class="rid">${esc(st.request_id)}</dd><dt>Time</dt><dd>${esc(NV.time(st.timestamp))}</dd><dt>Status</dt><dd>VERIFIED</dd><dt>Receipt code</dt><dd class="rid">${esc(st.receipt)}</dd></dl></div>`
          : `<div class="notice n-info">You have not voted yet. <a href="voting.html">Cast your vote</a></div>`;
      } catch (e) {
        box.innerHTML = `<div class="notice n-info">Unable to load personal receipt. You can still verify any transaction ID below.</div>`;
      }
    } else {
      box.innerHTML = `<div class="notice n-info" style="background:#f0f9ff;border-color:#bae6fd">Voters can <a href="login.html">log in</a> to see their personal ballot receipt. Anyone can use the public lookup below to verify any ballot in the ledger.</div>`;
    }
    $('#verify-form').addEventListener('submit', async (ev) => {
      ev.preventDefault();
      const tx = $('#tx').value.trim(); if (!tx) return;
      const r = (await NV.api.get('/api/verify-receipt?transaction_id=' + encodeURIComponent(tx))).data;
      $('#verify-out').innerHTML = r.found ? `<div class="notice n-ok">Found in ledger: <span class="rid">${esc(r.transaction_id)}</span>, recorded ${esc(NV.time(r.timestamp))}, hash <span class="rid">${esc(r.hash)}...</span></div>` : '<div class="notice n-warn">No such transaction in the ledger.</div>';
    });
  };

  NV.pages.results = async () => {
    const area = $('#res-area'); let bar, dn, stop;
    const draw = async () => {
      let r;
      try { r = (await NV.api.get('/api/results')).data; }
      catch (e) { if (e.code === 'RESULTS_NOT_PUBLISHED') { area.innerHTML = `<div class="notice n-info"><strong>Results are not published yet.</strong> They appear when the election ends. Current status: ${esc(e.extra.election_status || '')}.</div>`; if (stop) stop(); return; } throw e; }
      $('#res-badge').innerHTML = r.final ? NV.badge('FINAL RESULTS', 'navy') : NV.badge('LIVE (admin view)', 'amber');
      const e = r.election, c = r.results;
      if (!bar) {
        area.innerHTML = `<div class="grid g4"><div class="card metric info"><div class="k">Registered voters</div><div class="v" id="r-reg"></div></div><div class="card metric info"><div class="k">Votes cast</div><div class="v" id="r-votes"></div></div><div class="card metric ok"><div class="k">Turnout</div><div class="v" id="r-turn"></div></div><div class="card metric"><div class="k">Leading</div><div class="v" id="r-lead" style="font-size:1.1rem"></div></div></div>
        <div class="grid g2" style="margin-top:1rem"><div class="card"><h3>Votes per candidate</h3><div class="chart-box"><canvas id="rc-bar" role="img" aria-label="Votes per candidate"></canvas></div></div><div class="card"><h3>Share of votes</h3><div class="chart-box"><canvas id="rc-dn" role="img" aria-label="Vote share"></canvas></div></div></div>
        <div class="card" style="margin-top:1rem"><h3>Breakdown</h3><div id="r-bars"></div></div>`;
        bar = NV.charts.bar('rc-bar', c.map((x) => x.name), [{ label: 'Votes', data: c.map((x) => x.vote_count), backgroundColor: c.map((x) => x.color) }], { plugins: { legend: { display: false } } });
        dn = NV.charts.doughnut('rc-dn', c.map((x) => x.name), c.map((x) => x.vote_count), c.map((x) => x.color));
      }
      $('#r-reg').textContent = NV.int(e.total_registered); $('#r-votes').textContent = NV.int(e.total_votes); $('#r-turn').textContent = e.turnout_pct + '%';
      $('#r-lead').textContent = r.total_votes ? c[0].name + ' (' + c[0].percent + '%)' : 'No votes yet';
      NV.charts.set(bar, c.map((x) => x.name), [c.map((x) => x.vote_count)]); bar.data.datasets[0].backgroundColor = c.map((x) => x.color);
      NV.charts.set(dn, c.map((x) => x.name), [c.map((x) => x.vote_count)]); dn.data.datasets[0].backgroundColor = c.map((x) => x.color);
      $('#r-bars').innerHTML = c.map((x) => `<div style="margin:.7rem 0"><div style="display:flex;justify-content:space-between"><span><strong>${esc(x.symbol)} ${esc(x.name)}</strong> <span class="muted small">${esc(x.party)}</span></span><span>${x.vote_count} votes (${x.percent}%)</span></div><div class="bar"><i style="width:${x.percent}%;background:${esc(x.color)}"></i></div></div>`).join('');
    };
    await draw();
    if (NV.me.user && NV.me.user.role === 'admin') stop = NV.poll(draw, 4000);
  };
})();
