# Next Codex Goal

Read `HANDOFF.md`, `VISION.md`, `ARCHITECTURE.md`, `AGENTS.md`,
`DECISIONS.md`, `RUNBOOK.md`, and the active stateboards in `agents/` first.
Then continue from `C:\Users\Public\Documents\thericher-v2`.

## Objective

Build `prospective-spy-paper-safety-reattest-v1`: close the three bounded
falsification gaps on the unscheduled prospective-SPY virtual-paper adapter
before any named activation relies on it. This improves live-risk control for
an already-authorized Paper route; it is not a scheduler, strategy, PnL, or
live-capital change.

## Boundaries

- Never read or route `KIS_LIVE_*`, use live capital, add a scheduler, or run
  an `--execute` Paper session for transport testing.
- Do not mutate capture caches or create a fresh receipt. Use fixtures and
  mocked clients only; no KIS, network, credential, account, quote, intent,
  order, cancel, or reconciliation call is needed.
- Preserve the daily SPY D1 route and broker-free `source: local_paper` replay
  as separate paths. Do not alter their strategy, sizing, or lifecycle logic.

## Required Work

1. **Execution:** Prove the adapter import and all ineligible receipt exits do
   not access configuration, credentials, account, or quote paths. Keep one
   lazy configuration chokepoint and avoid a second access path.
2. **Validation:** Reattest freshness from immutable receipt timestamps against
   the call-time clock, including an explicit stale boundary, rather than any
   producer-owned eligibility flag.
3. **Isolation:** Prove an intraday receipt-derived durable identity cannot
   collide with the daily SPY D1 route, and reattest that the existing canary
   client pins virtual-Paper endpoints.
4. **Review:** Ask Claude for a concise falsification-first verdict on these
   exact three closure facts. An adverse verdict defers only this adapter's
   activation; independent work continues.

## Completion Evidence

- focused tests cover import/no-I/O, stale-boundary, and daily/intraday
  durable-identity separation;
- virtual/non-live endpoint isolation remains explicit;
- no external Paper side effect occurred;
- Commit and push, then replace this file with exactly one next objective.

## Verification

```powershell
uv run --extra dev pytest -q <changed focused tests>
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example --profile research config --quiet
```
