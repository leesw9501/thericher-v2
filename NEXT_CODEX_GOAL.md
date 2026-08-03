# Next Codex Goal

Read `HANDOFF.md`, `VISION.md`, `ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`,
`RUNBOOK.md`, and the active `agents/` stateboards first. Then continue from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Complete `kis-spy-expiry-boundary-observation-v1`: consume the one remaining
source-safe 15:31 ET daylight-time receipt from the existing
`thericher-kis-paper-intraday-head` task and compare it with the committed
13:31 ET control observation.

The product outcome is a bounded fact about post-collection SPY prefix state
at the existing expiry-boundary dispatch. It must not infer 15:30 decision-time
availability, change cadence or TTL, or become a model, PnL, or Paper-trading
result.

## Boundaries

- Let only the existing owned scheduler make KIS Paper market-data calls. Do
  not start a collector manually, create a duplicate worker/cache, or change
  the existing SPY/QQQ head scope or triggers.
- Do not call or read KIS account, position, quote, order, submit, modify,
  cancel, reconciliation, or live routes. Never read or route `KIS_LIVE_*`.
- Consume only source-safe timing/terminal receipts and sanitized Task
  Scheduler metadata. Do not retain or display credentials, raw bars, prices,
  request URLs, account identifiers, private intents, or broker payloads.
- Treat the raw receipt's serialized Eastern timestamp and UTC endpoint as
  primary evidence. Do not reinterpret its offset through host-local PowerShell
  date conversion.
- Preserve the frozen prospective-SPY baseline, one-minute validity, virtual
  Paper route, and terminal schedule behavior. No observation alone changes
  them.

## Required Work

1. **Data:** reattest the first new 15:31 ET timing receipt and paired terminal
   outcome. Compare only safe timing, offset, collection count/status, and
   post-collection prefix categories with the committed 13:31 ET control.
2. **Engine Research:** retain `decision_time_availability: not_observed` and
   classify only what the two post-collection observations can and cannot say
   about the fixed 15:30 decision.
3. **Execution:** reattest the terminal's SPY-cycle/no-canary state and prove
   that no account, quote, order, local-paper, or live route was touched.
4. **Integration:** after both observations exist, ask Claude for a concise
   falsification-first challenge before writing one compact, later
   schedule/validity design proposal. Do not implement that proposal in this
   objective.
5. If the receipt is not due or the scheduler has not yet produced it, record
   its sanitized `next_due` and continue another ready lane without a
   foreground wait.

## Completion Evidence

- both matching source-safe timing receipts and terminal outcomes are
  reattested without raw/provider/account/order output;
- all active stateboards and `HANDOFF.md` distinguish post-collection state
  from decision-time availability;
- Claude verdict is recorded only for the later design proposal;
- required verification, commit, and push complete; then replace this file
  with exactly one next company objective.

## Verification

```powershell
uv run --extra dev pytest -q <changed focused tests>
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example --profile kis-paper-intraday-head config --quiet
```
