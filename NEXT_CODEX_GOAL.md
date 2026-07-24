# Next Codex Goal

## Objective

Close the first-five-session prospective-data gap by establishing, with
bounded evidence, why the existing KIS Paper intraday-head worker has not yet
produced a complete 390-minute QQQ regular session, then make the smallest
recoverable Data-side change that can improve collection coverage. The outcome
is a truthful coverage/recovery result, not a strategy, model, GPU, PnL, or
execution result.

## First Reads

1. Run:

   ```powershell
   .\scripts\start_next_codex_task.ps1
   ```

2. Read:
   - `HANDOFF.md`
   - `VISION.md`
   - `ARCHITECTURE.md`
   - `AGENTS.md`
   - `DECISIONS.md`
   - `RUNBOOK.md`
   - `agents/orchestration.md`
   - `agents/data.md`
   - `agents/engine-research.md`

3. Attempt a concise falsification-first Claude drift-check before changing
   collector behavior. Do not send credentials, raw rows, cache paths, or
   artifact contents. A local Claude authentication/tool failure is recorded as
   a scoped tooling fact and does not hold safe Data work.

## Hard Boundaries

- `KIS_PAPER_*` may be used only by the existing private Data client for
  market-data collection. Do not call account, position, order, modify, cancel,
  or live endpoints, and never read `KIS_LIVE_*`.
- Keep raw source data under `D:\market_data`; keep generated evidence under
  `D:\thericher-v2\model-artifacts`; never print or commit raw rows,
  credentials, account facts, or response bodies.
- Use the existing head worker, shared request control, and scheduled path when
  possible. Do not create a second scheduler, a polling platform, a permanent
  foreground sleep, or an approval gate.
- A QQQ session becomes usable only after exact contiguous 390-minute regular
  coverage and existing cache/index validation. Short, duplicate, conflicting,
  extended-hours, or timestamp-ambiguous coverage stays a scoped Data fact.
- Do not alter the frozen prospective Research contract, run a model/GPU job,
  select a candidate, construct a broker intent, or submit a Paper order.

## Required Work

1. Inventory the current head index, recent collector evidence, and any
   relevant historical probe metadata without dumping raw rows. State the exact
   coverage gap and the strongest falsifiable cause.
2. Trace the canonical KIS intraday request, continuation, page, timestamp,
   and session-selection path. Prefer source evidence and focused synthetic
   tests over guesses.
3. If evidence supports a correction, implement the smallest bounded,
   idempotent collector or recovery change. Preserve source pacing/retry facts
   inside the owned worker and let other lanes continue while it waits.
4. Exercise a bounded private data-only run when useful under the standing KIS
   Paper authority. Reconcile its index/manifest outcome, then invoke the
   existing preparation handoff only after durable collection.
5. Add focused tests for the observed failure/recovery shape and for rejection
   of any incomplete session. Refresh the Data, Research, and orchestration
   stateboards with evidence and next recovery action.

## Completion Evidence

- A metadata-only coverage statement identifies the current QQQ session state
  and either a concrete source limitation or a tested recovery change.
- Any changed worker remains private, idempotent, source-paced, and recoverable
  without blocking unrelated lanes.
- If five complete sessions now exist, the existing pair is prepared and the
  offline consumer may run; otherwise it remains a normal pending input with a
  precise next collection/recovery path.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Improve prospective intraday collection coverage`
