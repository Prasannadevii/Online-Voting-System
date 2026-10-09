# NetVote REST API

Base URL: `http://127.0.0.1:5000`. All bodies are JSON.

**Conventions**

* Every **write** (POST/PUT/DELETE) must send `X-Requested-With: NetVote` (CSRF defence) and `Content-Type: application/json`.
* Every response carries `X-Request-ID: REQ-YYYY-XXXXXXXX` and the same value in the JSON field `request_id`.
  A client may supply its own valid `X-Request-ID`.
* Success: `{"success": true, "request_id": "...", ...data}`
* Error: `{"success": false, "request_id": "...", "error": {"code": "...", "message": "..."}}`
* Auth is a signed, HttpOnly session cookie set by the login endpoints. `401` = not logged in, `403` = wrong role.
* Rate limits (per IP, 60 s window): **20** for login/register/vote, **300** for other endpoints -> `429` + `Retry-After`.

| Status | Meaning in NetVote |
|---|---|
| 200 / 201 | OK / created (a new vote returns 201, an idempotent replay returns 200) |
| 400 | malformed JSON, missing or invalid field |
| 401 | not authenticated / bad credentials |
| 403 | wrong role, election closed, suspended account, CSRF header missing, results not published |
| 404 | resource not found |
| 405 | invalid HTTP method |
| 409 | conflict: already voted, duplicate registration, invalid state transition, request-id conflict |
| 413 | body larger than 64 KB |
| 429 | rate limit exceeded |
| 500 | unexpected server or database error (no stack trace is returned) |
| 503 | service temporarily unavailable (lock timeout / database busy); the vote was NOT recorded |

---

## Authentication

### POST `/api/auth/register`  (public)
```json
{"voter_id":"NEW001","name":"Asha Rao","email":"asha@example.test","password":"Passw0rd1","confirm_password":"Passw0rd1"}
```
`201 {"success":true,"message":"Registration successful..."}` - errors: `400` (`MISSING_FIELDS`, `INVALID_EMAIL`, `WEAK_PASSWORD`, `PASSWORD_MISMATCH`, `INVALID_VOTER_ID`), `409` (`DUPLICATE_VOTER_ID`, `DUPLICATE_EMAIL`), `429`.

### POST `/api/auth/login`  (public)
`{"voter_id":"10012","password":"Voter@123"}` -> `200 {"role":"voter","name":"...","voter_id":"10012"}`. Errors: `401 INVALID_CREDENTIALS`, `403 ACCOUNT_SUSPENDED`, `429`.

### POST `/api/auth/admin-login`  (public)
`{"username":"admin","password":"Admin@123"}` -> `200 {"role":"admin"}`. `401` on failure.

### POST `/api/auth/logout`  (any) -> `200`
### GET `/api/auth/me`  (public) -> `{"authenticated":true,"user":{"role":"voter",...},"election_status":"ACTIVE"}`

## Election and voting

### GET `/api/election`  (public)
`{"election":{"election_name":"...","status":"ACTIVE","total_registered":20,"total_votes":5,"turnout_pct":25.0,"ledger_tail":[{"transaction_id":"VOTE-2026-00005","hash":"a1b2..."}]}}`

### GET `/api/candidates`  (public) -> `{"candidates":[{"id":1,"name":"...","party":"...","symbol":"...","color":"#2456e6","description":"..."}]}`

### GET `/api/voter/profile`  (voter) -> `{"profile":{"voter_id","name","has_voted",...},"election":{...}}`

### POST `/api/vote`  (voter)
Request:
```json
{"candidate_id": 2, "request_id": "REQ-2026-A82F91B3"}
```
`request_id` is the **idempotency key**; omit it to let the server use the request's own ID.

Response `201`:
```json
{"success":true,"transaction_id":"VOTE-2026-00006","request_id":"REQ-2026-A82F91B3","status":"confirmed",
 "timestamp":"2026-10-09T10:32:14","replayed":false,"receipt":"394d095f00a0b720","message":"Your vote has been recorded."}
```
Retry with the same `request_id` -> `200` with `"replayed": true` and the **original** transaction (no second vote).
Errors: `409 ALREADY_VOTED` (includes `transaction_id`, `voted_at`), `409 REQUEST_ID_CONFLICT`, `403 ELECTION_CLOSED`, `404 INVALID_CANDIDATE`, `400 INVALID_FIELD / INVALID_REQUEST_ID`, `503 SERVICE_BUSY / SERVICE_UNAVAILABLE`, `429`.

