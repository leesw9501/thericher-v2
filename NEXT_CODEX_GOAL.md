# Next Codex Goal

## Objective

Classify the first complete three-window KIS Paper intraday-head collection
cycle after the 02:35, 04:35, and 06:20 KST schedule installation, without
changing the proven KIS minute request semantics.

The completed diagnosis established that the 2026-07-24 06:20 KST QQQ/NAS and
SPY/AMS observations each ended at the KIS source after one 120-row page. The
collector's four-page ceiling did not truncate them: the response did not offer
an `M`/`F` continuation. The prior in-session observation reached two pages and
was likewise handled by the existing official continuation contract. This is a
bounded provider-availability and anchor-timing fact, not a pagination,
execution, GPU, or operator-approval hold.

## Standing Authority

- Private `KIS_PAPER_*` market-data collection and local retention on `D:` are
  authorized. This goal is data-only; it must not access account or order
  endpoints.
- Do not read `KIS_LIVE_*`, use a live route or real capital, buy data, accept
  unclear rights, publish anything, expose raw rows, or put data/artifacts in
  Git.
- The existing named `thericher-kis-paper-intraday-head` task owns the three
  triggers and its four-page cap. Do not add another task or manually duplicate
  a due/running invocation.

## Role-Owned Work

### Data Agent

1. After each scheduled run, inspect only sanitized task, index, and chunk
   metadata. Record page/continuation categories, exact-overlap/conflict
   counts, and source coverage; do not inspect or output raw market rows.
2. Re-run the metadata-only prospective preparer after the full cycle. Accept
   a future input only for an exact, contiguous 390-minute QQQ regular session;
   otherwise retain `pending` as a source-coverage fact.
3. Do not change initial anchors, continuation semantics, pagination cap, or
   schedule unless a new concrete contradiction appears. Any such change needs
   the required Claude falsification-first review before implementation.

### Engine Research Agent

Keep the frozen historical baselines and prospective contract unchanged. A
partial head slice remains neither a model sample nor a selection/GPU input.

### Execution Agent

Keep paper-only routing and existing daily/quote schedules unchanged. Do not
infer a fill, terminal state, or PnL from task success or daily no-intent
evidence.

## Completion Evidence

- Sanitized evidence covers all three scheduled windows, or accurately records
  a scoped task/recovery anomaly.
- The metadata-only preparer classifies the resulting QQQ coverage without
  reading raw rows or becoming an approval gate.
- Research and Execution boundaries remain unchanged; no duplicate scheduler,
  broker route, or raw artifact is introduced.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Classify intraday head coverage cycle`
