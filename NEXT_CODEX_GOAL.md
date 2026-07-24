# Next Codex Goal

## Objective

Reconcile the first expanded-cadence prospective QQQ intraday-head collection
and use its metadata-only result to make, at most, one further evidence-backed
Data recovery change. The new 00:35 KST window is owned by the existing single
head task; do not wait in the foreground for it or create a duplicate scheduler.

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
   collector, duplicate, timestamp, or page-size behavior. Do not send
   credentials, raw rows, cache paths, or artifact contents. A local Claude
   authentication/tool failure is a scoped tooling fact, not a Data hold.

## Hard Boundaries

- `KIS_PAPER_*` may be used only by the private Data client for market-data
  collection. Do not call account, position, order, modify, cancel, or live
  endpoints, and never read `KIS_LIVE_*`.
- Keep raw data under `D:\market_data` and generated evidence under
  `D:\thericher-v2\model-artifacts`; do not print or commit raw rows, prices,
  credentials, account facts, response bodies, or private cache paths.
- Preserve one existing `thericher-kis-paper-intraday-head` task, one Docker
  profile, the four-page-per-target cap, source pacing, strict conflicting-row
  rejection, and exact 390-minute session selection unless new evidence directly
  falsifies one of those rules.
- Do not rerun a known out-of-session duplicate-conflict shape merely to create
  activity. The scheduler owns its due time; other ready lanes continue.
- Do not run a model/GPU job, select a candidate, create an intent, or submit a
  Paper order. The frozen offline consumer remains input-pending until a valid
  first-five preparation pair exists.

## Required Work

1. Reattest the installed four-trigger task and current head-index metadata
   without opening raw bars. Run
   `uv run python scripts\inspect_kis_intraday_head_coverage.py` to record the
   QQQ coverage baseline and recovery class.
2. After the first due expanded-cadence result, run the same inspector and
   compare only its source-safe metadata: QQQ regular-session minute count and
   offset-based missing ranges, continuation category, exact/conflicting
   overlap categories, and preparation-input status.
3. If exact 390-minute QQQ coverage exists, invoke the existing metadata-only
   preparation handoff and then run the already-built offline consumer. Do not
   use KIS, credentials, or broker routes in the consumer.
4. If coverage remains short, identify the exact missing interval/category and
   make only one smallest source-backed recovery change. The official KIS sample
   documents `NREC` as configurable up to 120, but do not introduce page-size or
   duplicate-policy behavior without a bounded source/test case that requires it.
5. Refresh Data, Research, and orchestration stateboards with current evidence,
   next recovery, and no invented wait or approval state.

## Completion Evidence

- A metadata-only before/after coverage comparison names the QQQ session state,
  source continuation/conflict category, and recovery classification.
- Any change remains private, idempotent, source-paced, recoverable, and inside
  the existing single-worker/single-task boundary.
- A valid five-session pair either drives the offline local-paper observation or
  remains an explicit normal pending input with the precise next Data action.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Reconcile expanded intraday head coverage`
