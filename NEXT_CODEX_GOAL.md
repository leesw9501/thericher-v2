# Next Codex Goal

## Objective

Complete `kis-paper-iwm-current-head-capability-capture-v1`: use the prepared
isolated IWM/AMS one-current-day-page collector once to establish whether its
KIS Paper path can produce one source-safe categorical outcome and external
data receipt. This is a bounded data-capability capture, not a historical-data
claim, causal input, model result, Paper order, or live route.

The earlier `kis-intraday-later-terminal-reattachment-v1` remains an existing
task-owned monitor. Do not foreground-wait for it or manually invoke it.

## Standing Authorization And Boundaries

- `KIS_PAPER_*` may be read only by the named collector path for this one KIS
  Paper market-data invocation. Never read or route `KIS_LIVE_*`; never print,
  log, commit, or send credentials, account identifiers, raw rows, broker
  bodies, private intents, or tokens to Claude.
- Run only `scripts\collect_kis_paper_iwm_current_head.py --execute` with its
  fixed IWM/AMS one-current-day, no-previous-day, no-continuation scope. Do not
  retry in this objective, paginate, change the collector, modify a task,
  schedule a worker, start a Docker service, submit/modify/cancel an order, or
  enable live behavior.
- Keep any raw market data only beneath `D:\market_data`; keep its source-safe
  receipt only beneath `D:\thericher-v2\model-artifacts`. Do not inspect,
  copy, hash, or persist raw rows outside the collector's existing external
  path. Never store raw data or generated artifacts in Git.
- Keep the new ingestion receipt separate from the established IWM replay
  receipt directory. A `collected`, `recovered`, `unavailable`, or `locked`
  categorical outcome establishes only this one attempt's scope. It does not
  qualify replay, historical reach, finality, availability, a model input, or
  a Paper consumer.

## Required Work

1. Run the prepared collector exactly once and retain only its source-safe
   stdout category plus external evidence pointer if one is written.
2. If it completes, reattach only the categorical receipt metadata through the
   existing offline-safe reader/path checks; do not read raw data. If it is
   unavailable or locked, record its narrow recovery fact without retrying.
3. Refresh Data, orchestration, and `HANDOFF.md` with the outcome. Keep the
   intraday later-terminal task-owned monitor non-blocking and do not infer
   equivalence between its QQQ/SPY path and IWM.
4. Run focused tests for any code changes. After a material outcome, run the
   goal-boundary verification, commit, push, replace this file with one next
   company objective, and continue.

## Completion Evidence

- One source-safe categorical collector result, with no live route or order.
- Any resulting receipt/cache location is external and replay-isolated.
- No raw values, credential values, account identifiers, model, PnL, or
  predictive eligibility claim is retained in Git or stateboards.
