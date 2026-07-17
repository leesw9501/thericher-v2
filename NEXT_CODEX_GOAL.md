# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Run one bounded fresh-symbol broker-free local-paper replay-selection from the
strongest trace-only crossing symbols.

This advances backtest validation and PnL attribution by converting the best
fresh-symbol probability traces into a small local-paper replay, without KIS,
credentials, live/paper broker calls, training, or broader search.

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
- Do not run model training, feature-input ablation, trace recomputation, broad
  threshold search, or data acquisition.
- Do not download market data into the Git workspace.
- Do not store generated GPU/model artifacts in the repo. Use
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`.
- Prefer existing trace artifacts and existing broker-free local-paper replay
  primitives. Do not add a new job kind or executable worker unless direct
  helper use is impossible, and ask Claude CLI first if a dispatch change is
  needed.
- Keep diagnostic context labeled as `source: diagnostic_overlay`.
- Any fills created by the local simulator must remain `source: local_paper`.
- Do not turn replay-selection into a live execution threshold, order-intent
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
   - Engine Research: verify the replay-selection helper shape and threshold
     pairs.
   - Execution/Review: verify local-paper-only fills and no execution/gate
     semantics.
   - Infra: verify Docker `research` only if replay runs in Docker.

4. Ask Claude CLI for a short drift-check before adding or changing any
   research-job dispatch path. If existing helper calls can consume the traces
   safely, prefer that over adding code.

## Evidence To Consume

- Trace-only batch summary:
  `D:\thericher-v2\model-artifacts\candidate-probability-trace-batch\engine-agent-fresh-symbol-trace-only-batch-20260717-r1\metrics.json`
- Short source-context feature branch:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch\bounded-entry-adverse-firsteval-source-context-validation-20260716\metrics.json`
- Local market data:
  `D:\market_data\us_equities\yahoo_intraday_starter\canonical\ohlcv_1m\snapshot=2026-06-18\ohlcv_1m.csv.gz`

Top crossing traces to replay first:

- MRVL:
  `D:\thericher-v2\model-artifacts\candidate-probability-trace\engine-agent-fresh-symbol-trace-only-batch-20260717-r1-fresh_mrvl\trace.json`
- MU:
  `D:\thericher-v2\model-artifacts\candidate-probability-trace\engine-agent-fresh-symbol-trace-only-batch-20260717-r1-fresh_mu\trace.json`
- SNDK:
  `D:\thericher-v2\model-artifacts\candidate-probability-trace\engine-agent-fresh-symbol-trace-only-batch-20260717-r1-fresh_sndk\trace.json`
- COHR:
  `D:\thericher-v2\model-artifacts\candidate-probability-trace\engine-agent-fresh-symbol-trace-only-batch-20260717-r1-fresh_cohr\trace.json`

## Required Work

1. Confirm the trace-only result:
   - `7` requested symbols,
   - `7` completed compatible traces,
   - `7` symbols crossed the fixed descriptive buy threshold `0.541000`,
   - best symbol MRVL max probability `0.565431`, gap `+0.024431`,
   - no replay, no order intents, and no fills in the trace-only batch.
2. Run one bounded replay-selection for only MRVL, MU, SNDK, and COHR.
   Prefer an existing helper path that consumes `probability_trace_artifact`
   directly, such as the threshold-robustness primitive, so the traces do not
   need to be recomputed.
3. Use the fixed feature-branch replay threshold pairs:
   - `0.541000 / 0.497000`
   - `0.542000 / 0.497000`
   - `0.543000 / 0.497000`
4. Keep the replay broker-free and local-paper-only. Verify:
   - all fills, if any, are `source: local_paper`,
   - diagnostic rows remain `source: diagnostic_overlay`,
   - no KIS, credentials, network, broker submit/cancel/status, or live/paper
     external broker behavior occurred.
5. Produce one compact external replay-selection artifact recording:
   - symbols and trace artifacts consumed,
   - threshold pairs used,
   - local-paper fill/order-intent counts,
   - fill-source verification,
   - PnL/path summary if fills occur,
   - no promotion/gate/execution-rule semantics.
6. If replay creates local-paper fills, refresh `NEXT_CODEX_GOAL.md` toward a
   bounded PnL/trade-path attribution goal. If replay still creates no fills,
   rotate to review/simplification or a different Engine Research input
   question instead of repeating fresh-symbol replay.
7. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose config --quiet
```

Also report:

- the replay-selection command used,
- any focused replay-selection smoke/assertion command,
- any sidecars used,
- whether Docker/PyTorch CUDA was used and where artifacts were written,
- whether a future attribution or replay is justified.

## Suggested Commit Message

`Run fresh-symbol replay selection`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- which sidecars or executable workers were used,
- data found or acquired under `D:\market_data`,
- data still needed from the operator, if any,
- whether GPU/Docker compute was used and where artifacts were written,
- produced replay-selection artifacts,
- local-paper source evidence,
- diagnostic-overlay source evidence,
- what was intentionally not built,
- next goal.
