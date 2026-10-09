/* Concurrency lab, TCP demo and the demonstrations page. Every result is returned by the backend. */
(function () {
  'use strict';
  const { $, esc } = NV;
  const cell = (k, v) => `<div class="cell"><div class="k">${esc(k)}</div><div class="v">${v}</div></div>`;
  const OUT_COLOR = { success: '#0f7a55', rejected: '#8b93a7', error: '#b6322a' };

  /* ---- Gantt-style timeline: one row per thread. amber = waiting for the lock, colour = executing/outcome */
  function drawTimeline(canvas, tl) {
    const dpr = window.devicePixelRatio || 1, W = canvas.parentElement.clientWidth - 2, rowH = tl.length > 60 ? 5 : 8, pad = 24, H = tl.length * rowH + pad + 8;
    canvas.width = W * dpr; canvas.height = H * dpr; canvas.style.width = W + 'px'; canvas.style.height = H + 'px';
    const g = canvas.getContext('2d'); g.scale(dpr, dpr); g.clearRect(0, 0, W, H);
    const maxT = Math.max(...tl.map((r) => r.end_ms), 1), x = (t) => 70 + (t / maxT) * (W - 90);
    g.font = '11px sans-serif'; g.fillStyle = '#5a6a85';
    for (let i = 0; i <= 5; i++) { const t = (maxT * i) / 5; g.fillText(Math.round(t) + ' ms', x(t) - 14, 12); g.fillStyle = '#e4e9f3'; g.fillRect(x(t), 16, 1, H - 16); g.fillStyle = '#5a6a85'; }
    tl.forEach((r, i) => {
      const y = pad + i * rowH, w0 = Math.min(r.wait_ms, r.end_ms - r.start_ms);
      if (tl.length <= 40) { g.fillStyle = '#5a6a85'; g.fillText('Thread ' + (i + 1), 6, y + rowH - 1); }
      g.fillStyle = '#e0a21a'; g.fillRect(x(r.start_ms), y, Math.max(1, x(r.start_ms + w0) - x(r.start_ms)), rowH - 1);
      g.fillStyle = OUT_COLOR[r.outcome] || '#2456e6'; g.fillRect(x(r.start_ms + w0), y, Math.max(2, x(r.end_ms) - x(r.start_ms + w0)), rowH - 1);
    });
  }

  function labResult(r) {
    const verdictCls = r.synchronization ? (r.race_detected ? 'badv' : 'good') : (r.race_detected ? 'badv' : 'neutral');
    const pipe = r.synchronization
      ? `<div class="pipeline"><span class="pipe-node">${r.requests_sent} threads</span><span class="pipe-arrow">&rarr;</span><span class="pipe-node crit">CRITICAL SECTION &middot; vote lock</span><span class="pipe-arrow">&rarr;</span><span class="pipe-node db">DATABASE TRANSACTION</span></div>`
      : `<div class="pipeline"><span class="pipe-node">${r.requests_sent} threads</span><span class="pipe-arrow">&rarr;</span><span class="pipe-node" style="border-color:#b6322a;color:#b6322a">NO LOCK, NO TRANSACTION</span><span class="pipe-arrow">&rarr;</span><span class="pipe-node db">DATABASE (unprotected)</span></div>`;
    return `<div class="card"><div class="card-head"><h3>Concurrency test result</h3><span class="sim-tag">EDUCATIONAL SIMULATION</span></div>
      <p>Race condition: <span class="verdict ${verdictCls}">${esc(r.race_condition)}</span></p>${pipe}
      <div class="result-grid">${cell('Requests sent', r.requests_sent)}${cell('Requests completed', r.requests_completed)}${cell('Successful votes', r.successful_votes)}${cell('Rejected requests', r.rejected_requests)}${cell('Errors', r.errors)}
      ${cell('Duplicate votes in DB', r.duplicate_votes)}${cell('Lost counter updates', r.lost_updates)}${cell('Threads used', r.threads_used)}${cell('Peak active threads', r.peak_active_threads)}
      ${cell('Average response', r.avg_ms + ' ms')}${cell('P95 response', r.p95_ms + ' ms')}${cell('Maximum response', r.max_ms + ' ms')}${cell('Execution time', r.execution_ms + ' ms')}
      ${r.lock ? cell('Lock acquisitions', r.lock.acquisitions) + cell('Lock contention', r.lock.contention_pct + '%') + cell('Max lock wait', r.lock.max_wait_ms + ' ms') : ''}${r.pool ? cell('Pool workers', r.pool.max_workers) + cell('Pool completed', r.pool.completed) : ''}</div>
      <p class="small muted" style="margin-top:.8rem">Ledger rows: ${r.ledger_rows}. Voters marked voted: ${r.voters_marked_voted}. Sum of candidate counters: ${r.counter_sum}. ${r.synchronization ? 'Expected for one voter: exactly 1 vote, counters equal to ledger rows.' : 'Without synchronization, ledger rows exceed 1 per voter (duplicates) and counters fall behind the ledger (lost updates).'}</p></div>
      <div class="card"><h3>Thread timeline</h3><div class="legend"><span><i style="background:#e0a21a"></i>waiting for the lock</span><span><i style="background:#0f7a55"></i>vote accepted</span><span><i style="background:#8b93a7"></i>rejected (already voted)</span><span><i style="background:#b6322a"></i>error</span></div>
      <canvas id="timeline" role="img" aria-label="Thread timeline"></canvas><p class="hint">Showing ${r.timeline.length} of ${r.requests_sent} threads, ordered by start time. ${esc(r.label)}</p></div>`;
  }

  /* ---- animated race trace (REAL event log from two threads) */
  function playTrace(box, tr) {
    const lanes = ['Thread 1', 'Thread 2'], maxT = Math.max(...tr.events.map((e) => e.t_ms), 1);
    const accepted = tr.events.filter((e) => e.op === 'RESULT: vote accepted').length;
    const token = (box._run = (box._run || 0) + 1);                 // a newer run cancels older timers
    const alive = () => box.isConnected && box._run === token;
    box.innerHTML = `<div class="lanes">${lanes.map((l, i) => `<div class="lane"><h4>${l}</h4><div data-lane="${i}"></div></div>`).join('')}</div><div data-res style="margin-top:1rem"></div>`;
    let at = 0;
    tr.events.forEach((e) => {
      at = Math.max(at + 380, (e.t_ms / maxT) * 4200);
      setTimeout(() => {
        if (!alive()) return;
        const lane = box.querySelector(`[data-lane="${e.thread === 'Thread 1' ? 0 : 1}"]`); if (!lane) return;
        let cls = 'chip', op = e.op;
        if (op.startsWith('LOCK_WAIT')) cls += ' wait'; else if (op.startsWith('LOCK_') || op === 'UNLOCK') cls += ' lock';
        else if (op.startsWith('RESULT: REJECTED')) cls += tr.synchronization ? ' good' : ' bad';
        else if (op === 'RESULT: vote accepted') cls += accepted > 1 ? ' bad' : ' good';
        else if (op.startsWith('COMMIT')) cls += ' good';
        lane.insertAdjacentHTML('beforeend', `<div class="${cls}">${esc(op)} <span class="muted">+${e.t_ms} ms</span></div>`);
      }, at);
    });
    setTimeout(() => { if (!alive()) return; box.querySelector('[data-res]').innerHTML = `<span class="verdict ${tr.result.includes('PREVENTED') ? 'good' : tr.result.includes('DUPLICATE') ? 'badv' : 'neutral'}">RESULT: ${esc(tr.result)}</span> <span class="muted small">votes recorded for the single voter: ${tr.votes_recorded}</span>`; }, at + 500);
  }

  NV.pages['concurrency-lab'] = () => {
    const mode = NV.seg('#seg-mode'), nSeg = NV.seg('#seg-n'), sync = NV.seg('#seg-sync'), exec = NV.seg('#seg-exec');
    $('#start-test').addEventListener('click', async () => {
      const btn = $('#start-test'); btn.disabled = true; $('#test-spin').classList.remove('hidden');
      try {
        const r = (await NV.api.post('/api/admin/concurrency-test', { mode: mode.get(), requests: +nSeg.get(), synchronization: sync.get() === '1', executor: exec.get() }, { timeout: 60000 })).data.result;
        $('#lab-out').innerHTML = labResult(r); drawTimeline($('#timeline'), r.timeline);
        NV.toast('Test finished: ' + r.race_condition, r.race_detected && r.synchronization ? 'error' : 'success');
      } catch (e) { NV.showError(e); }
      btn.disabled = false; $('#test-spin').classList.add('hidden');
    });
    const race = (safe) => async () => {
      $('#race-out').innerHTML = '<span class="spinner"></span> running two real threads...';
      try { const tr = (await NV.api.post('/api/admin/demo/race-trace', { synchronization: safe }, { timeout: 30000 })).data.result; playTrace($('#race-out'), tr); } catch (e) { $('#race-out').innerHTML = ''; NV.showError(e); }
    };
    $('#race-unsafe').addEventListener('click', race(false)); $('#race-safe').addEventListener('click', race(true));
  };

  /* ---- TCP */
  function tcpView(r) {
    const lines = r.transcript.map((l) => l.dir === 'client' ? `<span class="c">CLIENT &rarr;</span> ${esc(l.text)}\n<span class="i">   frame bytes: ${esc(l.hex)}</span>` : l.dir === 'server' ? `<span class="s">SERVER &larr;</span> ${esc(l.text)}` : `<span class="h">${esc(l.text)}</span>`).join('\n');
    const f = r.framing;
    return `<div class="card"><h3>Session transcript <span class="sim-tag">REAL TCP SOCKETS</span></h3><div class="term">${lines}</div>
      <p class="small muted" style="margin-top:.6rem">Calls used: ${r.calls.map((c) => `<code>${c}</code>`).join(' ')}. Port ${r.port} was chosen by the OS. The second VOTE is rejected because the voter already voted.</p></div>
      <div class="card"><h3>Why framing is needed</h3><div class="term">server did:  send("VOTE_ACK|TX-1;")   send("VOTE_ACK|TX-2;")      <span class="i">(2 send calls)</span>
client did:  recv(1024)  <span class="i">(1 recv call)</span>  &rarr;  <span class="h">${esc(f.received)}</span></div>
      <p style="margin-top:.7rem">${f.merged ? NV.badge('MERGED', 'amber') + ' ' : ''}${esc(f.lesson)}</p><p class="small">Fix used by NetVote's TCP demo: <code>[4-byte length][payload]</code> and a <code>recv_exact()</code> loop that keeps reading until all N bytes arrive.</p></div>`;
  }
  NV.pages['tcp-demo'] = () => {
    $('#run-tcp').addEventListener('click', async () => {
      const b = $('#run-tcp'); b.disabled = true; $('#tcp-out').innerHTML = '<span class="spinner"></span> opening sockets...';
      try { $('#tcp-out').innerHTML = tcpView((await NV.api.post('/api/admin/demo/tcp', {}, { timeout: 30000 })).data.result); } catch (e) { $('#tcp-out').innerHTML = ''; NV.showError(e); }
      b.disabled = false;
    });
  };

  /* ---- demonstrations */
  const run = (name, body, t) => NV.api.post('/api/admin/demo/' + name, body || {}, { timeout: t || 30000 }).then((r) => r.data.result);
  const evTable = (ev) => `<div class="term">${ev.map((e) => `<span class="i">+${String(e.t_ms).padStart(6)} ms</span>  <span class="c">${esc(e.thread)}</span>  ${esc(e.op)}`).join('\n')}</div>`;
  const DEMOS = [
    { id: 'race', title: 'Demonstrate Race Condition', concept: 'OS: race condition, critical section, lost update',
      problem: 'Two threads check has_voted at the same time, both see false, and both insert a vote.', solution: 'Make check-then-act indivisible with a mutex plus a transaction.',
      go: async (sim) => { const tr = await run('race-trace', { synchronization: false }); const st = await NV.api.post('/api/admin/concurrency-test', { mode: 'same_voter', requests: 50, synchronization: false }, { timeout: 60000 }).then((x) => x.data.result);
        sim.html = ''; sim.fn = (box) => { const d = document.createElement('div'); box.appendChild(d); playTrace(d, tr); const s = document.createElement('div'); s.style.marginTop = '1rem'; s.innerHTML = `<div class="result-grid">${cell('Threads', st.requests_sent)}${cell('Duplicate votes', st.duplicate_votes)}${cell('Lost updates', st.lost_updates)}</div>`; box.appendChild(s); };
        return { text: `${st.race_condition}: ${st.duplicate_votes} duplicate votes and ${st.lost_updates} lost counter updates with 50 unsynchronised threads.`, bad: st.race_detected }; } },
    { id: 'sync', title: 'Demonstrate Synchronization', concept: 'OS: mutex (threading.Lock), atomicity',
      problem: 'The same attack, but the vote path holds the vote lock and runs in BEGIN IMMEDIATE ... COMMIT.', solution: 'Exactly one thread enters the critical section at a time; the rest wait, re-check, and are rejected.',
      go: async (sim) => { const tr = await run('race-trace', { synchronization: true }); const st = await NV.api.post('/api/admin/concurrency-test', { mode: 'same_voter', requests: 100, synchronization: true }, { timeout: 60000 }).then((x) => x.data.result);
        sim.fn = (box) => { const d = document.createElement('div'); box.appendChild(d); playTrace(d, tr); const s = document.createElement('div'); s.style.marginTop = '1rem'; s.innerHTML = `<div class="result-grid">${cell('Threads', st.requests_sent)}${cell('Successful', st.successful_votes)}${cell('Rejected', st.rejected_requests)}${cell('Duplicates', st.duplicate_votes)}${cell('Lock contention', st.lock.contention_pct + '%')}${cell('Avg response', st.avg_ms + ' ms')}</div>`; box.appendChild(s); };
        return { text: `${st.successful_votes} successful, ${st.rejected_requests} rejected, ${st.duplicate_votes} duplicates. Race condition ${st.race_condition}.`, bad: st.race_detected }; } },
    { id: 'timeout', title: 'Demonstrate Network Timeout', concept: 'CN: timeouts, request/response, TCP',
      problem: 'The server answers slower than the client is willing to wait.', solution: 'Clients set timeouts, and because vote requests are idempotent a retry with the same Request ID is safe.',
      go: async (sim) => { const r = (await NV.api.post('/api/admin/network-test', { delay_ms: 3000, timeout_ms: 2000, burst: 0 }, { timeout: 30000 })).data.result;
        sim.fn = (box) => { box.insertAdjacentHTML('beforeend', `<div class="result-grid">${cell('Normal request', r.normal.ms + ' ms')}${cell('Simulated request', r.simulated.ms + ' ms')}${cell('Status', esc(r.simulated.status))}</div><p class="small">Request ID <span class="rid">${esc(r.simulated.request_id)}</span></p>`); };
        return { text: r.verdict, bad: r.simulated.status === 'TIMEOUT' }; } },
    { id: 'rate', title: 'Demonstrate Rate Limiting', concept: 'CN: application-layer rate limiting, HTTP 429',
      problem: 'A client floods the login or vote endpoint.', solution: 'Sliding-window limiter per IP returns 429 with Retry-After. (TCP congestion control is separate and is not re-implemented.)',
      go: async (sim) => { const r = await run('rate-limit');
        sim.fn = (box) => { box.insertAdjacentHTML('beforeend', `<div style="display:flex;flex-wrap:wrap;gap:4px">${r.sequence.map((s) => `<span title="request ${s.n}: HTTP ${s.status}" class="badge b-${s.status === 200 ? 'green' : 'red'}" style="min-width:2.2rem;justify-content:center">${s.n}</span>`).join('')}</div><p class="small muted">Green = 200 OK, red = 429 Too Many Requests</p>`); };
        return { text: r.result, bad: false }; } },
    { id: 'retry', title: 'Demonstrate Request Retry', concept: 'CN: idempotency, reliability over an unreliable network',
      problem: 'The vote is stored but the response is lost; the client retries.', solution: 'The Request ID is the idempotency key: the server returns the original result and creates no second vote.',
      go: async (sim) => { const r = await run('retry');
        sim.fn = (box) => { box.insertAdjacentHTML('beforeend', `<div class="term">${r.log.map((l) => `<span class="${l.who === 'client' ? 'c' : l.who === 'server' ? 's' : 'h'}">${l.who.toUpperCase().padEnd(8)}</span> ${esc(l.msg)}`).join('\n')}</div><p class="small">Votes in demo ledger: <strong>${r.votes_in_ledger}</strong></p>`); };
        return { text: r.result, bad: !r.idempotent }; } },
    { id: 'rollback', title: 'Demonstrate Transaction Rollback', concept: 'OS/DB: atomicity, ACID',
      problem: 'A failure happens after the vote row is inserted but before the tally is updated.', solution: 'ROLLBACK undoes every statement since BEGIN, so no half-recorded vote can exist.',
      go: async (sim) => { const r = await run('rollback');
        sim.fn = (box) => { const row = (k, o) => `<tr><td>${k}</td><td>${o.votes_in_ledger}</td><td>${o.voter_has_voted}</td><td>${o.candidate_1_count}</td></tr>`;
          box.insertAdjacentHTML('beforeend', `<ol class="steps">${r.steps.map((s) => `<li><strong>${esc(s.step)}</strong> ${esc(s.detail)}</li>`).join('')}</ol><div class="table-wrap" style="margin-top:.8rem"><table><thead><tr><th>State</th><th>Votes in ledger</th><th>has_voted</th><th>Candidate counter</th></tr></thead><tbody>${row('Before', r.before)}${row('After failed vote (rolled back)', r.after_failure)}${row('After clean retry', r.after_retry)}</tbody></table></div>`); };
        return { text: r.result, bad: !r.atomic }; } },
    { id: 'tcp', title: 'Demonstrate TCP Communication', concept: 'CN: sockets, TCP, message framing',
      problem: 'TCP is a byte stream; message boundaries are not preserved.', solution: 'Length-prefixed frames and a recv_exact() loop.',
      go: async (sim) => { const r = await run('tcp'); sim.fn = (box) => { const d = document.createElement('div'); d.className = 'stack'; d.innerHTML = tcpView(r); box.appendChild(d); }; return { text: `Framed session completed on port ${r.port}; raw recv merged two messages: ${r.framing.merged}.`, bad: false }; } },
    { id: 'deadlock', title: 'Demonstrate Deadlock', concept: 'OS: deadlock, Coffman conditions, lock ordering',
      problem: 'Process A holds R1 and wants R2; Process B holds R2 and wants R1.', solution: 'Lock ordering, timeouts with back-off, or try-lock. The voting path uses a single lock, so a cycle is impossible.',
      go: async (sim) => { const bad = await run('deadlock', { strategy: 'deadlock' }), good = await run('deadlock', { strategy: 'lock_ordering' }), tb = await run('deadlock', { strategy: 'timeout_backoff' });
        sim.fn = (box) => { [['Without prevention', bad], ['Prevention: lock ordering', good], ['Avoidance: timeout + back-off', tb]].forEach(([t, x]) => box.insertAdjacentHTML('beforeend', `<h4 style="margin:.8rem 0 .3rem">${t}: <span class="verdict ${x.deadlock_detected ? 'badv' : 'good'}" style="font-size:.85rem;padding:.2rem .6rem">${esc(x.result)}</span></h4>${evTable(x.events)}<p class="small muted">${esc(x.explanation)}</p>`)); };
        return { text: `${bad.result}. With lock ordering: ${good.result}.`, bad: false }; } },
    { id: 'starve', title: 'Demonstrate Starvation', concept: 'OS: starvation, scheduling fairness, aging',
      problem: 'A low-priority job waits forever while high-priority jobs keep arriving.', solution: 'FIFO or priority with aging bounds the wait. The vote lock also uses a timeout.',
      go: async (sim) => { const r = await run('starvation'); const names = { priority: 'Strict priority', fifo: 'FIFO', aging: 'Priority + aging' };
        sim.fn = (box) => box.insertAdjacentHTML('beforeend', `<div class="table-wrap"><table><thead><tr><th>Policy</th><th>Low-priority job waited</th><th>Finished at</th><th>Avg wait (all jobs)</th></tr></thead><tbody>${r.policies.map((p) => `<tr><td>${names[p.policy]}</td><td><strong>${p.low_priority_wait} ticks</strong></td><td>t=${p.low_priority_finish}</td><td>${p.avg_wait}</td></tr>`).join('')}</tbody></table></div><p class="small muted">${esc(r.explanation)}</p>`);
        return { text: `Strict priority starved the low-priority job for ${r.policies[0].low_priority_wait} ticks; FIFO ${r.policies[1].low_priority_wait}, aging ${r.policies[2].low_priority_wait}.`, bad: false }; } },
    { id: 'tamper', title: 'Demonstrate Tamper Detection', concept: 'Security: hash chain, integrity',
      problem: 'Someone edits a stored vote directly in the database.', solution: 'Each vote hash covers the previous hash, so any edit breaks verification. Tamper-evident, not tamper-proof.',
      go: async (sim) => { const r = await run('tamper');
        sim.fn = (box) => box.insertAdjacentHTML('beforeend', `<p>Before edit: <strong>${r.before_tamper.valid ? 'valid' : 'invalid'}</strong> (${r.before_tamper.votes_checked} votes)</p><p>After a direct SQL edit:</p><div class="term">${r.after_tamper.problems.map((p) => '<span class="h">!</span> ' + esc(p)).join('\n')}</div><p class="small muted">${esc(r.note)}</p>`);
        return { text: r.result, bad: false }; } },
  ];

  NV.pages.demonstrations = () => {
    $('#demo-cards').innerHTML = DEMOS.map((d) => `<div class="card concept"><h3>${esc(d.title)}</h3><p class="small muted">${esc(d.concept)}</p><button class="btn btn-primary" data-id="${d.id}">Run demonstration</button></div>`).join('');
    NV.$$('#demo-cards button').forEach((b) => b.addEventListener('click', async () => {
      const d = DEMOS.find((x) => x.id === b.dataset.id), out = $('#demo-out');
      NV.$$('#demo-cards button').forEach((x) => (x.disabled = true));
      out.innerHTML = `<div class="card"><span class="spinner"></span> running <strong>${esc(d.title)}</strong>...</div>`; out.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      try {
        const sim = {}, res = await d.go(sim);
        out.innerHTML = `<div class="card stack"><div class="card-head"><h2>${esc(d.title)}</h2><span class="sim-tag">EDUCATIONAL SIMULATION</span></div>
          <div><h4>1. Problem</h4><p>${esc(d.problem)}</p></div><div><h4>2. Simulation</h4><div id="sim-box"></div></div>
          <div><h4>3. Result</h4><p><span class="verdict ${res.bad ? 'badv' : 'good'}">${esc(res.text)}</span></p></div><div><h4>4. Solution</h4><p>${esc(d.solution)}</p></div><div><h4>5. CN / OS concept</h4><p>${esc(d.concept)}</p></div></div>`;
        if (sim.fn) sim.fn($('#sim-box'));
      } catch (e) { out.innerHTML = ''; NV.showError(e); }
      NV.$$('#demo-cards button').forEach((x) => (x.disabled = false));
    }));
  };
})();
