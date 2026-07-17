# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Run one bounded fresh-symbol local-paper replay probe for non-AMAT evidence
outside the current bridge lineage.

This advances feature/model research, backtest validation, PnL attribution, and
paper-trading preparation by seeking fresh timing-context evidence rather than
reusing the same prior AMAT-bridge rows again.

## Current Agent Reality

- Engine Research Agent has an executable single-shot worker:
  `thericher-v2-engine-research-agent`.
- Data Agent has an executable single-shot worker:
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
- Do not add a new research job kind.
- Do not run ablation, training, threshold search, data acquisition, or new
  executable workers.
- Do not download market data into the Git workspace.
- Do not store generated GPU/model artifacts in the repo. Use
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`.
- Use Docker/GPU only through the existing Engine Research Agent single-shot
  runner and existing research job kinds if the selected replay probe requires
  it.
- Replay must remain broker-free local paper only. Generated fills must be
  `source: local_paper`; reconstructed or summary rows must be
  `source: diagnostic_overlay`.
- Avoid promotional model-quality language except when quoting unavoidable
  existing artifact field names.
- Do not convert diagnostic context into an execution filter, order intent,
  replay rule, feature rule, threshold rule, or model-promotion rule.

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
   - Engine Research: select one bounded existing feature-branch replay shape
     and review whether the probe is narrow enough.
   - Data/Infra: verify candidate fresh symbols have enough existing local
     Yahoo rows and Docker/runner readiness if compute is needed.
   - Review/Execution: verify local-paper-only source labels, broker
     boundaries, and multi-agent drift.

4. Ask Claude CLI for a short drift-check before architecture-changing edits.
   If it times out, record that and keep changes tightly scoped.

## Evidence To Consume

- Non-AMAT label-ready inventory:
  `D:\thericher-v2\model-artifacts\feature-input-stability\engine-agent-non-amat-label-ready-inventory-20260717-r1\metrics.json`
- Non-AMAT feasibility decision:
  `D:\thericher-v2\model-artifacts\feature-input-ablation\engine-agent-non-amat-bridge-feasibility-decision-20260717-r1\metrics.json`
- First-evaluation wider-holdout attribution:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-entry-adverse-firsteval-source-context-wider-holdout-depth-attribution-20260717\metrics.json`
- Existing feature-branch artifacts referenced by that attribution, especially
  the short and depth source-context feature branches.
- Local market data:
  `D:\market_data\us_equities\yahoo_intraday_starter\canonical\ohlcv_1m\snapshot=2026-06-18\ohlcv_1m.csv.gz`

## Required Work

1. Exclude symbols and timing contexts already used by the current non-AMAT
   baseline and prior AMAT bridge lineage:
   - ADBE, ADI, ADP, AEM, AMAT, AMZN, and BA timing contexts already recorded
     in the current branch.
2. Select a very small fresh-symbol set from existing `snapshot=2026-06-18`
   rows. Prefer symbols with at least `240` bars and no current-branch timing
   reuse.
3. Use only an existing feature-branch replay shape and existing research job
   kind. Do not create a new job kind, helper, replay path, threshold search,
   or model axis.
4. If a replay probe is run, run one bounded broker-free local-paper replay
   through the existing Engine Research Agent runner or the equivalent existing
   Docker `research` command shape. Keep artifacts outside Git.
5. If Docker/runner readiness or artifact lineage blocks a safe replay, record
   a compact external blocked/selection artifact instead of inventing new
   plumbing.
6. After the probe, build one compact external artifact that records:
   - selected symbols and exclusion rationale,
   - replay or blocked command lineage,
   - local-paper fill-source evidence,
   - any fresh non-AMAT timing contexts found,
   - whether those contexts are candidates for a later strict label-ready
     bridge,
   - no broker/KIS/credential/data-acquisition behavior.
7. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose config --quiet
```

Also report:

- any focused artifact-only smoke command,
- any Engine Research/Data Agent runner command used,
- any sidecars used,
- artifact paths written outside Git,
- whether Docker/GPU compute was used and why.

## Suggested Commit Message

`Probe fresh-symbol local-paper evidence`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- which sidecars or executable workers were used,
- data found or acquired under `D:\market_data`,
- data still needed from the operator, if any,
- whether GPU/Docker compute was used and where artifacts were written,
- produced replay/diagnostic artifacts,
- local-paper source evidence,
- diagnostic-overlay source evidence,
- what was intentionally not built,
- next goal.
