# Next Codex Goal

## Objective

Establish the first frozen six-symbol daily CPU local-paper baseline from the
qualified KIS Paper current-basket panel.

This connects each immutable `AAPL`, `AMZN`, `GOOGL`, `META`, `MSFT`, and
`NVDA` D1 stream to broker-free local-paper replay with an explicit naive
comparator. It proves an offline validation loop only. It does not rank stocks,
select a strategy, train a depth model, create an ensemble, submit a Paper
order, or enable live behavior.

## First Reads

1. Run:

~~~powershell
.\scripts\start_next_codex_task.ps1
~~~

2. Read HANDOFF.md, AGENTS.md, ARCHITECTURE.md, DECISIONS.md, RUNBOOK.md,
   agents/orchestration.md, agents/data.md, agents/engine-research.md, and
   agents/execution.md.
3. Inspect only source-safe panel manifest/evidence and existing local-paper
   validation interfaces. Do not print raw rows, prices, credentials, account
   facts, or sealed labels.

## Required Work

1. Load only the frozen six-symbol panel through its dedicated hash-bound
   offline loader. Preserve the ordered NAS scope, 199 common sessions,
   `MODP=0_unadjusted`, current-listing limitation, and source separation.
2. Freeze one small CPU replay contract before execution: per-symbol replay,
   chronological completed-bar timing, fixed local-paper costs and sizing, one
   transparent momentum baseline, and one explicit naive comparator. Do not
   pool symbols into a cross-sectional ranking or tune after seeing results.
3. Run the six independent broker-free local-paper replays through the existing
   validation boundary. Persist only source-safe results and replay evidence
   under `D:\thericher-v2\model-artifacts`; every fill must remain
   `source: local_paper`.
4. Invoke temporary Validation after the contract is frozen. It must check
   source binding, completed-bar timing, all-local-paper fills, replayability,
   and that no result materially exceeds its naive comparator without a
   falsification note.
5. Do not allocate GPU work from this 199-session current-basket panel. Record
   whether the CPU baseline supports a future breadth hypothesis, but make no
   winner, promotion, ensemble, PnL-profitability, or Paper-order claim.
6. Update the Data, Engine Research, and orchestration stateboards with only
   the frozen contract/result, limitations, recovery fact, and next ready
   action.

## Hard Boundaries

- Offline only: do not call KIS, read `.env`, access account/order endpoints,
  create a schedule, or use any `KIS_LIVE_*` value.
- Use only the frozen six-symbol panel. Do not blend Norgate, Tiingo, Yahoo,
  ETF, or other KIS cache rows, and do not expand the symbols or date range.
- Do not use the result for historical PIT claims, stock ranking, corporate
  action claims, GPU depth training, an ensemble, a dashboard, an intent, or a
  broker action.
- Keep raw data and generated artifacts outside Git. Do not print or persist
  raw rows, credentials, account facts, or broker payloads.

## Completion Evidence

- One immutable source-safe CPU baseline result for each fixed symbol with a
  linked panel identity and fixed replay economics.
- An explicit naive comparator and per-symbol outcome table that does not make
  a selection or profitability claim.
- Focused tests proving offline/source binding, completed-bar timing,
  local-paper-only fills, replayability, and artifact containment.
- Stateboards that state whether this small panel supports only another bounded
  hypothesis or needs more Data before depth work.

## Verification

~~~powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
~~~

Before ending, verify, commit, push, and replace this file with exactly one
next company objective. A weak baseline result, local artifact issue, or Claude
OAuth fault does not stop independent ready work.
