# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Attribute the explicit-slice Engine Research Agent depth target before spending
more GPU time.

This advances PnL attribution, feature/model research, and backtest and
walk-forward validation by explaining why the completed explicit-slice depth
target generated many local-paper fills with poor holdout PnL.

## Hard Boundaries

- Do not call KIS APIs.
- Do not place paper or live orders through any broker.
- Do not read credentials, `.env`, or secret-like files.
- Do not expose a public dashboard.
- Do not import v1 modules wholesale.
- Do not create report/gate sprawl.
- Do not download market data into the Git workspace.
- Do not acquire market data in this slice unless a tiny no-auth,
  lawful, license-compatible external fixture is absolutely required.
- Do not store generated artifacts in the repo. Use
  `D:\thericher-v2\model-artifacts` or the configured artifact root.
- Do not run new GPU training before attributing the completed explicit-slice
  depth target.
- Do not queue another Engine Research Agent job unless the attribution proves
  the current artifact set is unreadable or incomplete.
- Do not make Execution, Infra, or Review executable workers in this slice.
- Do not add a daemon, scheduler, Windows service, dashboard, notification
  system, broad autonomous multi-agent platform, coordinator, or auto-commit
  path.
- Do not call any threshold, candidate, feature set, preprocessing branch, or
  model best, recommended, passed, promoted, or production ready.

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
   - `agents/data.md`
   - `agents/engine-research.md`
   - `agents/execution.md`
   - `agents/infra.md`
   - `agents/review.md`

3. Ask Claude CLI for a short drift-check before any code or architecture
   edits. If the slice stays artifact-only plus stateboard updates, record why a
   drift-check was not needed.

## Required Work

1. Consume the completed artifact:
   `D:\thericher-v2\model-artifacts\candidate-depth-target\engine-agent-depth-target-explicit-slices-20260717-r1\metrics.json`.
2. Use existing related artifacts only: training metrics, evaluation metrics,
   calibration, holdout, robustness, probability traces, event artifacts, and
   selected local Yahoo rows from `D:\market_data` if needed.
3. Produce one compact external attribution artifact under
   `D:\thericher-v2\model-artifacts`.
4. Explain at least:
   - fill and PnL concentration by holdout slice,
   - fill and PnL concentration by threshold pair,
   - whether the `531` holdout fills are caused by threshold bands sitting too
     close to the probability distribution,
   - whether the holdout max probability outlier `0.957193` is tied to a single
     row or slice,
   - whether loss appears driven by too many entries, delayed exits, or both.
5. Keep all fill evidence labeled and checked as `source: local_paper`.
6. If the existing artifacts are insufficient, record the exact missing
   artifact paths and stop; do not substitute broker, credential, network, or
   dashboard work.
7. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

## Data Policy

- Prefer existing `D:\market_data` snapshots before acquiring anything new.
- This task should use existing data, not expand the dataset.
- Acquire additional data only when it is no-auth, lawful,
  license-compatible, and useful for the active validation loop.
- Stop acquisition for a source when it requires credentials/payment/manual
  access, licensing is unclear, two automated attempts fail, or more data no
  longer improves the active goal.
- If operator help is needed, record exact symbols, markets, date ranges,
  formats, and blocker reasons in `agents/data.md` and the completion report.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose config --quiet
```

Also report any focused artifact-only command used, artifact paths, and
local-paper source evidence.

## Suggested Commit Message

`Attribute explicit-slice depth target`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- data found or acquired under `D:\market_data`,
- data still needed from the operator, if any,
- whether GPU/Docker were used,
- produced attribution artifacts,
- local-paper source evidence,
- what was intentionally not built,
- next goal.
