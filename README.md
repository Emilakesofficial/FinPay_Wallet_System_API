**Wallet System — Production-Grade Double-Entry Ledger**

- **Purpose**: A secure, auditable wallet platform implementing double-entry bookkeeping for deposits, withdrawals and transfers with strong idempotency, reconciliation, and auditing.

**Key Highlights**
- **Double-entry correctness**: Every monetary operation strictly creates a debit and a credit ledger entry; ledger entries are immutable and running balances are cached for performance.
- **Idempotency & Concurrency Safety**: All mutating operations use idempotency keys and database-level locking (`SELECT FOR UPDATE`) to prevent duplicates and race conditions.
- **Reconciliation Engine**: Automated, multi-check reconciliation implemented as Celery tasks to detect imbalances, drift, negative balances, stale transactions, and global parity.
- **Audit Trail**: Immutable audit logs capture actor, action, target, metadata, IP and user-agent for full forensicability.
- **Tested**: Comprehensive automated tests (121 passing locally) exercising core wallet flows, reconciliation checks, audit behaviour, load testing, concurrency, end to end integration test and API endpoints.

**Repository Structure (selected paths)**
- **Domain / Apps**:
	- **accounts**: user model and auth-related API ([apps/accounts/models.py](apps/accounts/models.py)).
	- **wallets**: core domain — `Wallet`, `Transaction`, `LedgerEntry`, service layer for money movements ([apps/wallets/models.py](apps/wallets/models.py), [apps/wallets/services.py](apps/wallets/services.py), [apps/wallets/views.py](apps/wallets/views.py)).
	- **audit**: audit models, middleware, service and admin/API ([apps/audit/models.py](apps/audit/models.py), [apps/audit/service.py](apps/audit/service.py), [apps/audit/middleware.py](apps/audit/middleware.py)).
	- **reconciliation**: Celery tasks and report model that run multi-step checks and produce reports ([apps/reconciliation/tasks.py](apps/reconciliation/tasks.py), [apps/reconciliation/models.py](apps/reconciliation/models.py)).

- **Common utilities & infra**:
	- `common` contains helpers, exceptions, middleware and base models ([common/utils.py](common/utils.py), [common/exceptions.py](common/exceptions.py), [common/models.py](common/models.py)).
	- `config/settings` contains production and development configuration (Postgres, Redis, Celery, logging, JWT).

**Architecture Overview**
- **API Layer**: DRF-powered ViewSets expose wallet CRUD and transaction endpoints. Input validation, JWT auth, and throttling are enforced at the API boundary.
- **Service Layer**: `WalletService` is the single source of truth for all money movement. It enforces atomic transactions, idempotency, deadlock-safe locking order, and writes exactly two ledger entries per transaction.
- **Persistence**: PostgreSQL stores immutable ledger entries; balances are derived (with a cached running balance in `LedgerEntry.balance_after`) to avoid drift.
- **Background Work**: Celery orchestrates reconciliation workflows. A master task composes parallel checks (via a chord) and aggregates results into `ReconciliationReport` instances.
- **Audit & Observability**: `AuditService` creates immutable `AuditLog` entries and middleware records request context (ip, user-agent). `structlog` and JSON logging are configured for structured observability.

**Architecture Diagram**

![Architecture diagram](docs/architecture.svg)


**Reconciliation Checks (what they do)**
- **Double-entry parity**: Ensures every completed transaction has balanced debits and credits and exactly two ledger entries.
- **Balance drift check**: Compares cached `balance_after` to a computed balance (sum of entries); small drifts are auto-fixed, large drifts are reported.
- **Negative balances**: Detects non-system wallets with negative computed balances.
- **Transaction state**: Flags FAILED transactions that nevertheless have entries, PENDING transactions stuck > 5 minutes, and COMPLETED transactions with wrong entry counts.
- **Global parity**: Ensures SUM(debits) == SUM(credits) across the entire ledger.

**Testing & Quality**
- **Test coverage**: The codebase includes an extensive test suite covering core wallet operations, reconciliation checks, audit recording, and API endpoints. Locally the suite runs 121 tests (all passing).
- **Targeted unit tests**: I added focused tests for:
	- Reconciliation: each check (`check_double_entry`, `check_balance_drift`, `check_negative_balances`, `check_transaction_state`, `check_global_balance`), the aggregator, and the orchestration (`run_reconciliation`).
	- Audit: `AuditService` helpers, middleware context management, immutability rules, serializer and admin/API endpoints.
	- Wallet domain: deposit/withdraw/transfer behaviors, idempotency, and concurrency scenarios.
- **How to run tests locally**:

```bash
source venv/bin/activate
pip install -r requirements/requirements.txt
pytest --maxfail=1 -q --disable-warnings --cov=apps --cov-report=html
# open htmlcov/index.html to inspect per-file coverage
```

**Operational Notes & Production Concerns**
- **System wallet**: A system wallet per currency holds platform-level assets — created via management command ([apps/wallets/management/commands/create_system_wallet.py](apps/wallets/management/commands/create_system_wallet.py)).
- **Immutability**: Ledger entries are immutable by design; reconciliation tasks include safe auto-fix for minor drift (raw DB update of the latest ledger entry's `balance_after`) — auto-fix is intentionally conservative.
- **Idempotency**: All external-facing mutating endpoints require an `Idempotency-Key` header; service-layer uses `get_or_create` semantics to claim keys safely.
- **Scaling**: Reconciliation uses batching and Celery chords for parallelism. Celery settings are configured for safe prefetch and worker limits in `config/settings/base.py`.
- **Alerts**: Reconciliation sends email alerts on warnings/failures; make sure `RECONCILIATION_ALERT_EMAILS` and SMTP settings are configured in environment.

**Security & Auditability**
- **Custom user model** with UUID primary keys improves privacy and distribution.
- **Structured logging** (`structlog`) and immutable audit trail enable forensic analysis.
- **Permissions**: Audit API and admin views are restricted to staff users.