### GET `/api/vote/status`  (voter) -> `{"has_voted":true,"transaction_id":"...","timestamp":"...","status":"verified","request_id":"...","receipt":"..."}`

### GET `/api/verify-receipt?transaction_id=VOTE-2026-00006`  (public)
`{"found":true,"transaction_id":"...","timestamp":"...","status":"verified","hash":"394d095f00a0b720"}` - never reveals the choice or voter.

### GET `/api/results`  (admin: always; others: only when status is ENDED, else `403 RESULTS_NOT_PUBLISHED`)
`{"results":[{"id":1,"name":"...","vote_count":3,"percent":42.9,...}],"total_votes":7,"final":false,"live":true}`

## Admin  (role `admin`)

| Method & URL | Body / query | Notes |
|---|---|---|
| POST `/api/admin/election/start` \| `pause` \| `resume` \| `end` | - | `409 INVALID_STATE` for illegal transitions; start needs >= 2 active candidates |
| POST `/api/admin/election/create` | `{"election_name":"..."}` | only when no election is ACTIVE/PAUSED; **resets all ballots** |
| GET `/api/admin/voters` | `?q=&limit=&offset=` | never includes anyone's choice |
| PUT `/api/admin/voters/<voter_id>/status` | `{"status":"suspended"\|"active"}` | audited |
| GET `/api/admin/candidates` | - | includes `locked` flag |
| POST `/api/admin/candidates` | `{name,party,symbol,color,description}` | `409 CANDIDATES_LOCKED` while election runs |
| PUT `/api/admin/candidates/<id>` | same | cosmetic fields editable while running |
| DELETE `/api/admin/candidates/<id>` | - | `409 HAS_VOTES` if votes exist |
| GET `/api/admin/audit-logs` | `?action=&user=&severity=&date_from=&date_to=&limit=&offset=` | newest first |
| GET `/api/admin/settings` | - | read-only runtime configuration |
| POST `/api/admin/change-password` | `{current_password,new_password}` | |

## Monitoring  (admin; polled by dashboards, excluded from request statistics)

| URL | Returns |
|---|---|
| GET `/api/admin/dashboard` | election, candidates, network snapshot, events, concurrency, rate-limit, health, ledger check |
| GET `/api/admin/network` | `snapshot` (rps, latency percentiles, status codes, errors...), per-second `series`, limiter stats |
| GET `/api/admin/system-health` | component states, CPU/memory (psutil), uptime, DB size, last error, last vote |
| GET `/api/admin/concurrency-status` | threads, pool, vote-lock statistics, queue depth |
| GET `/api/admin/ledger-verify` | recomputes the vote hash chain and cross-checks tallies |

## Simulations  (admin; **isolated demo database**, real execution)

### POST `/api/admin/concurrency-test`
```json
{"mode":"same_voter","requests":100,"synchronization":true,"executor":"threads"}
```
`mode`: `same_voter` | `multiple_voters`; `requests`: 2-500; `executor`: `threads` | `pool`. Returns counts (`successful_votes`, `rejected_requests`, `duplicate_votes`, `lost_updates`), `race_condition` verdict, latency stats, `lock` stats and a `timeline`.

### POST `/api/admin/network-test`
`{"delay_ms":3000,"timeout_ms":2000,"burst":0}` - the server sends **real HTTP requests to itself** (`/api/sim/ping`) and reports `normal` vs `simulated` latency and status (`OK` | `DELAYED` | `TIMEOUT`). `burst` (0-300) adds concurrent requests so the monitor charts move.

### POST `/api/admin/demo/<name>`
`race-trace` `{"synchronization":bool}`, `deadlock` `{"strategy":"deadlock|lock_ordering|timeout_backoff|try_lock"}`, `starvation`, `rollback`, `retry`, `rate-limit`, `tamper`, `tcp`.

### GET `/api/sim/ping?delay=<ms>`  (public, harmless)
Sleeps up to 5000 ms and returns `{"pong":true}`; exempt from rate limiting; touches no data.
