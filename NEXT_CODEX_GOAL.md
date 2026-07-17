# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build the first bounded fresh-symbol replay opportunity prefilter, then run at
most one small local-paper replay only if the prefilter finds a
threshold-crossing opportunity.

This advances feature/model research, backtest validation, PnL attribution, and
paper-trading preparation by reducing blind zero-fill replays before any more
model-input or training work.

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
- Do not add broker authority to the Engine Research Agent.
- Do not run live or broker paper trading.
- Do not run model training, feature-input ablation, broad threshold search, or
  data acquisition.
- Do not download market data into the Git workspace.
- Do not store generated GPU/model artifacts in the repo. Use
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`.
- Use Docker/GPU only through the existing Engine Research Agent single-shot
  runner and existing research job kinds unless a tiny tested selector can run
  locally without model artifacts entering Git.
- Replay, if run, must remain broker-free local paper only. Generated fills
  must be `source: local_paper`; reconstructed or summary rows must be
  `source: diagnostic_overlay`.
- A probability prefilter must not become an execution threshold, order-intent
  generator, risk rule, broker policy, replay rule, feature rule, or
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
   - Engine Research: review the smallest opportunity-prefilter shape and
     whether an existing research primitive is enough.
   - Data/Infra: verify candidate symbols/windows have enough existing local
     Yahoo rows and Docker/runner readiness if compute is needed.
   - Review/Execution: verify the prefilter cannot become broker/order logic
     and that any replay remains local-paper-only.

4. Ask Claude CLI for a short drift-check before architecture-changing edits.
   If it times out, record that and keep changes tightly scoped.

## Evidence To Consume

- Fresh-symbol no-fill probe:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\engine-agent-fresh-symbol-short-replay-probe-20260717-r1\metrics.json`
- Fresh-symbol replay artifact:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay\engine-agent-fresh-symbol-short-replay-aapl-abbv-abt-acn-20260717-r1\metrics.json`
- Fresh-symbol robustness artifact:
  `D:\thericher-v2\model-artifacts\candidate-threshold-robustness\engine-agent-fresh-symbol-short-replay-aapl-abbv-abt-acn-20260717-r1-robustness\metrics.json`
- Short source-context feature branch:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch\bounded-entry-adverse-firsteval-source-context-validation-20260716\metrics.json`
- Prior non-AMAT decision:
  `D:\thericher-v2\model-artifacts\feature-input-ablation\engine-agent-non-amat-bridge-feasibility-decision-20260717-r1\metrics.json`
- Local market data:
  `D:\market_data\us_equities\yahoo_intraday_starter\canonical\ohlcv_1m\snapshot=2026-06-18\ohlcv_1m.csv.gz`

## Required Work

1. Record why the previous fresh replay produced no fills:
   - selected symbols AAPL, ABBV, ABT, and ACN,
   - derived threshold pairs `0.541/0.497`, `0.542/0.497`, `0.543/0.497`,
   - best observed probability ACN `0.535336`, below the minimum buy threshold,
   - `0` order intents, `0` fills, and `0` strict-bridge timing contexts.
2. Define a bounded opportunity-prefilter that ranks fresh local slices by
   probability versus the derived buy threshold. Prefer reusing existing
   probability-trace or robustness primitives. A small tested selector in the
   existing research package is allowed only if it directly prevents repeated
   zero-fill replay work and does not add a worker, scheduler, gate, or report
   family.
3. Exclude symbols and timing contexts already used by the current baseline,
   prior AMAT bridge lineage, and the no-fill fresh replay:
   - ADBE, ADI, ADP, AEM, AMAT, AMZN, BA,
   - AAPL, ABBV, ABT, ACN for immediate replay repetition.
4. Use existing `snapshot=2026-06-18` rows first. Avoid expensive full
   recursive scans. Start with at most `12` fresh candidate symbols and at most
   `240` bars per symbol unless the codebase already has a safer smaller
   convention.
5. Produce one compact external prefilter artifact recording:
   - candidate symbols/windows,
   - data row counts and selected-window warnings,
   - probability maxima and threshold gaps,
   - threshold-crossing candidates, if any,
   - excluded symbols and rationale,
   - no broker/KIS/credential/data-acquisition behavior.
6. If no candidate crosses the derived buy threshold, stop the branch for this
   goal and refresh `NEXT_CODEX_GOAL.md` toward a lane rotation instead of
   forcing another replay.
7. If one or more candidates cross the derived buy threshold, run at most one
   bounded broker-free local-paper replay through the existing Engine Research
   Agent runner or equivalent existing Docker `research` command shape:
   - at most `4` symbols,
   - at most `240` bars per symbol,
   - existing research job kind only,
   - artifacts outside Git.
8. After any replay, write one compact external artifact recording local-paper
   fill-source evidence, fresh timing contexts, and whether any contexts are
   candidates for a later strict label-ready bridge.
9. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose config --quiet
```

Also report:

- any focused artifact or selector smoke command,
- any Engine Research/Data Agent runner command used,
- any sidecars used,
- artifact paths written outside Git,
- whether Docker/GPU compute was used and why.

## Suggested Commit Message

`Add fresh-symbol opportunity prefilter`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- which sidecars or executable workers were used,
- data found or acquired under `D:\market_data`,
- data still needed from the operator, if any,
- whether GPU/Docker compute was used and where artifacts were written,
- produced prefilter/replay/diagnostic artifacts,
- local-paper source evidence,
- diagnostic-overlay source evidence,
- what was intentionally not built,
- next goal.
