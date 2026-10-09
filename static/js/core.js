/* NetVote frontend core: API client, toasts, modals, layout shell, helpers.
   CN CONCEPT: client side of the HTTP request/response model - request IDs, timeouts, retries. */
(function () {
  'use strict';
  const NV = (window.NV = { pages: {}, me: null });

  /* ---------- helpers ---------- */
  NV.$ = (s, r) => (r || document).querySelector(s);
  NV.$$ = (s, r) => Array.from((r || document).querySelectorAll(s));
  NV.esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  NV.int = (n) => (n ?? 0).toLocaleString('en-US');
  NV.time = (iso) => (iso ? iso.replace('T', ' ') : '-');
  NV.sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  NV.reqId = () => {
    const a = new Uint8Array(4); crypto.getRandomValues(a);
    return 'REQ-' + new Date().getFullYear() + '-' + Array.from(a, (b) => b.toString(16).padStart(2, '0')).join('').toUpperCase();
  };
  NV.badge = (text, kind) => `<span class="badge b-${kind || 'blue'}">${NV.esc(text)}</span>`;
  const STATUS_KIND = { ACTIVE: 'green', PAUSED: 'amber', ENDED: 'navy', NOT_STARTED: 'blue', healthy: 'green', warning: 'amber', critical: 'red' };
  NV.statusBadge = (s) => NV.badge(String(s).replace('_', ' '), STATUS_KIND[s] || 'blue');
  NV.dot = (state) => `<span class="dot ${state === 'healthy' ? 'green' : state === 'warning' ? 'amber' : 'red'}"></span>`;
  NV.poll = (fn, ms) => {
    let stopped = false;
    const tick = async () => { if (stopped) return; if (!document.hidden) { try { await fn(); } catch (e) { /* shown by caller */ } } setTimeout(tick, ms); };
    tick();
    return () => { stopped = true; };
  };

  /* ---------- API client ---------- */
  class ApiError extends Error {
    constructor(code, message, status, requestId, extra) { super(message); Object.assign(this, { code, status, requestId, extra: extra || {} }); }
  }
  NV.ApiError = ApiError;

  function friendly(status, serverMsg) {
    if (status === 0) return 'Cannot reach the NetVote server. Check that it is running. Your request was not processed.';
    if (status === 503) return serverMsg || 'Service temporarily unavailable. Your request has NOT been recorded.';
    if (status >= 500) return serverMsg || 'Something went wrong on the server. Try again or contact the administrator.';
    return serverMsg || 'The request could not be completed.';
  }

  async function request(method, path, body, opts) {
    opts = opts || {};
    const rid = opts.requestId || NV.reqId();
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), opts.timeout || 10000);
    const t0 = performance.now();
    let res;
    try {
      res = await fetch(path, {
        method, credentials: 'same-origin', signal: ctrl.signal,
        headers: { 'Content-Type': 'application/json', Accept: 'application/json', 'X-Requested-With': 'NetVote', 'X-Request-ID': rid },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch (e) {
      clearTimeout(timer);
      if (e.name === 'AbortError') throw new ApiError('TIMEOUT', 'The server took too long to respond. Your request may or may not have been processed. Retrying with the same Request ID is safe.', 0, rid);
      throw new ApiError('NETWORK', friendly(0), 0, rid);
    }
    clearTimeout(timer);
    let data = null;
    try { data = await res.json(); } catch (e) { /* non-JSON */ }
    const ms = Math.round(performance.now() - t0);
    if (!res.ok) {
      const err = (data && data.error) || {};
      if (res.status === 401 && err.code === 'UNAUTHENTICATED' && document.body.dataset.require) { goLogin(); }
      throw new ApiError(err.code || 'HTTP_' + res.status, friendly(res.status, err.message), res.status, (data && data.request_id) || rid, err);
    }
    return { data, ms, status: res.status, requestId: (data && data.request_id) || rid };
  }
  NV.api = {
    get: (p, o) => request('GET', p, undefined, o), post: (p, b, o) => request('POST', p, b === undefined ? {} : b, o),
    put: (p, b, o) => request('PUT', p, b, o), del: (p, o) => request('DELETE', p, undefined, o),
  };

  function goLogin() {
    const need = document.body.dataset.require;
    const next = encodeURIComponent(location.pathname.replace(/^\//, ''));
    location.href = (need === 'admin' ? 'admin-login.html' : 'login.html') + '?next=' + next;
  }

  /* ---------- toast & modal ---------- */
  NV.toast = (msg, type, rid) => {
    let box = NV.$('#toasts');
    if (!box) { box = document.createElement('div'); box.id = 'toasts'; box.setAttribute('role', 'status'); box.setAttribute('aria-live', 'polite'); document.body.appendChild(box); }
    const t = document.createElement('div');
    t.className = 'toast ' + (type || 'info');
    t.innerHTML = NV.esc(msg) + (rid ? `<span class="rid">Request ID: ${NV.esc(rid)}</span>` : '');
    box.appendChild(t);
    setTimeout(() => t.remove(), type === 'error' ? 8000 : 4500);
  };
  NV.showError = (e) => {
    if (e instanceof ApiError) NV.toast(e.message, 'error', e.requestId);
    else { console.error(e); NV.toast('Something went wrong. Please try again.', 'error'); }
  };

  NV.modal = (opts) => new Promise((resolve) => {
    const prev = document.activeElement;
    const back = document.createElement('div');
    back.className = 'modal-back';
    const buttons = opts.buttons || [{ label: 'OK', value: true, cls: 'btn-primary' }];
    back.innerHTML = `<div class="modal" role="dialog" aria-modal="true" aria-labelledby="mt"><h3 id="mt">${NV.esc(opts.title)}</h3>
      <div>${opts.html || ''}</div><div class="btn-row">${buttons.map((b, i) => `<button class="btn ${b.cls || ''}" data-i="${i}">${NV.esc(b.label)}</button>`).join('')}</div></div>`;
    document.body.appendChild(back);
    const btns = NV.$$('button', back);
    const close = (v) => { back.remove(); document.removeEventListener('keydown', onKey); if (prev) prev.focus(); resolve(v); };
    const onKey = (e) => {
      if (e.key === 'Escape') close(false);
      if (e.key === 'Tab') { const first = btns[0], last = btns[btns.length - 1]; if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); } else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); } }
    };
    document.addEventListener('keydown', onKey);
    btns.forEach((b) => b.addEventListener('click', () => close(buttons[+b.dataset.i].value)));
    btns[btns.length - 1].focus();
  });
  NV.confirm = (title, html, confirmLabel, danger) => NV.modal({
    title, html, buttons: [{ label: 'Cancel', value: false }, { label: confirmLabel || 'Confirm', value: true, cls: danger ? 'btn-danger' : 'btn-primary' }],
  });

  /* ---------- icons & layout ---------- */
  const I = {
    grid: '<rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>',
    flag: '<path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><line x1="4" y1="22" x2="4" y2="15"/>',
    users: '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
    id: '<rect x="2" y="5" width="20" height="14" rx="2"/><circle cx="8" cy="12" r="2"/><path d="M14 10h5M14 14h5"/>',
    chart: '<line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>',
    list: '<line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><circle cx="3.5" cy="6" r="1"/><circle cx="3.5" cy="12" r="1"/><circle cx="3.5" cy="18" r="1"/>',
    wifi: '<path d="M5 12.55a11 11 0 0 1 14.08 0"/><path d="M1.42 9a16 16 0 0 1 21.16 0"/><path d="M8.53 16.11a6 6 0 0 1 6.95 0"/><line x1="12" y1="20" x2="12.01" y2="20"/>',
    cpu: '<rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 14h3M1 9h3M1 14h3"/>',
    pulse: '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>',
    term: '<polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/>',
    play: '<polygon points="5 3 19 12 5 21 5 3"/>',
    book: '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>',
    shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
    sliders: '<line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/>',
    out: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>',
    layers: '<polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/>',
    q: '<circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
    globe: '<circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>',
  };
  const icon = (n) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${I[n]}</svg>`;
  const LOGO = `<svg viewBox="0 0 32 32" aria-hidden="true"><rect x="2" y="2" width="28" height="28" rx="7" fill="#0284c7"/><rect x="8" y="14" width="16" height="11" rx="2" fill="#fff"/><rect x="12" y="17" width="8" height="2" rx="1" fill="#0284c7"/><path d="M13 9.5l2.2 2.2L20 7" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>`;

  const ADMIN_NAV = [
    ['Control Center', [['Dashboard', 'admin-dashboard.html', 'grid'], ['Election', 'election.html', 'flag'], ['Voters', 'voters.html', 'users'], ['Candidates', 'candidates.html', 'id'], ['Results', 'results.html', 'chart']]],
    ['Telemetry & Operations', [['Audit Logs', 'audit-logs.html', 'list'], ['Network Monitor', 'network-monitor.html', 'wifi'], ['Concurrency Lab', 'concurrency-lab.html', 'cpu'], ['System Health', 'system-health.html', 'pulse'], ['TCP Demo', 'tcp-demo.html', 'term'], ['Demonstrations', 'demonstrations.html', 'play']]],
    ['Platform Information', [['About Website', 'about-website.html', 'layers'], ['About Author', 'aboutme.html', 'id']]],
    ['Account', [['Settings', 'settings.html', 'sliders']]],
  ];
  const PUBLIC_NAV = [['Home', 'index.html'], ['Live Results', 'results.html'], ['Verify Receipt', 'vote-status.html'], ['About Website', 'about-website.html'], ['About Author', 'aboutme.html']];
  const VOTER_NAV = [['Dashboard', 'voter-dashboard.html'], ['Cast Vote', 'voting.html'], ['My Receipt', 'vote-status.html'], ['Live Results', 'results.html'], ['About Website', 'about-website.html'], ['About Author', 'aboutme.html']];
  const here = () => (location.pathname.split('/').pop() || 'index.html');
  const cur = (href) => (href === here() ? ' aria-current="page"' : '');

  function mountLayout(kind, me) {
    const main = NV.$('#main');
    main.setAttribute('tabindex', '-1');
    const skip = '<a class="skip" href="#main">Skip to content</a>';
    if (kind === 'admin') {
      const shell = document.createElement('div');
      shell.className = 'shell';
      shell.innerHTML = `${skip}<aside class="sidebar" id="sidebar" aria-label="Admin navigation">
        <a class="brand" href="admin-dashboard.html">${LOGO}<span>NetVote</span></a>
        ${ADMIN_NAV.map(([t, items]) => `<h4>${t}</h4>${items.map(([l, h, ic]) => `<a href="${h}"${cur(h)}>${icon(ic)}${l}</a>`).join('')}`).join('')}
        <h4>Session</h4><a href="#" id="logout-link">${icon('out')}Logout</a></aside>
        <div class="scrim" id="scrim"></div>
        <div class="main"><header class="topbar"><button class="btn btn-sm menu-btn" id="menu-btn" aria-label="Open navigation" aria-controls="sidebar">Menu</button>
          <strong id="topbar-title"></strong><span class="spacer"></span><span id="election-badge"></span>
          <span class="small muted">${NV.esc(me.user.name)}</span></header><div class="content" id="content"></div></div>`;
      document.body.prepend(shell);
      NV.$('#content').appendChild(main);
      NV.$('#topbar-title').textContent = (document.title.split('|')[0] || '').trim();
      const sb = NV.$('#sidebar'), sc = NV.$('#scrim');
      const toggle = (open) => { sb.classList.toggle('open', open); sc.classList.toggle('show', open); };
      NV.$('#menu-btn').addEventListener('click', () => toggle(!sb.classList.contains('open')));
      sc.addEventListener('click', () => toggle(false));
      refreshElectionBadge(); setInterval(() => !document.hidden && refreshElectionBadge(), 15000);
    } else {
      const nav = kind === 'voter' ? VOTER_NAV : PUBLIC_NAV;
      const right = kind === 'voter'
        ? `<a href="#" id="logout-link" class="nav-btn">Logout (${NV.esc(me.user ? me.user.name : '')})</a>`
        : (me.authenticated && me.user.role === 'voter' ? '<a href="voter-dashboard.html" class="nav-btn">My Dashboard</a>' : '<a href="login.html" class="nav-btn">Voter Login</a><a href="admin-login.html" style="margin-left:0.4rem;color:#bae6fd">Admin</a>');
      const head = document.createElement('div');
      head.innerHTML = `${skip}<header class="topnav"><div class="in"><a class="brand" href="index.html">${LOGO}<span>NetVote</span></a>
        <nav aria-label="Main">${nav.map(([l, h]) => `<a href="${h}"${cur(h)}>${l}</a>`).join('')}${right}</nav></div></header>`;
      const wrap = document.createElement('div');
      wrap.className = 'page';
      document.body.prepend(wrap);
      wrap.appendChild(main);
      document.body.prepend(head);
      const foot = document.createElement('footer');
      foot.className = 'foot';
      foot.innerHTML = `
        <div style="max-width:1180px;margin:0 auto;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:1.2rem;">
          <div><strong style="color:var(--ink)">NetVote</strong> &mdash; Secure, Concurrent & Network-Aware Online Voting Platform</div>
          <div style="display:flex;gap:1.2rem;flex-wrap:wrap;font-weight:500;">
            <a href="index.html">Home</a>
            <a href="results.html">Live Results</a>
            <a href="vote-status.html">Verify Receipt</a>
            <a href="about-website.html">About Website</a>
            <a href="aboutme.html">About Author</a>
          </div>
        </div>
        <div style="margin-top:1rem;color:var(--muted);font-size:0.84rem;">Designed & Engineered by <strong>Prasannadevi S</strong> &bull; Vellore Institute of Technology (VIT), Vellore</div>
      `;
      document.body.appendChild(foot);
    }
    const lo = NV.$('#logout-link');
    if (lo) lo.addEventListener('click', async (e) => { e.preventDefault(); try { await NV.api.post('/api/auth/logout'); } catch (x) { /* ignore */ } location.href = 'index.html'; });
  }

  async function refreshElectionBadge() {
    try { const r = await NV.api.get('/api/election'); const el = r.data.election; NV.$('#election-badge').innerHTML = NV.statusBadge(el.status) + ` <span class="small muted">${NV.esc(el.election_name)}</span>`; } catch (e) { /* ignore */ }
  }

  /* segmented control helper: NV.seg('#id') -> { get(): string } */
  NV.seg = (sel) => {
    const root = NV.$(sel), btns = NV.$$('button', root);
    btns.forEach((b) => b.addEventListener('click', () => btns.forEach((x) => x.setAttribute('aria-pressed', x === b))));
    return { get: () => (btns.find((b) => b.getAttribute('aria-pressed') === 'true') || btns[0]).dataset.v };
  };

  /* ---------- boot ---------- */
  async function boot() {
    const b = document.body, layout = b.dataset.layout || 'public', need = b.dataset.require;
    let me = { authenticated: false };
    try { me = (await NV.api.get('/api/auth/me')).data; } catch (e) { /* server down: pages will show errors */ }
    NV.me = me;
    if (need && (!me.authenticated || me.user.role !== need)) { goLogin(); return; }
    const role = me.authenticated ? me.user.role : null;
    const kind = layout === 'auto' ? (role === 'admin' ? 'admin' : 'public') : layout === 'auto2' ? (role === 'admin' ? 'admin' : role === 'voter' ? 'voter' : 'public') : layout;
    mountLayout(kind, me);
    const fn = NV.pages[b.dataset.page];
    if (fn) { try { await fn(); } catch (e) { NV.showError(e); } }
  }
  document.addEventListener('DOMContentLoaded', boot);
})();
