# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Attribute the fresh-symbol replay-selection trade paths and PnL.

This advances PnL attribution and backtest validation by consuming the `100`
broker-free local-paper fills created by the fresh-symbol replay-selection and
turning them into compact closed/open trade-path evidence before any broader
replay, model training, feature rule, or threshold iteration.

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
  threshold search, or data acquisition.
- Do not download market data into the Git workspace.
- Do not store generated GPU/model artifacts in the repo. Use
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`.
- Keep diagnostic/path context labeled as `source: diagnostic_overlay`.
- Preserve all referenced fills as `source: local_paper`.
- Do not turn attribution into a live execution threshold, order-intent
  generator, risk rule, broker policy, feature rule, gate, or model-promotion
  rule.

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
   - Engine Research: verify trade-path helper shape and attribution fields.
   - Data: verify selected MRVL/MU/SNDK/COHR local bar context.
   - Execution/Review: verify local-paper-only fills, diagnostic-overlay
     context, and no execution/gate semantics.

4. Ask Claude CLI for a short drift-check before adding or changing any helper,
   job kind, dispatch path, agent governance, or attribution contract. If the
   existing trade-path attribution helper can consume the artifacts safely,
   prefer that over adding code.

## Evidence To Consume

- Replay-selection compact artifact:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-selection\engine-agent-fresh-symbol-replay-selection-20260717-r1\metrics.json`
- Replay-selection robustness artifact:
  `D:\thericher-v2\model-artifacts\candidate-threshold-robustness\engine-agent-fresh-symbol-replay-selection-20260717-r1\metrics.json`
- Trace-only batch summary:
  `D:\thericher-v2\model-artifacts\candidate-probability-trace-batch\engine-agent-fresh-symbol-trace-only-batch-20260717-r1\metrics.json`
- Local market data:
  `D:\market_data\us_equities\yahoo_intraday_starter\canonical\ohlcv_1m\snapshot=2026-06-18\ohlcv_1m.csv.gz`

Known replay-selection facts to confirm:

- `4` slices completed: MRVL, MU, SNDK, COHR.
- `12` threshold variants completed using:
  - `0.541000 / 0.497000`
  - `0.542000 / 0.497000`
  - `0.543000 / 0.497000`
- `100` local-paper order intents and `100` local-paper fills were observed.
- Fill-source verification reported `fill_source_counts: {"local_paper": 100}`,
  `non_local_fill_source_counts: {}`, `unknown_fill_count: 0`, and
  `all_fills_local_paper: true`.
- PnL evidence is mixed: MRVL and MU variants were positive, while SNDK and
  COHR were negative.

## Required Work

1. Confirm the replay-selection artifact and robustness artifact match the facts
   above and that all fills remain `source: local_paper`.
2. Parse the existing replay event artifacts only. Do not rerun replay.
3. Load only the selected MRVL, MU, SNDK, and COHR local bars needed to attribute
   those event paths.
4. Use or adapt the existing trade-path attribution helper if it fits. Prefer a
   direct artifact script over a new job kind.
5. Produce one compact external attribution artifact recording:
   - symbols and threshold variants consumed,
   - event artifacts consumed,
   - local-paper fill-source verification,
   - closed path count and open path count,
   - per-symbol and per-threshold PnL/drawdown/path summary,
   - adverse/favorable movement context where available,
   - repeated-threshold/duplicate-market-moment notes,
   - diagnostic rows labeled `source: diagnostic_overlay`,
   - no promotion/gate/execution-rule semantics.
6. If attribution identifies a clear bounded model-input or exit-timing question,
   refresh `NEXT_CODEX_GOAL.md` toward one artifact-only or helper-sized follow
   up. If attribution is too mixed or duplicated, rotate to review/simplification
   instead of forcing another replay/training block.
7. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose config --quiet
```

Also report:

- the attribution command or focused smoke used,
- any sidecars used,
- whether Docker/GPU was used,
- produced attribution artifact path,
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
- produced attribution artifacts,
- local-paper source evidence,
- diagnostic-overlay source evidence,
- what was intentionally not built,
- next goal.
