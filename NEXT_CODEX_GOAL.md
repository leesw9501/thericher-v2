# Next Codex Goal

## Objective

Determine why the first post-close KIS Paper intraday-head run did not produce
one complete 390-minute QQQ regular session, then make the smallest proven
data-only correction.

The 2026-07-24 06:20 KST task succeeded and committed one new 120-row chunk per
QQQ/NAS and SPY/AMS, but the metadata-only preparer still found zero complete
QQQ regular sessions. This is a bounded source-coverage problem, not a Paper,
GPU, or human-approval hold.

## Standing Authority

- All private `KIS_PAPER_*` market-data/account/order work, virtual Paper
  submit/modify/cancel, `D:` retention, and goal-owned schedules are already
  authorized. For this goal, use only the data-only KIS market-data path.
- Do not read `KIS_LIVE_*`, use a live route, real capital, paid data,
  unclear-rights assets, public exposure, Git-hosted raw data/artifacts, or
  secrets.
- Keep raw source rows under `D:\market_data` and generated artifacts under
  `D:\thericher-v2\model-artifacts`, never Git.
- A short, duplicate, delayed, or unavailable source result limits only that
  exact data claim. It never pauses another Paper, Data, or Research action.

## Required First Reads

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `VISION.md`, `ARCHITECTURE.md`, `AGENTS.md`,
   `DECISIONS.md`, and `RUNBOOK.md`.
3. Read `agents/README.md`, `agents/data.md`, `agents/engine-research.md`,
   and `agents/execution.md`.
4. Inspect only sanitized task/index/chunk metadata before looking at raw
   source bytes.
5. Ask Claude for a short falsification-first drift-check before changing the
   KIS minute pagination, source anchors, page count, or task schedule.

## Role-Owned Work

### Data Agent

1. Compare the current KIS minute request/continuation implementation with the
   official KIS sample and deterministic fake transports. Establish whether the
   short result is caused by continuation semantics, request anchors, provider
   availability, or another concrete source fact.
2. Change only the demonstrated fault. Keep the writer's exact-overlap,
   conflict, raw-retention, and D: storage contracts intact.
3. Run one bounded data-only KIS verification collection only when it improves
   that diagnosis or validates a correction. It may retain source rows on D:
   but must not access account/order routes or output raw rows.
4. Re-run the metadata-only prospective preparer and classify the result. An
   exact 390-minute QQQ session is future input eligibility; any other result
   remains a source-coverage fact.
5. The existing named head task now has 02:35, 04:35, and 06:20 KST triggers
   with the unchanged four-page cap. Do not add a duplicate task or manually
   duplicate a due/running trigger.

### Engine Research Agent

1. Keep the existing historical baselines, breadth/depth/ensemble queues, and
   frozen prospective contract unchanged. Do not treat a partial head slice as
   a model sample, selection result, or GPU qualification.
2. Continue only CPU preparation that does not consume the partial head input.

### Execution Agent

1. Keep virtual-host-only routing and the existing Paper schedule unchanged
   unless Data proves a data-only task configuration fault.
2. Do not infer terminal state, PnL, or execution performance from the daily
   `target_already_satisfied` no-intent outcome.

### Validation Agent

1. Verify any correction preserves secret redaction, data-only isolation,
   exact-overlap handling, replayability, and no broker/account/order access.

## Completion Evidence

- A concrete source diagnosis is recorded, with a focused regression test if
  implementation changes.
- A bounded data-only verification result is classified from safe evidence.
- The metadata-only preparer has been rerun; its outcome is recorded without
  turning it into an approval gate.
- Raw data and artifacts remain outside Git, and Paper/live route isolation is
  unchanged.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Classify intraday head coverage`
