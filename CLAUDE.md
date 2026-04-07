# TTrade — AI Agent Instructions

> Options trading engine: Python scanner + Cloudflare Worker API + D1 database.
> Last updated: April 7, 2026.

## What Is This

**TTrade** is a state-driven vertical spread trading engine for a $1,000 options account. It scans 7 tickers (SPY, QQQ, AAPL, MSFT, NVDA, VCX, RKLB), evaluates setups through 15 sequential gates, scores qualifying signals on 7 dimensions, and optionally gets AI conviction analysis before alerting.

**Architecture:**
```
Python Engine (local) → scans tickers, runs gates, scores signals
  ↕ syncs to
Cloudflare Worker (remote) → D1 database, dashboard API, AI gateway
  ↕ routes AI through
CF AI Gateway (aicr) → OpenRouter → Claude Haiku
```

## Project Structure

```
engine/                 # Python engine (v1.1.0)
├── config.py           # 40+ strategy thresholds (frozen dataclass)
├── models.py           # Pydantic v2 contracts (SignalEvaluation, etc.)
├── pipeline.py         # 15-gate pipeline + scoring + AI analysis
├── db.py               # SQLModel schema (6 tables)
├── main.py             # Market hours loop (scan + monitor cycles)
├── cli.py              # Click CLI (scan, sync, approve, run)
├── market_data.py      # yfinance bars, SMA, ATR
├── market_state.py     # Regime detection (TREND_UP/DOWN/CHOP)
├── scoring.py          # 7-dimension scoring engine
├── ai_analyst.py       # Worker /ai/analyze caller
├── ai_journal.py       # Worker /ai/review-trade caller
├── broker.py           # Public.com API broker client
├── executor.py         # Order execution
├── monitor.py          # Exit rules (stop loss, profit target)
├── reviewer.py         # Post-trade grading (A-F)
├── notifier.py         # iMessage alerts
├── weekly_report.py    # Weekly aggregation
└── gates/              # 15 sequential gates
    ├── regime.py           #  1: Market state ≠ CHOP
    ├── alignment.py        #  2: Price/SMA alignment
    ├── pullback.py         #  3: Pullback zone
    ├── confirmation.py     #  4: Volume + close strength
    ├── earnings.py         #  5: Not near earnings
    ├── price_stability.py  #  6: ATR spike check
    ├── options_volatility.py # 7: IV Rank thresholds
    ├── liquidity.py        #  8: Open interest + bid/ask
    ├── position_construction.py # 9: Spread sizing
    ├── cooldown_exposure.py # 10: Max trades/positions
    ├── correlation.py      # 11: Speculative overlap
    ├── vix_circuit_breaker.py # 12: VIX > 30 block
    ├── earnings_calendar.py # 13: Live earnings date
    ├── loss_circuit_breaker.py # 14: Daily/weekly loss limit
    └── news_sentiment.py   # 15: News via AI

worker/                 # Cloudflare Worker (Hono + D1)
├── src/
│   ├── worker.ts       # Hono app entry, middleware, routes
│   ├── types.ts        # Env bindings (DB, AI, secrets)
│   ├── routes/         # 9 route modules
│   │   ├── ai.ts       # AI analyze + review (CF Gateway → OpenRouter → Claude)
│   │   ├── sync.ts     # Engine → D1 sync
│   │   ├── dashboard.ts # Dashboard data API
│   │   ├── signals.ts  # Signal CRUD
│   │   ├── market.ts   # Market data proxy
│   │   └── ...
│   └── db/schema.ts    # Drizzle schema
├── migrations/         # D1 SQL migrations
└── package.json        # Hono, Drizzle, Wrangler

tests/                  # 22 test files, 133+ tests
data/                   # Local SQLite (ttrade.db)
dashboard.html          # Trading dashboard UI
```

## Tech Stack

| Layer | Technology |
|-------|------------|
| Engine | Python 3.12+, Pydantic v2, SQLModel, Click, yfinance |
| Worker | TypeScript, Hono, Drizzle ORM, Cloudflare Workers |
| Database | Local: SQLite (via SQLModel), Remote: D1 (via Drizzle) |
| AI | CF AI Gateway → OpenRouter → Claude Haiku 4.5 |
| Broker | Public.com API (httpx) |
| Alerts | iMessage (AppleScript) |

