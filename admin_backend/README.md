# Admin Backend Module

> **INTEGRATION STATUS: CONNECTED & ACTIVE**
> This module is connected to the primary application backend in [`api/main.py`](file:///c:/Projects/Multi-agent-research-platform/api/main.py).
> The admin router is mounted on FastAPI (accessible at `/api/admin` and `/admin`), and request telemetry,
> trace collection, metric aggregation, and guardrail safety logging are actively hooked into the request lifecycle.

---

## 1. Executive Summary & Capabilities

This module allows authorized platform administrators to answer four fundamental operational questions without compromising security, privacy, or system performance:

1. **Is the platform healthy?**
   - Detailed dependency probes evaluate actual reachability and round-trip latency for Redis, PostgreSQL (including pgvector), Groq LLM API, local Ollama daemon, and Tavily search.
   - Reports exact failure causes without labeling unverified services healthy.
2. **Is the output good?**
   - Ingests and aggregates historical LLM-as-a-judge scoring data (`logs/scores.jsonl`).
   - Identifies low-scoring reports, failed grading attempts, and heuristic indications of truncated outputs.
   - Distinctly isolates automated evaluation scores from human reviewer submissions.
3. **Is the system safe?**
   - Stores and audits blocked inputs/outputs, jailbreak attempts, toxic language detections, and indirect prompt-injection sanitizations (XPIA).
   - Ingests offline PyRIT red-team results (`logs/redteam_results.json`) while maintaining strict separation from live production telemetry.
   - Enforces privacy-conscious excerpt limits and PII masking.
4. **What data is stored?**
   - Provides safe management interfaces for PostgreSQL long-term memory (LTM), Redis semantic cache entries, and short-term conversation sessions.
   - Enforces explicit double-confirmation safeguards (`?confirm=true` or `X-Confirm-Destructive: true`) and mandatory audit logging for all deletion and invalidation operations.
   - Restricts session inspection to metadata (turn count, role, TTL) to protect conversation confidentiality.

---

## 2. Architecture & File Structure

```
admin_backend/
├── __init__.py                 # Safe package entrypoint (zero side-effects on import)
├── config.py                   # Pydantic BaseSettings for admin configuration
├── router.py                   # Master APIRouter uniting all administrative sub-routers
├── security/                   # Authentication, cryptographic tokens, RBAC, rate-limiting
│   ├── __init__.py
│   ├── passwords.py            # PBKDF2-HMAC-SHA256 password hashing (600,000 iterations)
│   ├── tokens.py               # HS256 JWT-compatible signed bearer tokens (standard library)
│   ├── rate_limiter.py         # In-memory sliding-window rate limiter per client
│   └── dependencies.py         # FastAPI Depends: require_admin_role, require_destructive_confirmation
├── models/                     # Strongly-typed Pydantic schemas
│   ├── __init__.py
│   ├── auth.py                 # UserRecord, LoginRequest, TokenResponse, ProvisionRequest
│   ├── audit.py                # AuditLogEntry, AuditLogFilter, AuditAction enum
│   ├── health.py               # DetailedSystemHealth, DependencyCheckResult, ServiceStatus
│   ├── metrics.py              # RequestMetric, MetricsSummary, LatencyPercentiles
│   ├── quality.py              # JudgeScoreRecord, HumanReviewScore, QualitySummary
│   ├── traces.py               # RequestTrace, AgentStepRecord, AgentStepType enum
│   ├── safety.py               # SafetyEvent, RedTeamRunSummary, GuardCheckType enum
│   ├── memory_cache.py         # LTMReportItem, CacheEntryItem, SessionMetadataItem, DestructiveActionResult
│   ├── config_schemas.py       # Read-only draft blueprints for future dynamic settings
│   └── cost.py                 # TokenUsageRecord with exact vs estimated cost markers
├── services/                   # Business logic and external dependency adapters
│   ├── __init__.py
│   ├── audit_service.py        # Append-only audit logging with PII/secret redaction
│   ├── health_service.py       # Non-crashing probes for Redis, Postgres, Groq, Ollama, Tavily
│   ├── metrics_service.py      # Telemetry aggregation (avg, min, max, p50, p90, p95, p99 latencies)
│   ├── quality_service.py      # Judge log parsing, heuristic truncation detector, human reviews
│   ├── trace_service.py        # Trace collector & pipeline instrumentation hooks
│   ├── safety_service.py       # Blocked event recorder and offline red-team parser
│   ├── memory_cache_service.py # Safe lazy memory/cache adapter (no import side-effects)
│   ├── gateway_adapter.py      # Non-intrusive wrapper capturing LLM latency, model, and fallback
│   └── export_service.py       # CSV and JSON streaming exports
├── storage/                    # Storage repository interfaces and standalone implementations
│   ├── __init__.py
│   ├── interfaces.py           # Abstract repository contracts (User, Audit, Trace, Safety, Metric)
│   └── in_memory.py            # Thread-safe in-memory implementations for review and testing
├── migrations/
│   └── 001_admin_tables.sql    # Unexecuted PostgreSQL DDL for production persistence
├── routes/                     # FastAPI route controllers
│   ├── __init__.py
│   ├── auth_routes.py          # /admin/auth/login, /admin/auth/me, /admin/auth/provision-initial-admin
│   ├── health_routes.py        # GET /admin/health
│   ├── metrics_routes.py       # GET /admin/metrics/summary, GET /admin/metrics/latency
│   ├── quality_routes.py       # GET /admin/quality/scores, GET /admin/quality/summary, POST /admin/quality/human-reviews
│   ├── trace_routes.py         # GET /admin/traces, GET /admin/traces/{request_id}
│   ├── safety_routes.py        # GET /admin/safety/events, GET /admin/safety/redteam
│   ├── memory_routes.py        # GET/DELETE /admin/memory/reports, GET/DELETE /admin/memory/cache, GET /admin/memory/sessions
│   ├── config_routes.py        # GET /admin/config/draft
│   ├── export_routes.py        # GET /admin/export/scores/csv, GET /admin/export/scores/json
│   └── audit_routes.py         # GET /admin/audit/logs
├── tests/                      # Isolated pytest suite (100% offline, zero database side-effects)
│   ├── __init__.py
│   ├── conftest.py             # Fixtures and test harness
│   ├── test_security.py        # Password hashing, token signing, tampering rejection, rate limits
│   ├── test_health.py          # Probes with mocked states (healthy, unreachable, degraded)
│   ├── test_metrics.py         # Percentiles calculation, aggregations, time-range filters
│   ├── test_quality.py         # Log parser, truncation detection heuristics, human review separation
│   ├── test_traces.py          # TraceCollector, agent step context manager, privacy redactions
│   ├── test_safety.py          # Safety event truncation, red-team summary parsing
│   ├── test_memory_cache.py    # Cache invalidation, clear, LTM deletion, audit generation
│   └── test_routes.py          # FastAPI TestClient endpoint authorization and confirmation tests
└── README.md                   # This documentation file
```

---

## 3. Security & Access Control Model

### Authentication & Token Architecture
- **Password Hashing**: Implemented in [`admin_backend/security/passwords.py`](file:///c:/Projects/Multi-agent-research-platform/admin_backend/security/passwords.py) using PBKDF2-HMAC-SHA256 with 600,000 iterations (OWASP compliant) and cryptographically secure random salts. Comparisons use constant-time `hmac.compare_digest` to prevent timing attacks.
- **Signed Tokens**: Implemented in [`admin_backend/security/tokens.py`](file:///c:/Projects/Multi-agent-research-platform/admin_backend/security/tokens.py) using HMAC-SHA256 signatures with base64url encoding. Requires zero external C-dependencies or PyJWT libraries. Tokens contain user ID (`sub`), `username`, `role`, `iat`, `exp`, and unique `jti`.
- **Role-Based Access Control (RBAC)**: Enforced via `require_admin_role` dependency on every administrative route. Regular users receive `403 Forbidden`.
- **Rate Limiting**: Sliding-window rate limiter in [`admin_backend/security/rate_limiter.py`](file:///c:/Projects/Multi-agent-research-platform/admin_backend/security/rate_limiter.py) configured to limit requests per minute per IP address.
- **Zero Hardcoded Secrets**: If `ADMIN_SECRET_KEY` is not supplied via `.env`, an ephemeral secret is generated at runtime with a logged warning.

### Destructive Action Safeguards
Destructive endpoints (cache invalidation, bulk cache clearing, and report deletion from long-term memory) require callers to explicitly supply:
- Query parameter: `?confirm=true`, or
- HTTP header: `X-Confirm-Destructive: true`

Requests lacking explicit confirmation are blocked with `400 Bad Request`. Every executed destructive action is immutably recorded by the audit logger.

---

## 4. Endpoint Specifications

Every administrative endpoint (except `/admin/auth/login` and `/admin/auth/provision-initial-admin`) requires:
```http
Authorization: Bearer <ADMIN_TOKEN>
```

| Path | Method | Access | Description |
|---|---|---|---|
| `/admin/auth/login` | `POST` | Public | Authenticates credentials and issues signed token. |
| `/admin/auth/me` | `GET` | User/Admin | Returns current user identity and role. |
| `/admin/auth/provision-initial-admin` | `POST` | Protected | Creates first admin account using `ADMIN_PROVISIONING_TOKEN`. |
| `/admin/health` | `GET` | Admin | Probes actual status of Redis, Postgres, Groq, Ollama, and Tavily. |
| `/admin/metrics/summary` | `GET` | Admin | Aggregated metrics (requests, errors, cache hits, fallbacks, search calls). |
| `/admin/metrics/latency` | `GET` | Admin | Percentiles (min, max, avg, p50, p90, p95, p99) over 1h, 24h, 7d, all. |
| `/admin/quality/scores` | `GET` | Admin | Paginated judge scores with low-score, failed, and truncation filters. |
| `/admin/quality/summary` | `GET` | Admin | Summary of relevance, accuracy, clarity averages, and failure counts. |
| `/admin/quality/human-reviews` | `POST` | Admin | Records a human review score. |
| `/admin/quality/human-reviews` | `GET` | Admin | Lists all human reviews. |
| `/admin/traces` | `GET` | Admin | Paginated query traces with outcome, session, and duration filters. |
| `/admin/traces/{request_id}` | `GET` | Admin | Full trace showing execution timeline of Search, Summarize, Write, Verify, Modify, Answer. |
| `/admin/safety/events` | `GET` | Admin | Blocked requests, prompt injection, and toxicity events with truncated excerpts. |
| `/admin/safety/redteam` | `GET` | Admin | Summary of PyRIT red-team attack evaluations. |
| `/admin/memory/reports` | `GET` | Admin | Lists and searches reports stored in PostgreSQL long-term memory. |
| `/admin/memory/reports/{report_id}` | `DELETE` | Admin + Confirm | Deletes a report from long-term memory. |
| `/admin/memory/cache` | `GET` | Admin | Lists active non-expired semantic cache entries in Redis. |
| `/admin/memory/cache/{entry_id}` | `DELETE` | Admin + Confirm | Invalidates an individual semantic cache entry in Redis. |
| `/admin/memory/cache/clear` | `POST` | Admin + Confirm | Flushes all semantic cache keys in Redis. |
| `/admin/memory/sessions` | `GET` | Admin | Lists active session metadata (turn count, TTL) without exposing messages. |
| `/admin/config/draft` | `GET` | Admin | Inspects draft system limits and parameters (read-only blueprint). |
| `/admin/export/scores/csv` | `GET` | Admin | Exports evaluation scores as downloadable CSV file. |
| `/admin/export/scores/json` | `GET` | Admin | Exports evaluation scores as formatted JSON. |
| `/admin/audit/logs` | `GET` | Admin | Queries administrative audit trail by actor, action, and date range. |

---

## 5. Environment Variables & Configuration

The admin module reads configuration from `.env` or system environment variables:

| Variable | Type | Default | Description |
|---|---|---|---|
| `ADMIN_SECRET_KEY` | `string` | *(Ephemeral)* | Secret key used for signing HS256 tokens. Set a secure random 32-byte hex string in production. |
| `ADMIN_TOKEN_EXPIRE_MINUTES` | `int` | `60` | Lifespan of issued administrator access tokens. |
| `ADMIN_RATE_LIMIT_PER_MINUTE` | `int` | `120` | Max admin API requests allowed per minute per client IP. |
| `ADMIN_PROVISIONING_TOKEN` | `string` | `None` | Secret one-time key required to provision the initial administrator account. |
| `ADMIN_AUDIT_LOG_PATH` | `string` | `logs/admin_audit.jsonl` | Append-only path for administrator action audit logs. |
| `ADMIN_DATA_RETENTION_DAYS` | `int` | `30` | Default retention timeframe for telemetry data. |
| `ADMIN_MAX_PREVIEW_LENGTH` | `int` | `160` | Maximum length of text previews to prevent leaking sensitive payloads. |
| `ADMIN_MASK_PII` | `bool` | `true` | When true, regex masks email addresses and phone numbers in trace previews. |

---

## 6. Migration Plan

A production-ready database schema has been prepared in [`admin_backend/migrations/001_admin_tables.sql`](file:///c:/Projects/Multi-agent-research-platform/admin_backend/migrations/001_admin_tables.sql).

### Tables Defined:
1. `admin_users` — Persistent administrator and user accounts with hashed credentials.
2. `admin_audit_logs` — Immutable audit trail with actor, action, target resource, outcome, and client IP.
3. `admin_request_traces` — Telemetry for request durations, intent, cache status, sources, outcome, and errors.
4. `admin_agent_steps` — Granular execution step records for each LangGraph agent node.
5. `admin_safety_events` — Records of input/output guardrail violations and XPIA sanitizations.
6. `admin_human_reviews` — Human assessment records kept distinct from automated judge scores.

*Note: In accordance with project boundaries, this migration has not been applied to the database.*

---

## 7. Deferred Integration Steps

To activate this admin backend in the primary application in the future, the following exact changes outside `admin_backend/` will be required:

### 1. Mount the Admin Router in `api/main.py`
In [`api/main.py`](file:///c:/Projects/Multi-agent-research-platform/api/main.py):
```python
# Add import:
from admin_backend.router import admin_router

# Mount the router before the static files UI mount at line 160:
app.include_router(admin_router, prefix="/api")
```

### 2. Instrument Request Traces in `api/main.py`
In [`api/main.py:generate()`](file:///c:/Projects/Multi-agent-research-platform/api/main.py#L75-L150):
```python
from admin_backend.services.trace_service import trace_service
from admin_backend.services.metrics_service import metrics_service

# At start of generate():
trace = trace_service.start_trace(request_id=str(uuid.uuid4()), session_id=session_id, topic=req.topic)

# In guardrail failure handler:
trace.complete(outcome=RequestOutcome.BLOCKED, error_category="guardrail_input_blocked")

# At end of successful generate():
trace.complete(
    outcome=RequestOutcome.SUCCESS,
    sources_count=len(search_results or []),
    overall_score=score.get("overall") if score else None,
    cache_status="hit" if cached else "miss"
)
metrics_service.record_request(
    request_id=trace.request_id,
    endpoint="/generate",
    method="POST",
    status_code=200,
    duration_ms=round((time.time() - start) * 1000, 2),
    cache_hit=bool(cached),
    search_called=(intent != "question" and not cached)
)
```

### 3. Instrument Guardrail Safety Events in `guardrails/checks.py`
In [`guardrails/checks.py`](file:///c:/Projects/Multi-agent-research-platform/guardrails/checks.py):
```python
from admin_backend.services.safety_service import safety_service
from admin_backend.models.safety import GuardCheckType, SafetyOutcome

# When an input or output check fails:
safety_service.record_blocked_event(
    check_type=GuardCheckType.INPUT_RULE,
    reason=reason,
    raw_text=topic,
    outcome=SafetyOutcome.BLOCKED
)
```

### 4. Apply Database Migrations
Run the SQL script against PostgreSQL:
```bash
psql -d research_platform -f admin_backend/migrations/001_admin_tables.sql
```

### 5. Provision Initial Administrator
Define `ADMIN_PROVISIONING_TOKEN` in `.env` and execute initial bootstrap:
```bash
curl -X POST http://localhost:8000/api/admin/auth/provision-initial-admin \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "SecurePassword123!", "provisioning_token": "<TOKEN>"}'
```
