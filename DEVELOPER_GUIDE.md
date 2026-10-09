# NetVote — Developer Guide & Engineering Manual
*A High-Concurrency, Network-Aware Electronic Voting Platform*

**Author:** Prasannadevi S  
**Institution:** Vellore Institute of Technology (VIT), Vellore  
**Specialization:** Systems & Backend Platform Engineering  

---

## Table of Contents
1. [Project Overview & Design Philosophy](#1-project-overview--design-philosophy)
2. [Admin System & File Verification](#2-admin-system--file-verification)
3. [Directory Layout](#3-directory-layout)
4. [Development Setup & Quick Start](#4-development-setup--quick-start)
5. [Database Architecture & WAL Mode](#5-database-architecture--wal-mode)
6. [Concurrency Control & Mutex Synchronization](#6-concurrency-control--mutex-synchronization)
7. [Networking & Low-Level TCP Socket Framing](#7-networking--low-level-tcp-socket-framing)
8. [Complete REST API Reference](#8-complete-rest-api-reference)
9. [Automated Testing Suite (68 Unit Tests)](#9-automated-testing-suite-68-unit-tests)
10. [Troubleshooting & Common Questions](#10-troubleshooting--common-questions)

---

## 1. Project Overview & Design Philosophy

NetVote is a client-server electronic voting platform that guarantees:
- **One Voter, One Ballot, Counted Exactly Once:** Physical prevention of double-voting and lost updates through layered defense-in-depth (in-process mutex + immediate transaction + unique database constraints).
- **Cryptographic Ballot Secrecy & Verification:** Salted HMAC pseudonyms decouple voter identities from ballot choices, while SHA-256 hash chains form a tamper-evident audit ledger.
- **Resilience Over Unreliable Networks:** Correlation Request IDs (`REQ-YYYY-XXXXXXXX`) ensure that replayed or retried HTTP requests are strictly idempotent.
- **Real-Time Telemetry:** Live requests-per-second, in-flight TCP connection tracking, and response latency percentiles (P50, P95, P99).

---

## 2. Admin System & File Verification

### Admin Credentials
* **Username:** `admin`
* **Password:** `Admin@123` (stored as PBKDF2-SHA256 salted hash)
* **Access URL:** `http://127.0.0.1:5000/admin-login.html`

### Admin Files Verification Matrix
All administrator interfaces, controllers, and services are fully verified and present in the codebase:

| Component | File Path | Purpose |
|---|---|---|
| **Admin Login** | `frontend/admin-login.html` | Secure administrative authentication entry point |
| **Admin Dashboard** | `frontend/admin-dashboard.html` | Real-time control center: turnout, charts, ledger integrity, network stats |
| **Audit Logs UI** | `frontend/audit-logs.html` | Searchable log viewer with Request ID, IP, severity, and timestamps |
| **Voters Management** | `frontend/voters.html` | Admin voter roster, suspension/activation controls |
| **Candidates Management** | `frontend/candidates.html` | Candidate creation, editing, and ballot configuration |
| **Election Control** | `frontend/election.html` | Election state machine: Start, Pause, Resume, End election |
| **System Settings** | `frontend/settings.html` | Server configurations, rate limit thresholds, admin password change |
| **Concurrency Lab** | `frontend/concurrency-lab.html` | Live stress-testing lab: 10–500 threads with/without synchronization |
| **Network Monitor** | `frontend/network-monitor.html` | Live throughput, P50/P95/P99 latency charts, simulation delays |
| **System Health** | `frontend/system-health.html` | 6-point subsystem health check, memory & CPU statistics |
| **TCP Framing Demo** | `frontend/tcp-demo.html` | Interactive raw socket protocol inspection |
| **Live Demonstrations** | `frontend/demonstrations.html` | Interactive demos: Race, Deadlock, Starvation, Rollback, Tamper |
| **Admin Routes (API)** | `backend/routes/admin_routes.py` | Admin backend endpoints (election control, candidate CRUD, voter management) |
| **Monitoring Routes (API)**| `backend/routes/monitoring_routes.py` | Polled telemetry endpoints (dashboard, network, health, ledger verify) |
| **Audit Service** | `backend/services/audit_service.py` | Database audit logging and background query service |
| **Election Service** | `backend/services/election_service.py` | State transitions and election lifecycle rules |
| **Admin JavaScript** | `static/js/admin.js` | Admin dashboard event handling, chart rendering, and data tables |

---

## 3. Directory Layout

```
netvote/
├── run.py                          # Launcher script (auto-seeds database on first run)
├── app.py                          # Flask application factory, CORS, headers & routing
├── config.py                       # Configuration loader (.env, secret key, rate limits)
├── requirements.txt                # Flask>=3.0,<4.0 and psutil>=5.9
├── DEVELOPER_GUIDE.md              # This developer manual
├── README.md                       # High-level operational manual
│
├── backend/
│   ├── routes/
│   │   ├── admin_routes.py         # /api/admin/election, /api/admin/voters, candidates
│   │   ├── auth_routes.py          # /api/auth/login, /api/auth/register, /api/auth/admin-login
│   │   ├── monitoring_routes.py    # /api/admin/dashboard, network, system-health
│   │   ├── simulation_routes.py    # /api/admin/concurrency-test, network-test, demo/*
│   │   ├── voter_routes.py         # /api/candidates, /api/voter/profile, /api/results
│   │   └── voting_routes.py        # /api/vote, /api/vote/status
│   │
│   ├── services/
│   │   ├── audit_service.py        # Centralized audit logging to SQLite
│   │   ├── auth_service.py         # Voter & Admin registration, credential verification
│   │   ├── concurrency_service.py  # Simulation orchestration & lab execution
│   │   ├── election_service.py     # Election state management & candidate tallying
│   │   ├── monitoring_service.py   # Health inspection & system metrics (psutil)
│   │   └── voting_service.py       # Atomic cast_vote, vote_status, verify_ledger
│   │
│   ├── database/
│   │   ├── database.py             # SQLite connection factory & WAL configuration
│   │   ├── schema.sql              # Relational DDL definitions & constraints
│   │   └── seed.py                 # Seed script populating development data
│   │
│   ├── concurrency/
│   │   ├── vote_lock.py            # InstrumentedLock mutex tracking wait/hold times
│   │   ├── thread_manager.py       # Bounded ThreadPoolExecutor wrapper
│   │   ├── race_demo.py            # Safe vs. unsafe vote execution testbed
│   │   └── os_demos.py             # Deadlock & starvation demonstrations
│   │
│   ├── networking/
│   │   ├── network_monitor.py      # Thread-safe in-memory metrics collector
│   │   ├── rate_limiter.py         # Sliding-window rate limiter per client IP
│   │   ├── request_manager.py      # Request lifecycle: correlation IDs, CSRF, logging
│   │   ├── tcp_demo_server.py      # Raw socket server with 4-byte message framing
│   │   └── tcp_demo_client.py      # Raw socket client & framing boundary demo
│   │
│   ├── security/
│   │   ├── auth.py                 # Flask session helpers & @login_required decorator
│   │   ├── hashing.py              # PBKDF2-SHA256 password hashing & constant-time verify
│   │   └── validation.py           # Strict server-side input schema validation
│   │
│   └── utils/
│       ├── helpers.py              # new_request_id(), ok(), fail(), ApiError
│       ├── logger.py               # Rotating file logging setup
│       └── transaction.py          # Database transaction context manager
│
├── frontend/                       # Web application pages
│   ├── index.html                  # Landing page with live ledger feed
│   ├── about-website.html          # Consolidated architecture & tech specs page
│   ├── aboutme.html                # About the Author (Prasannadevi S)
│   ├── admin-dashboard.html        # Control center dashboard
│   ├── admin-login.html            # Admin login portal
│   ├── voting.html                 # Voter ballot casting interface
│   ├── results.html                # Public election results & vote share charts
│   ├── vote-status.html            # Ballot receipt inspection & public ledger verify
│   └── ... (24 HTML templates)
│
├── static/
│   ├── css/                        # Sky Blue theme: style.css, dashboard.css, voting.css
│   ├── js/                         # core.js (API & shell), charts.js, voter.js, admin.js
│   └── vendor/                     # chart.umd.js (bundled for 100% offline support)
│
└── tests/                          # 68 automated unit tests
    ├── base.py                     # NetVoteTestCase fixture with isolated temp DB
    ├── test_auth.py                # Authentication, sessions & hashing tests
    ├── test_voting.py              # Voting workflow, duplicate detection, idempotency
    ├── test_concurrency.py         # Multi-threaded stress testing (100 simultaneous votes)
    ├── test_transactions.py        # Rollback atomicity, database error handling
    └── test_network.py             # TCP framing, sliding window rate limits, timeouts
```

---

## 4. Development Setup & Quick Start

### Prerequisites
- Python 3.10 or higher
- PowerShell, Command Prompt, or Bash

### Setup Commands
```bash
# 1. Navigate to directory
cd C:\Users\user\Videos\netvote\netvote

# 2. Setup Virtual Environment
python -m venv venv
.\venv\Scripts\activate

# 3. Install Requirements
pip install -r requirements.txt

# 4. Seed Development Database
python database\seed.py

# 5. Launch Server
python run.py
```
Open **`http://127.0.0.1:5000`** in your browser.

---

## 5. Database Architecture & WAL Mode

The system stores all state in SQLite using **Write-Ahead Logging (WAL)** mode:
```sql
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA foreign_keys=ON;
```

### Table Definitions
1. **`voters`**: Registered voters (`voter_id`, `name`, `email`, `password_hash`, `has_voted`, `status`).
2. **`admins`**: Administrative accounts (`username`, `password_hash`, `created_at`, `last_login`).
3. **`candidates`**: Ballot choices (`name`, `party`, `symbol`, `color`, `vote_count`, `status`).
4. **`votes`**: Cast ballots (`transaction_id`, `voter_ref`, `candidate_id`, `request_id`, `timestamp`, `prev_hash`, `vote_hash`).
5. **`audit_logs`**: System audit trail (`user_id`, `action`, `request_id`, `ip_address`, `timestamp`, `severity`, `status`).
6. **`requests`**: Log of handled HTTP transactions written asynchronously by background worker.
7. **`system_events`**: High-priority alerts (`SERVER_ERROR`, `RATE_LIMIT_TRIGGERED`).
8. **`election_config`**: Election state (`status` in `NOT_STARTED`, `ACTIVE`, `PAUSED`, `ENDED`).

---

## 6. Concurrency Control & Mutex Synchronization

When multiple voters submit ballots concurrently:
```
Thread 1 (Voter A) ───┐
                      ├───► [ vote_lock (Mutex) ] ───► BEGIN IMMEDIATE ───► COMMIT
Thread 2 (Voter A) ───┘           │
                                  ▼
                         Subsequent threads wait
                         (timeout: 10 seconds)
```

1. **`InstrumentedLock`**: Wraps `threading.Lock()` to record contention count, average wait time, and average hold time.
2. **Transaction Isolation**: `BEGIN IMMEDIATE` acquires SQLite's write lock immediately, preventing read-write deadlocks between processes.
3. **Defense in Depth**: Even if application-level checks fail, `UNIQUE(voter_ref)` raises `sqlite3.IntegrityError`, causing an immediate transaction rollback.

---

## 7. Networking & Low-Level TCP Socket Framing

TCP is a stream-oriented protocol without inherent message boundaries. NetVote demonstrates protocol framing in `backend/networking/tcp_demo_server.py`:

```
[ 4-byte Big-Endian Length N ][ UTF-8 Encoded Message Payload ]
Example: \x00\x00\x00\x0fHELLO|CLIENT001
```

The `recv_exact(sock, n)` loop guarantees that chunked packets are fully reassembled before parsing, preventing message fragmentation and coalescing bugs.

---

## 8. Complete REST API Reference

| Method | Endpoint | Access | Description |
|---|---|---|---|
| `POST` | `/api/auth/register` | Public | Register new voter account |
| `POST` | `/api/auth/login` | Public | Voter login (issues HttpOnly cookie) |
| `POST` | `/api/auth/admin-login` | Public | Admin login |
| `POST` | `/api/auth/logout` | Authenticated | Terminate session |
| `GET` | `/api/auth/me` | Public | Current session status |
| `GET` | `/api/candidates` | Public | Active candidate roster |
| `POST` | `/api/vote` | Voter | Cast ballot (idempotent with `request_id`) |
| `GET` | `/api/vote/status` | Voter | Check personal voting status & receipt |
| `GET` | `/api/verify-receipt` | Public | Verify ballot hash in ledger |
| `GET` | `/api/results` | Public | Election results (visible when ENDED or to admin) |
| `GET` | `/api/admin/dashboard` | Admin | Full control center metrics |
| `GET` | `/api/admin/network` | Admin | Real-time RPS & latency statistics |
| `GET` | `/api/admin/system-health` | Admin | 6-point subsystem status check |
| `POST` | `/api/admin/election/<act>` | Admin | Start, pause, resume, or end election |
| `GET` | `/api/admin/voters` | Admin | Searchable voter roster |
| `GET` | `/api/admin/audit-logs` | Admin | Filterable audit event logs |
| `POST` | `/api/admin/concurrency-test`| Admin | Run multi-threaded stress simulation |
| `GET` | `/api/admin/ledger-verify` | Admin | Audit SHA-256 hash chain validity |

---

## 9. Automated Testing Suite (68 Unit Tests)

Run the test suite from the project root:
```bash
python -m unittest discover -s tests -t . -v
```

### Key Test Cases
- **`test_concurrency.py`**: Executes 100 concurrent HTTP requests from 100 threads for the same voter. Validates that exactly 1 vote succeeds, 99 are rejected, and the database ledger has 0 duplicate records.
- **`test_transactions.py`**: Simulates mid-transaction exceptions to verify that SQLite rollback leaves no partial records. Tests Windows file-locking resolution with `RequestLogWriter.flush()`.
- **`test_network.py`**: Tests raw socket framing, partial reads, and rate limit sliding windows (HTTP 429).

---

## 10. Troubleshooting & Common Questions

* **Port 5000 in use:** Stop existing instances with `Stop-Process -Id (Get-NetTCPConnection -LocalPort 5000).OwningProcess -Force` or set `PORT=5001` in `.env`.
* **Database Reset:** Run `python database\seed.py` to reset and repopulate fictional test data.
* **Rate Limited (HTTP 429):** Default sensitive limit is 20 login/vote calls per 60 seconds per IP. Wait 60 seconds or increase `RATE_LIMIT_SENSITIVE` in `config.py`.
