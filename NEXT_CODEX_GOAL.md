# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Run one compact duplicate-aware simplification pass over the fresh-symbol
replay-selection attribution.

This advances PnL attribution and backtest validation by collapsing the
threshold-duplicated MRVL/MU/SNDK/COHR trade-path evidence into unique market
moments before any broader replay, model training, feature rule, exit rule, or
threshold iteration.

## Current Agent Reality

- Engine Research Agent has an executable single-shot Docker research worker:
  `thericher-v2-engine-research-agent`.
- Data Agent has an executable single-shot metadata worker:
  `thericher-v2-data-agent`.
- Execution, Infra, and Review are stateboards plus temporary Codex sidecar
  roles, not repo-owned executable workers.
- Temporary sidecars may run in parallel for scoped review, but do not build a
  durable multi-agent platform, scheduler, daemon, coordinator, notification
  loop, or auto-commit worker in this goal.

## Hard Boundaries

- Do not call KIS APIs.
- Do not place paper or live orders through any broker.
- Do not read credentials, `.env`, or secret-like files.
- Do not expose a public dashboard.
- Do not import v1 modules wholesale.
- Do not create report/gate sprawl.
- Do not create a durable multi-agent platform, scheduler, daemon,
  notification loop, coordinator, or auto-commit worker.
- Do not run model training, ablation, trace recomputation, replay reruns,
  threshold search, exit-policy simulation, or data acquisition.
- Do not download market data into the Git workspace.
- Do not store generated GPU/model artifacts in the repo. Use
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`.
- Keep diagnostic/path context labeled as `source: diagnostic_overlay`.
- Preserve all referenced fills as `source: local_paper`.
- Do not turn simplification into a live execution threshold, order-intent
  generator, risk rule, broker policy, feature rule, exit rule, gate, or
  model-promotion rule.

## Required First Reads

1. Run:

   ```powershell
   .\scripts\start_next_codex_task.ps1
   ```

2. Then read:
   - `HANDOFF.md`
   - `VISION.md`
   - `ARCHITECTURE.md`
   - `AGENTS.md`
   - `DECISIONS.md`
   - `RUNBOOK.md`
   - `agents/README.md`
   - `agents/engine-research.md`
   - `agents/data.md`
   - `agents/execution.md`
   - `agents/infra.md`
   - `agents/review.md`

3. Use temporary Codex sidecars for disjoint checks when useful:
   - Engine Research: verify duplicate-aware grouping and possible next
     research question.
   - Execution/Review: verify source separation and no rule/gate semantics.
   - Data: verify no new market-data read is needed beyond existing artifacts.

4. Ask Claude CLI for a short drift-check before adding or changing any helper,
   job kind, dispatch path, agent governance, or attribution contract. If the
   simplification can be done as a direct artifact script, prefer that over
   adding code.

## Evidence To Consume

- Trade-path attribution artifact:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\engine-agent-fresh-symbol-replay-selection-trade-path-20260717-r1\metrics.json`
- Replay-selection compact artifact:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-selection\engine-agent-fresh-symbol-replay-selection-20260717-r1\metrics.json`
- Replay-selection robustness artifact:
  `D:\thericher-v2\model-artifacts\candidate-threshold-robustness\engine-agent-fresh-symbol-replay-selection-20260717-r1\metrics.json`

Known attribution facts to confirm:

- `100` referenced fills remained `source: local_paper`.
- `50` closed segments and `0` open segments were attributed.
- Closed fee-aware delta sum was `-18.6423`.
- Symbol fee-aware sums were:
  - MRVL: `+4.8555`
  - MU: `+28.3638`
  - SNDK: `-41.9307`
  - COHR: `-9.9309`
- `17` duplicate closed market moments were recorded across nearby threshold
  variants.

## Required Work

1. Confirm the attribution artifact matches the facts above and remains
   local-paper-only.
2. Collapse closed trade paths into unique market-moment keys, at minimum:
   symbol, entry timestamp, exit timestamp, and direction.
3. Summarize duplicate-aware evidence by symbol and by threshold band:
   - unique market-moment count,
   - repeated threshold-variant count,
   - negative/non-negative fee-aware count,
   - fee-aware delta sum/min/max,
   - adverse/favorable path context.
4. Record whether the apparent SNDK and COHR losses survive duplicate collapse,
   and whether MU/MRVL positive paths are independent enough to justify another
   bounded question.
5. Produce one compact external simplification artifact recording:
   - consumed artifact paths,
   - duplicate-aware grouping rules,
   - local-paper source verification carried forward,
   - diagnostic-overlay source verification,
   - hold/continue recommendation for this branch,
   - no promotion/gate/execution-rule semantics.
6. Refresh `NEXT_CODEX_GOAL.md` again before ending:
   - If a bounded next question is justified, make it artifact-only or
     helper-sized first.
   - If evidence remains mixed or duplicate-heavy, rotate to review,
     simplification, or another lane instead of forcing replay/training.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose config --quiet
```

Also report:

- the simplification command or focused smoke used,
- any sidecars used,
- whether Docker/GPU was used,
- produced simplification artifact path,
- whether a future model/replay follow-up is justified.

## Suggested Commit Message

`Attribute fresh-symbol replay paths`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- which sidecars or executable workers were used,
- data found or acquired under `D:\market_data`,
- data still needed from the operator, if any,
- whether GPU/Docker compute was used and where artifacts were written,
- produced simplification artifacts,
- local-paper source evidence,
- diagnostic-overlay source evidence,
- what was intentionally not built,
- next goal.
