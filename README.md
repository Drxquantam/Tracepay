# TracePay: Money in Flight

> **⚠️ Simulation only.** Fake money, fake banks, a mock UPI switch. No real payment
> details, no real bank or NPCI integration.

TracePay is a simulated UPI-style payments platform built around one question: *what happens
to my money after something goes wrong?* It tracks each payment through its stages and shows
when a bank misses its turnaround deadline. The bank then owes compensation, and TracePay
works out how much.

Status: **Phase 1 of 7** (scaffold, schema, auth, seed data). The full README (architecture,
design decisions, rules table, limitations) is written in Phase 7.

## Run it

```bash
docker compose up --build
```

- API: http://localhost:8000 (interactive docs at `/docs`)
- Web: http://localhost:5173
- Postgres: `localhost:5433` (user/password `tracepay`)

On start the API container runs `alembic upgrade head`, then `python -m app.seed` (safe to
repeat), then the server.

### Demo users (password `demo1234` for all, simulation only)

| Username | Who | Bank |
|---|---|---|
| `aarav` | Aarav Mehta, college student | Jhatpat Bank (flaky) |
| `shanti` | Shanti Mehta, his grandmother (trusted person, senior mode) | Suraksha Bank (reliable) |
| `ravi` | Ravi Kumar, Ravi General Store | Suraksha Bank |
| `admin` | Demo admin (chaos controls, time travel) | none |

## Tests

Tests use a separate `tracepay_test` database in the same Postgres container.

```bash
docker compose run --rm api pytest -q
```

Or from your machine with the db container running (`docker compose up -d db`):

```bash
cd backend && python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt
.venv/Scripts/pytest -q          # use .venv/bin/ on macOS/Linux
.venv/Scripts/ruff check . && .venv/Scripts/mypy app
```

## Data model (so far)

- **users**, **banks**, **accounts**: an account belongs to a bank and has a UPI ID (`vpa`).
- **ledger_entries**: double-entry ledger. A signed amount in paise, where every transaction's
  rows sum to zero. Opening balances come in from a system account, so the whole ledger sums
  to zero from the very first row.
- **payments**, **payment_events**: a payment and its append-only history of state changes.
- **idempotency_keys**: saved results for replayed requests (Phase 2).
- **sim_clock**: a single row holding the simulated clock's offset (Phase 2).

Money is always stored as integer **paise** (BIGINT), never as a float.
