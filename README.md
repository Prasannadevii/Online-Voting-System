# NetVote — Secure, Concurrent and Network-Aware Online Voting System

[![Python](https://img.shields.io/badge/Python-3.10%2B-0284c7.svg)](https://www.python.org/)
[![Framework](https://img.shields.io/badge/Framework-Flask%203.1-0ea5e9.svg)](https://flask.palletsprojects.com/)
[![Database](https://img.shields.io/badge/Database-SQLite%20WAL-38bdf8.svg)](https://www.sqlite.org/)
[![Tests](https://img.shields.io/badge/Tests-68%20Passing-0f7a55.svg)]()
[![Theme](https://img.shields.io/badge/Theme-Sky%20Blue-38bdf8.svg)]()

**NetVote** is a secure, high-concurrency, and network-aware electronic voting system. It combines atomic ACID transactions, cryptographic ballot integrity (SHA-256 hash chains & HMAC pseudonyms), real-time network telemetry, and multithreaded concurrency controls into a unified web platform.

* **Designed & Engineered by:** Prasannadevi S
* **Institution:** Vellore Institute of Technology (VIT), Vellore
* **Specialization:** Systems & Backend Platform Engineering
* **In-Depth Technical Manual:** See [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md)

---

## Quick Start (Windows)

```bat
# 1. Open terminal in the project directory
cd C:\Users\user\Videos\netvote\netvote

# 2. (Optional) Create virtual environment
python -m venv venv
venv\Scripts\activate

# 3. Install requirements
pip install -r requirements.txt

# 4. Seed database (creates database/voting.db with 20 voters & 5 candidates)
python database\seed.py

# 5. Launch the application
python run.py
```
Open **[http://127.0.0.1:5000](http://127.0.0.1:5000)** in your browser.

---

## Default Credentials

| Role | Username / Voter ID | Password | Notes |
|---|---|---|---|
| **Administrator** | `admin` | `Admin@123` | Full election lifecycle, telemetry & audit control |
| **Voters (Already Voted)** | `10001` ... `10005` | `Voter@123` | Pre-seeded ballots in ledger |
| **Voters (Eligible to Vote)** | `10006` ... `10020` | `Voter@123` | Ready to cast a ballot |

*Passwords are stored only as salted PBKDF2-SHA256 hashes (200,000 iterations).*

---

## Administrator System & File Verification

All administrative features and files are fully implemented and verified in the project:

### 1. Admin Web Interfaces (`frontend/`)
* **Admin Login (`admin-login.html`):** Secure access portal for election administrators.
* **Control Center Dashboard (`admin-dashboard.html`):** Real-time monitoring of turnout, live results charts, network latency percentiles, and ledger health.
* **Election Control (`election.html`):** Manage election state lifecycle (Start, Pause, Resume, End).
* **Voters Management (`voters.html`):** Search, inspect, suspend, or activate voter accounts.
* **Candidates Management (`candidates.html`):** Configure candidates, parties, symbols, and ballot colors.
* **Audit Logs Viewer (`audit-logs.html`):** Comprehensive event trail searchable by Request ID, IP, user, and action.
* **Settings & Security (`settings.html`):** System configuration, rate limit thresholds, and admin password management.
* **Telemetry & Labs:**
  * `concurrency-lab.html` — Stress-test 10–500 simultaneous threads with synchronization ON/OFF.
  * `network-monitor.html` — Live throughput (RPS), in-flight requests, and latency simulation.
  * `system-health.html` — 6-point subsystem status check and memory/CPU metrics.
  * `tcp-demo.html` — Inspect raw TCP length-prefixed socket frames.
  * `demonstrations.html` — Live demonstrations of Deadlock, Starvation, Rollback, and Tamper Detection.

### 2. Admin Backend Controllers (`backend/`)
* **`backend/routes/admin_routes.py`:** Election control, voter status updates, candidate CRUD, and audit log queries.
* **`backend/routes/monitoring_routes.py`:** Telemetry endpoints for live dashboard polling, system health, and ledger verification.
* **`backend/services/audit_service.py`:** Database logging and event persistence.
* **`backend/services/election_service.py`:** Election state machine management.

---

## Core Engineering Pillars

1. **Atomic Transactions (`BEGIN IMMEDIATE ... COMMIT/ROLLBACK`):**
   Every vote cast executes atomically: records the ballot, updates voter status, increments candidate tally, and writes the audit log. Any error triggers an immediate rollback.
2. **Mutex Concurrency Protection:**
   The `vote_lock` (`InstrumentedLock`) critical section completely eliminates race conditions and lost updates under high concurrency bursts.
3. **Idempotent Safe Retries:**
   The client generates a unique Request ID (`REQ-YYYY-XXXXXXXX`). If a request is interrupted and retried, the server returns the original receipt without creating a second ballot.
4. **Cryptographic Tamper-Evident Ledger:**
   Ballots are chained using SHA-256 hashes (`prev_hash` & `vote_hash`). Any manual database edit invalidates the cryptographic chain.
5. **HMAC Ballot Pseudonymity:**
   Voter identity is decoupled from candidate choice using a keyed cryptographic pseudonym (`voter_ref`), preserving the secret ballot.
6. **Low-Level TCP Message Framing:**
   The raw socket module implements 4-byte big-endian framing (`[Length][Payload]`) to ensure exact message boundary preservation over byte streams.

---

## Running Automated Tests

NetVote includes 68 automated unit tests covering all security, concurrency, networking, and transactional behaviors:

```bat
python -m unittest discover -s tests -t . -v
```

**Result:** `Ran 68 tests in ~50s - OK (100% Passing)`

---

## Project Structure

```
netvote/
├── app.py                      # Flask factory & middleware
├── run.py                      # Application launcher
├── config.py                   # Configuration and secret key management
├── requirements.txt            # Flask and psutil
├── DEVELOPER_GUIDE.md          # In-depth technical architecture manual
├── README.md                   # This document
│
├── backend/
│   ├── routes/                 # admin, auth, voter, voting, monitoring, simulation
│   ├── services/               # business logic & atomic operations
│   ├── database/               # schema.sql, database.py, seed.py
│   ├── concurrency/            # vote_lock, race_demo, os_demos, thread_manager
│   ├── networking/             # rate_limiter, network_monitor, tcp_demo
│   ├── security/               # hashing, auth, validation
│   └── utils/                  # helpers, transaction, logger
│
├── frontend/                   # 24 responsive HTML pages (Sky Blue theme)
│   ├── index.html              # Landing page
│   ├── about-website.html      # Comprehensive platform architecture
│   ├── aboutme.html            # Author profile (Prasannadevi S)
│   ├── admin-dashboard.html    # Control center
│   ├── voting.html             # Ballot submission
│   └── ...
│
├── static/                     # CSS, JS, fonts, and bundled vendor/chart.umd.js
└── tests/                      # 68 automated tests
```

---

## License & Attribution

Designed and engineered by **Prasannadevi S**, Vellore Institute of Technology (VIT), Vellore.
