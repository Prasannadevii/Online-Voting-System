/* Educational pages. The "where" fields point at real files so you can open them during a viva. */
(function () {
  'use strict';
  const { $, esc } = NV;

  const CN = [
    ['Client-Server Architecture', 'A client requests, a server responds.', 'Browser (client) calls the Flask server; the server owns all state and rules.', 'app.py, static/js/core.js', 'Browser POST /api/vote -> Flask -> SQLite -> JSON reply.'],
    ['TCP', 'Reliable, ordered byte-stream delivery between two ports.', 'HTTP between browser and Flask normally runs over TCP. The raw socket module uses TCP directly: socket, bind, listen, accept, connect, send, recv, close.', 'backend/networking/tcp_demo_server.py', 'Run the TCP Demo page and read the transcript.'],
    ['HTTP', 'Text request/response protocol with methods and status codes.', 'REST API: GET reads, POST creates/acts, PUT updates, DELETE removes. Meaningful codes: 400, 401, 403, 404, 405, 409, 429, 500, 503.', 'backend/routes/*.py', 'Second vote attempt returns 409 Conflict (ALREADY_VOTED).'],
    ['IP Address', 'Identifies a host on a network (127.0.0.1 = this machine).', 'The server binds to HOST from .env. The client IP (request.remote_addr) feeds rate limiting and audit logs.', 'config.py, request_manager.py', 'Audit rows store ip_address; the limiter counts per IP.'],
    ['Port Number', 'Identifies a service/process on a host.', 'Flask listens on port 5000. The raw TCP demo lets the OS choose a free ephemeral port (bind to port 0).', 'run.py, tcp_demo_server.py', 'http://127.0.0.1:5000 = IP + port.'],
    ['Request / Response', 'Each client request gets exactly one server response.', 'Every call is JSON in, JSON out, with a Request ID header both ways.', 'static/js/core.js (NV.api)', 'POST /api/auth/login -> 200 with session cookie.'],
    ['Application-Layer Protocol', 'Rules for messages above TCP.', 'The REST API is one. The educational TCP protocol (HELLO, AUTH, VOTE, QUIT) is another, defined by us.', 'tcp_demo_server.py', 'VOTE|1|REQ-123 -> VOTE_ACK|VOTE-2026-00007.'],
    ['Error Handling', 'Fail with the right status and a useful message, never a stack trace.', 'Central handlers map every failure to JSON {code, message, request_id}. Details go to logs/error.log only.', 'request_manager.py', 'DB busy -> 503 "Your vote has NOT been recorded. Request ID: REQ-..."'],
    ['Timeout', 'Do not wait forever.', 'Browser fetch aborts after 8 s and retries with the same Request ID; sockets use settimeout; the vote lock has a wait timeout.', 'core.js, tcp_demo_server.py, vote_lock.py', 'Network Monitor lab: 3000 ms delay vs 2000 ms timeout.'],
    ['Rate Limiting', 'Limit requests per client to protect the server.', 'Sliding window per IP: 20/min on login, register and vote; 300/min elsewhere. Returns 429 and Retry-After. This is application-level, NOT TCP congestion control.', 'rate_limiter.py', 'The 21st login in a minute returns HTTP 429.'],
    ['Message Framing', 'TCP has no message boundaries.', 'Length-prefixed frames [4-byte length][payload] plus recv_exact() loop; a maximum frame size guards memory.', 'tcp_demo_server.py', 'Two send() calls arrive in one recv(): the TCP Demo page proves it.'],
    ['Connection Management', 'Open, use, close connections and track them.', 'Werkzeug serves each connection on its own thread; the monitor tracks in-flight requests; sockets are closed in finally blocks; SO_REUSEADDR allows quick restarts.', 'network_monitor.py', 'Active connections tile rises during a traffic burst.'],
  ];
  const OS = [
    ['Process', 'A running program with its own address space.', 'The Flask server is one process. The TCP demo can run as a second process. Separate processes do NOT share the Python lock, so SQLite BEGIN IMMEDIATE protects across processes.', 'Two servers writing the same DB file.', 'Single-process deployment (use_reloader=False) plus DB-level locking.'],
    ['Thread', 'A unit of execution inside a process sharing its memory.', 'Werkzeug creates one thread per connection; the lab creates up to 500 threads; the log writer is a daemon thread.', 'threading.active_count() on the System Health page.', 'Thread pool and bounded queues limit resource use.'],
    ['Multithreading', 'Several threads making progress concurrently.', 'Many voters hit /api/vote at once. Python threads interleave on I/O, so races are real even with the GIL.', 'Concurrency Lab with 100 threads.', 'Synchronise every shared read-modify-write.'],
    ['Race Condition', 'Result depends on timing of unsynchronised threads.', 'check has_voted, then insert. Two threads can pass the check together.', 'Lab with synchronization DISABLED: duplicates and lost updates.', 'Mutex + transaction + UNIQUE constraint (defence in depth).'],
    ['Critical Section', 'Code that touches shared state and must run exclusively.', 'The whole check-then-insert-then-update block inside cast_vote().', 'voting_service._critical_section()', 'Keep it short and take the lock only around it.'],
    ['Mutex', 'Lock allowing one holder at a time.', 'InstrumentedLock wraps threading.Lock and counts contention.', 'with vote_lock: ...', 'Use "with" so the lock is always released, even on exceptions.'],
    ['Synchronization', 'Coordinating threads so shared data stays correct.', 'Mutex for threads, BEGIN IMMEDIATE for processes, Barrier in the lab to release all threads at once, Queue for the log writer.', 'race_demo.py uses threading.Barrier.', 'Right tool per level: thread, process, database.'],
    ['Deadlock', 'Threads wait for each other in a cycle forever.', 'Demo: A holds R1 wanting R2, B holds R2 wanting R1. The real vote path uses exactly one lock.', 'Demonstrations -> Deadlock.', 'Lock ordering, timeouts with back-off, try-lock.'],
    ['Starvation', 'A thread never gets the resource.', 'Strict priority scheduling starves a low-priority job. The vote lock acquire has a 10 s timeout, so requests fail fast with 503.', 'Demonstrations -> Starvation.', 'FIFO, aging, bounded waits.'],
    ['Resource Sharing', 'Many consumers share limited resources.', 'The SQLite file, the vote lock, the CPU and the worker pool are shared; WAL mode lets readers continue while one writer commits.', 'database.py', 'Per-thread connections, short transactions, busy timeout.'],
    ['Transaction', 'A group of operations treated as one unit.', 'Insert vote + mark voter + update counter + audit row.', 'utils/transaction.py', 'BEGIN IMMEDIATE ... COMMIT, ROLLBACK on error.'],
    ['Atomicity', 'All or nothing.', 'If anything fails after inserting the vote, the insert disappears too.', 'Demonstrations -> Transaction Rollback.', 'The transaction manager; verified by tests.'],
  ];
  const SECURITY = [
    ['Password hashing', 'Salted PBKDF2-SHA256 via Werkzeug; plaintext never stored or logged; dummy hash on unknown users to reduce timing leaks.'],
    ['Input validation', 'Server-side checks for every field (type, length, format) and JSON schema; the browser is never trusted.'],
    ['SQL parameterization', 'Every query uses ? placeholders; no string-built SQL with user input.'],
    ['Authentication', 'Signed, HttpOnly, SameSite=Lax session cookies; 30-minute lifetime; session cleared on login (fixation defence).'],
    ['Authorization', 'Role checks per endpoint: 401 if not logged in, 403 if the role is wrong. Pages are public files; the API enforces access.'],
    ['Duplicate-vote prevention', 'Mutex + transaction + UNIQUE(voter_ref) + idempotent Request IDs.'],
    ['Transaction safety', 'All vote effects commit or roll back together.'],
    ['Audit logging', 'Logins, votes, rejections, admin actions, rate-limit hits, timeouts - all with Request ID and IP.'],
    ['Rate limiting', 'Per-IP sliding window; 429 + Retry-After; flagged once per window in the audit log.'],
    ['Request tracing', 'REQ-YYYY-XXXXXXXX id on every request, log line, audit row and error message.'],
    ['Ballot pseudonymity', 'votes store an HMAC reference instead of the voter ID; admin screens never show choices.'],
    ['Tamper-evident ledger', 'SHA-256 hash chain over votes with a verifier (detects edits; does not prevent them).'],
    ['CSRF and browser hardening', 'Custom X-Requested-With header required on writes; CSP forbids inline scripts; X-Frame-Options DENY; nosniff.'],
  ];
  const LIMITS = [
    'This is an academic demonstration. It is NOT certified or suitable for real elections.',
    'HTTP only on localhost. A real deployment needs HTTPS/TLS (use a reverse proxy or certificate).',
    'The vote lock protects one process. Several server processes rely on SQLite locking, not on the Python lock.',
    'SQLite is single-writer. A real system would use a server database and replication.',
    'No strong voter identity proofing (no government ID, no MFA); email is not verified.',
    'Ballot secrecy is limited: the server can link a pseudonym to a choice if it holds the secret key. Real systems use cryptographic voting.',
    'In-memory network statistics reset when the server restarts.',
    'The hash chain is tamper-evident only; someone who can rewrite the whole chain and the tallies can still cheat.',
    'Rate limits are per IP, so users behind one NAT share a bucket.',
  ];
  const ARCH = [
    { id: 'browser', n: 'Browser (client)', p: 'Renders pages, sends HTTP requests with a Request ID, retries safely, shows friendly errors.', t: 'HTML, CSS, vanilla JS, Chart.js, fetch + AbortController', cn: 'Client side of client-server, HTTP request/response, timeouts, idempotent retries', os: 'Runs as a separate process on the voter\'s machine', f: 'static/js/core.js' },
    { id: 'flask', n: 'Flask server', p: 'Accepts connections, routes requests, applies rate limits, security headers, error handling.', t: 'Python 3, Flask, Werkzeug threaded server', cn: 'HTTP over TCP, IP + port, status codes, rate limiting (429)', os: 'One thread per connection, shared process memory', f: 'app.py, backend/networking/request_manager.py' },
    { id: 'auth', n: 'Authentication', p: 'Registers voters, verifies passwords, creates sessions, enforces roles.', t: 'Werkzeug PBKDF2, Flask signed sessions', cn: 'Stateless HTTP made stateful with cookies; 401 vs 403', os: 'CPU-bound hashing runs on request threads', f: 'backend/services/auth_service.py, backend/security/' },
    { id: 'voting', n: 'Voting service', p: 'The transactional vote: checks, insert, tally, audit, idempotency, hash chain.', t: 'Python + SQLite transactions', cn: 'Idempotent request IDs for reliable retries over unreliable networks', os: 'Critical section, atomic transaction', f: 'backend/services/voting_service.py' },
    { id: 'conc', n: 'Concurrency manager', p: 'Instrumented mutex, thread pool, race/deadlock/starvation labs on isolated demo data.', t: 'threading.Lock, ThreadPoolExecutor, Barrier', cn: 'Handling many simultaneous client requests', os: 'Mutex, race condition, deadlock, starvation, thread pool', f: 'backend/concurrency/' },
    { id: 'net', n: 'Network monitor', p: 'Counts and times every API request: rps, latency percentiles, errors, in-flight connections.', t: 'In-memory thread-safe counters', cn: 'Throughput, latency, reliability, status-code distribution', os: 'Shared counters protected by a lock', f: 'backend/networking/network_monitor.py' },
    { id: 'audit', n: 'Audit logger', p: 'Records who did what, from where, tied to a Request ID.', t: 'SQLite audit_logs + rotating log files; background queue writer', cn: 'Tracing across client, server and database', os: 'Producer-consumer queue; file I/O off the request path', f: 'backend/services/audit_service.py' },
    { id: 'db', n: 'SQLite database', p: 'Durable storage with constraints, indexes and WAL journaling.', t: 'SQLite 3, WAL mode, foreign keys', cn: 'Server-side state shared by all clients', os: 'File locking, ACID transactions, per-thread connections', f: 'backend/database/schema.sql' },
  ];
  const SCHEMA = [
    ['voters', 'id, voter_id (unique), name, email (unique), password_hash, has_voted, created_at, last_login, status'],
    ['admins', 'id, username (unique), password_hash, created_at, last_login'],
    ['candidates', 'id, name, party, symbol, color, description, vote_count, status'],
    ['votes', 'id, transaction_id (unique), voter_ref (unique pseudonym), candidate_id (FK), request_id (unique), timestamp, status, prev_hash, vote_hash'],
    ['audit_logs', 'id, user_id, action, request_id, ip_address, user_agent, timestamp, details, severity, status'],
    ['requests', 'id, request_id, request_type, user_id, status, response_code, created_at, completed_at, processing_time_ms, ip_address'],
    ['system_events', 'id, event_type, severity, message, timestamp'],
    ['election_config', 'id, election_name, start_time, end_time, status, total_registered, total_votes'],
  ];
  const VIVA = [
    ['OS', 'What is a race condition?', 'It happens when several threads access shared data and the result depends on the order they run. In NetVote: two requests for the same voter both read has_voted=false and both insert a vote.'],
    ['OS', 'How does your system prevent it?', 'The vote operation is a critical section protected by threading.Lock (with vote_lock), executed inside BEGIN IMMEDIATE ... COMMIT, backed by a UNIQUE constraint on voter_ref.'],
    ['OS', 'What is a critical section?', 'Code that accesses shared resources and must not be executed by more than one thread at a time. Ours is _critical_section() in voting_service.py.'],
    ['OS', 'What is a mutex and how is it different from a semaphore?', 'A mutex is a lock owned by one thread at a time. A semaphore is a counter allowing up to N holders (a mutex is like a binary semaphore without ownership rules).'],
    ['OS', 'Why use "with lock" instead of acquire/release?', 'The context manager guarantees release even if an exception occurs, preventing a permanently locked mutex (which would stall every voter).'],
    ['OS', 'What is deadlock and the four Coffman conditions?', 'Threads wait on each other in a cycle forever. Needs mutual exclusion, hold-and-wait, no pre-emption and circular wait. Our vote path holds one lock only, so no cycle exists.'],
    ['OS', 'How can deadlock be prevented?', 'Break one condition: global lock ordering (no circular wait), try-lock / release-and-retry (no hold-and-wait), or timeouts. All are shown in the Deadlock demo.'],
    ['OS', 'What is starvation?', 'A thread is repeatedly denied a resource. Example in the demo: strict priority scheduling. Fixes: FIFO or aging. Our lock waits have a timeout so requests fail fast with 503.'],
    ['OS', 'Process vs thread?', 'A process has its own address space; threads share the process memory. NetVote runs request threads inside one server process, which is why a threading.Lock is sufficient there.'],
    ['OS', 'Does the Python GIL remove race conditions?', 'No. The GIL protects interpreter internals, but threads can switch between bytecodes and during I/O, so check-then-act sequences still race. The lab proves it with duplicate votes.'],
    ['OS', 'What is a thread pool and why use one?', 'A fixed set of worker threads executing queued tasks. It bounds resource use and avoids per-task thread creation cost. See WorkerPool and the pool mode in the lab.'],
    ['OS', 'What is a lost update?', 'Two threads read the same counter value, each add 1, and write back the same result, losing one increment. The unsafe lab shows candidate counters falling behind the ledger.'],
    ['OS', 'What is atomicity?', 'All steps of an operation happen or none do. A failure after inserting the vote triggers ROLLBACK so no partial vote remains (Transaction Rollback demo).'],
    ['OS', 'Explain producer-consumer in your project.', 'Request threads put log rows on a Queue; one background thread consumes them and writes to SQLite in batches, keeping disk writes off the request path.'],
    ['OS', 'What does WAL mode do?', 'Write-ahead logging lets readers continue while a writer commits and improves concurrent performance in SQLite.'],
    ['CN', 'Where is TCP used in your project?', 'HTTP between browser and Flask runs over TCP. Additionally the TCP demo uses raw sockets: socket, bind, listen, accept, connect, send, recv, close.'],
    ['CN', 'Why does TCP need message framing?', 'TCP is a byte stream: it preserves order but not boundaries. Two sends may arrive in one recv. We prefix each message with a 4-byte length and loop until all bytes arrive.'],
    ['CN', 'What happens if a vote request is retried?', 'The client reuses the same Request ID. The server finds it in votes.request_id and returns the original result with replayed=true; no second vote is created.'],
    ['CN', 'What is idempotency?', 'Performing an operation several times has the same effect as once. Essential because networks can lose a response even after the server committed the vote.'],
    ['CN', 'HTTP status codes you used and why?', '201 created, 400 malformed, 401 not logged in, 403 forbidden, 404 not found, 409 conflict (already voted), 429 too many requests, 500 server error, 503 temporarily unavailable.'],
    ['CN', 'Explain your rate limiting. Is it TCP congestion control?', 'No. TCP congestion control is inside the kernel. Ours is application-level: a sliding window per IP (20 sensitive requests/minute) that returns 429. It protects against floods and password guessing.'],
    ['CN', 'What is a timeout and where do you use it?', 'A limit on waiting. Browser fetch (8 s) with safe retry, socket settimeout in the TCP server, and lock-acquire timeout on the server.'],
    ['CN', 'What is a Request ID and why have it?', 'A unique id per request (REQ-2026-XXXXXXXX) appearing in logs, audit rows and error messages so one exchange can be traced end to end.'],
    ['CN', 'Difference between 401 and 403?', '401: not authenticated (no valid login). 403: authenticated but not allowed (e.g. a voter calling an admin endpoint).'],
    ['CN', 'What is the difference between IP address and port?', 'The IP identifies the host; the port identifies the service on it. 127.0.0.1:5000 is localhost, port 5000.'],
    ['CN', 'What is the client-server model?', 'Clients initiate requests; the server owns the data and rules. The browser never decides whether a vote is valid.'],
    ['CN', 'What is the TCP three-way handshake and where does it appear?', 'SYN, SYN-ACK, ACK establish a connection. connect() on the client and accept() on the server complete it; the TCP demo shows connect().'],
    ['CN', 'What is CSRF and how do you mitigate it?', 'A malicious site makes the user\'s browser send a request with their cookie. We require a custom X-Requested-With header (not sendable cross-site without CORS) and use SameSite=Lax cookies.'],
    ['Project', 'How do you keep ballots secret while preventing double voting?', 'votes stores an HMAC pseudonym, not the voter ID, and the UI never shows choices. Limitation: whoever holds the server secret could re-derive links; real systems use cryptography.'],
    ['Project', 'What is the hash chain?', 'Each vote\'s hash covers the previous vote\'s hash. Changing any vote breaks all later hashes, so verification detects edits (tamper-evident, not tamper-proof).'],
    ['Project', 'Is the concurrency lab dangerous for the real election?', 'No. It runs on a throw-away temp database. The unsafe function refuses the real database path and the production vote path has no unsafe switch.'],
    ['Project', 'How are the dashboard numbers real?', 'The network monitor records each request; the lab runs real threads; health reads real DB and process state. Nothing is random.'],
    ['Project', 'What are the main limitations?', 'Not production-grade: HTTP only, SQLite, weak identity proofing, single-process lock, limited ballot secrecy. See the Security page.'],
  ];

  NV.pages['cn-concepts'] = () => {
    $('#cards').innerHTML = CN.map((c, i) => `<article class="card concept"><h3><span>${esc(c[0])}</span>${NV.badge(String(i + 1), 'navy')}</h3><p><strong>${esc(c[1])}</strong></p><dl><dt>HOW WE IMPLEMENT IT</dt><dd>${esc(c[2])}</dd><dt>WHERE IT IS USED</dt><dd><code>${esc(c[3])}</code></dd><dt>EXAMPLE</dt><dd>${esc(c[4])}</dd></dl></article>`).join('');
  };
  NV.pages['os-concepts'] = () => {
    $('#cards').innerHTML = OS.map((c, i) => `<article class="card concept"><h3><span>${esc(c[0])}</span>${NV.badge(String(i + 1), 'navy')}</h3><dl><dt>DEFINITION</dt><dd>${esc(c[1])}</dd><dt>HOW IT APPEARS IN NETVOTE</dt><dd>${esc(c[2])}</dd><dt>EXAMPLE</dt><dd>${esc(c[3])}</dd><dt>HOW WE PREVENT PROBLEMS</dt><dd>${esc(c[4])}</dd></dl></article>`).join('');
  };
  NV.pages.security = () => {
    $('#impl').innerHTML = SECURITY.map((s) => `<li><span class="tick">&#10003;</span><div><strong>${esc(s[0])}</strong><div class="small muted">${esc(s[1])}</div></div></li>`).join('');
    $('#limits').innerHTML = LIMITS.map((s) => `<li><span style="color:var(--amber);font-weight:700">!</span><div class="small">${esc(s)}</div></li>`).join('');
  };
  NV.pages.about = () => {
    $('#arch').innerHTML = `<button class="arch-node" data-id="browser" aria-pressed="false">Browser</button><div class="arch-wire">| HTTP request (Request ID, JSON) over TCP |</div><button class="arch-node" data-id="flask" aria-pressed="false">Flask server</button><div class="arch-wire">|</div>
      <div class="arch-row"><button class="arch-node" data-id="auth" aria-pressed="false">Authentication</button><button class="arch-node" data-id="voting" aria-pressed="false">Voting service</button><button class="arch-node" data-id="conc" aria-pressed="false">Concurrency manager</button><button class="arch-node" data-id="net" aria-pressed="false">Network monitor</button><button class="arch-node" data-id="audit" aria-pressed="false">Audit logger</button></div>
      <div class="arch-wire">| parameterised SQL inside transactions |</div><button class="arch-node" data-id="db" aria-pressed="false">SQLite database</button><div class="arch-wire small">voters &middot; candidates &middot; votes &middot; audit_logs &middot; requests &middot; system_events &middot; election_config</div>`;
    const show = (id) => {
      const a = ARCH.find((x) => x.id === id);
      NV.$$('.arch-node').forEach((b) => b.setAttribute('aria-pressed', b.dataset.id === id));
      $('#arch-detail').innerHTML = `<h2>${esc(a.n)}</h2><dl class="kv" style="grid-template-columns:1fr"><dt>Purpose</dt><dd>${esc(a.p)}</dd><dt>Technology</dt><dd>${esc(a.t)}</dd><dt>Computer Networks concept</dt><dd>${esc(a.cn)}</dd><dt>Operating Systems concept</dt><dd>${esc(a.os)}</dd><dt>Open this file</dt><dd><code>${esc(a.f)}</code></dd></dl>`;
    };
    NV.$$('.arch-node').forEach((b) => b.addEventListener('click', () => show(b.dataset.id)));
    show('flask');
    $('#schema').innerHTML = `<div class="table-wrap"><table><thead><tr><th>Table</th><th>Columns</th></tr></thead><tbody>${SCHEMA.map((s) => `<tr><td><strong>${s[0]}</strong></td><td class="small">${esc(s[1])}</td></tr>`).join('')}</tbody></table></div>`;
  };
  NV.pages.viva = () => {
    const draw = (f) => { $('#qa').innerHTML = VIVA.filter((q) => f === 'all' || q[0] === f).map((q, i) => `<details class="qa"><summary><span class="badge b-${q[0] === 'CN' ? 'blue' : q[0] === 'OS' ? 'green' : 'amber'}">${q[0]}</span><span>${esc(q[1])}</span></summary><p>${esc(q[2])}</p></details>`).join(''); };
    const seg = NV.seg('#viva-filter'); NV.$$('#viva-filter button').forEach((b) => b.addEventListener('click', () => draw(seg.get())));
    draw('all');
  };
})();