## Critical Rules

1. **AI VIA GATEWAY ONLY** — All AI calls route through the CF AI Gateway. Never add `ANTHROPIC_API_KEY` or call `api.anthropic.com` directly. See `.claude/AI_GATEWAY.md`.
2. **GATES ARE THE SAFETY LAYER** — AI can downgrade (execute→alert) but never upgrade. Gates make the hard pass/fail decisions.
3. **15 GATES RUN SEQUENTIALLY** — Short-circuit on first failure. Order matters. Don't reorder without understanding dependencies.
4. **NAIVE DATETIMES FOR SQLITE** — SQLite stores naive datetimes. Always strip `tzinfo` before comparison. See `loss_circuit_breaker.py` for the pattern.
5. **ENGINE NEVER CALLS AI DIRECTLY** — The Python engine calls Worker `/ai/*` endpoints, which route through the gateway. Two hops, no shortcuts.
6. **FAIL-OPEN ON DATA UNAVAILABILITY** — VIX, earnings, news gates pass when data is unavailable. Better to miss a gate than block all trading.

## AI Gateway

All AI calls: `engine → Worker /ai/* → CF AI Gateway (aicr) → OpenRouter (aicr-or-ai) → Claude Haiku`

| Setting | Value |
|---------|-------|
| Gateway | `aicr` |
| Provider | OpenRouter (`aicr-or-ai` BYOK alias) |
| Model | `anthropic/claude-haiku-4-5` |
| Auth | `CF_AIG_TOKEN` Worker secret + `cf-aig-byok-alias` header |

Full details: `.claude/AI_GATEWAY.md` and `~/Development/AICR/.claude/references/cloudflare-ai-gateway.md`

## Secrets (macOS Keychain)

All use uniform lookup: `security find-generic-password -a todd.lebaron -s <NAME> -w`

| Secret | Purpose |
|--------|---------|
| `CF_AIG_TOKEN` | AI Gateway auth (also Worker secret) |
| `DASHBOARD_TOKEN` | Dashboard API auth |
| `SYNC_API_KEY` | Engine→Worker sync auth |
| `PUBLIC_API_SECRET` | Public.com broker API |
| `PUBLIC_ACCOUNT_ID` | Public.com account |

## Quick Commands

```bash
# Activate venv
source .venv/bin/activate

# Run a scan (ignores market hours)
python -m engine.cli scan

# Start engine (market hours loop)
python -m engine.cli run

# Sync signals to D1
python -m engine.cli sync

# Run tests
python -m pytest tests/ -v

# Deploy Worker
npx wrangler deploy

# Check Worker logs
npx wrangler tail
```

## Pipeline Flow

```
1. Fetch SPY bars → evaluate_market_state() → TREND_UP / TREND_DOWN / CHOP
2. For each ticker:
   a. Run 15 gates sequentially (short-circuit on fail)
   b. If all pass → score on 7 dimensions (0-100)
   c. Score → action: execute (≥75) / alert (≥55) / log (≥0) / reject
   d. If execute or alert → AI analyst scores conviction (0-100, A/B/C/PASS)
   e. AI can downgrade execute→alert if quality=PASS
   f. Persist SignalRecord to local DB
   g. Send iMessage alert if execute/alert
3. Monitor cycle: check exit rules on open positions
4. Sync cycle: push unsynced signals + gates to D1
```

## Database Tables

**Local (SQLite via SQLModel):**
- `signal_records` — Gate results, scores, action, AI analysis
- `position_records` — Open/closed trades, P&L, reviewed flag
- `execution_records` — Order lifecycle events
- `cooldown_records` — Fill tracking per day

**Remote (D1 via Drizzle):**
- `signal_evaluations` — Synced signals with AI columns
- `gate_results` — Individual gate pass/fail per signal
- `trade_reviews` — AI coaching reviews

## When Stuck

1. Check `.claude/AI_GATEWAY.md` for AI-related issues
2. Run `python -m pytest tests/ -v --tb=short` to verify nothing is broken
3. Check `data/ttrade.db` with `sqlite3 data/ttrade.db ".tables"` for schema issues
4. Delete stale DB if schema mismatch: `rm -f data/ttrade.db` (recreated on next run)
