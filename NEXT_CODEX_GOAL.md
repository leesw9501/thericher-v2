# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Diagnose the zero-fill opportunity gap from the first bounded parallel-agent
research cadence, then queue the next bounded GPU experiment only if the
diagnostic shows enough actionable replay opportunity.

This advances feature/model research, backtest and walk-forward validation, and
PnL attribution by preventing the GPU lane from spending long blocks on a
threshold edge that produces no local-paper fills.

## Hard Boundaries

- Do not call KIS APIs.
- Do not place paper or live orders through any broker.
- Do not read credentials, `.env`, or secret-like files.
- Do not expose a public dashboard.
- Do not import v1 modules wholesale.
- Do not create report/gate sprawl.
- Do not create a durable multi-agent platform, scheduler, daemon, notification
  loop, or auto-commit worker.
- Do not add a new executable agent unless a specific engine loop need is
  proven and the user explicitly approves it.
- Do not add a new research job kind unless an existing test proves it removes
  more complexity than it adds.
- Do not download market data into the Git workspace.
- Do not store generated GPU/model artifacts in the repo. Use
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`.
- Keep PyTorch CUDA inside Docker `research` or the existing Engine Research
  Agent runner path. Do not add PyTorch to the base/runtime app path.
- Keep original local-paper fills labeled with `source: local_paper`; keep
  diagnostic rows labeled with `source: diagnostic_overlay`.
- Do not call any context, band, threshold, model, slice, or feature group
  selected, passed, promoted, production ready, or live ready.
- Do not convert a diagnostic feature context into an execution filter, order
  intent, replay rule, feature rule, or model-promotion rule.

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

3. Ask Claude CLI for a short drift-check before architecture-changing edits.
   If it times out, record that and keep the change tightly scoped.

## Current Evidence To Consume

- Engine Research Agent status:
  `D:\thericher-v2\model-artifacts\engine-research-agent\runs\engine-agent-feature-replay-firsteval-depth-adbe-adi-adp-20260717-r1\status.json`
- Short replay artifact:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay\engine-agent-feature-replay-firsteval-depth-adbe-adi-adp-20260717-r1\metrics.json`
- Robustness artifact:
  `D:\thericher-v2\model-artifacts\candidate-threshold-robustness\engine-agent-feature-replay-firsteval-depth-adbe-adi-adp-20260717-r1-robustness\metrics.json`
- Data Agent inventory:
  `D:\thericher-v2\model-artifacts\data-agent\market-data-inventory\data-agent-market-data-inventory-cadence-20260717-r2\metrics.json`

## Required Work

1. Inventory only the artifact subset needed to explain why the ADBE/ADI/ADP
   replay produced `0` fills:
   - source probability range,
   - derived buy/sell threshold pairs,
   - per-slice probability traces or robustness rows if available,
   - local-paper event artifacts,
   - existing `D:\market_data` rows only if trace timestamps need context.
2. Produce a compact artifact-only opportunity-gap summary outside Git under
   `D:\thericher-v2\model-artifacts`. Prefer a one-off artifact first. Add a
   reusable helper only if it removes meaningful duplication or prevents a
   repeated manual calculation.
3. The summary must report counts, not decisions:
   - candidate bars or trace rows per slice,
   - buy-threshold near misses,
   - max probability versus minimum buy threshold,
   - potential opportunity counts at already-derived thresholds only,
   - local-paper fill/source verification,
   - missing evidence counts.
4. If the gap diagnostic shows enough replay opportunity in an existing short
   slice set, queue one bounded Engine Research Agent GPU/Docker `research`
   job using an existing research job kind. If not, do not queue a longer
   candidate; recommend the next short experiment instead.
5. Keep the Engine Research queues visible in `agents/engine-research.md`:
   - short experiments for breadth,
   - longer candidate training for depth.
6. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

## Data Policy

- Prefer existing `D:\market_data` snapshots before acquiring anything new.
- This task should not acquire data unless a no-auth, lawful,
  license-compatible source clearly improves the zero-fill diagnosis.
- Stop acquisition for a source when it requires credentials/payment/manual
  access, licensing is unclear, two automated attempts fail, or more data no
  longer improves the active goal.
- If operator help is needed, record exact artifact names, symbols, markets,
  date ranges, formats, and blocker reasons in `agents/data.md`,
  `agents/execution.md`, and the completion report.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose config --quiet
```

Also report:

- any focused tests,
- any artifact-only smoke command,
- any Engine Research Agent command,
- Docker `research` or GPU command if used,
- artifact paths written outside Git.

## Suggested Commit Message

`Diagnose zero-fill replay opportunity gap`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- data found or acquired under `D:\market_data`,
- data still needed from the operator, if any,
- whether GPU/Docker were used and where artifacts were written,
- produced diagnostic or research artifacts,
- local-paper source evidence,
- diagnostic-overlay source evidence,
- sub-agents used and what they checked,
- what was intentionally not built,
- next goal.
