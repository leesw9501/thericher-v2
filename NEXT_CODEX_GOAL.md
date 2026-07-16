# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Do a bounded simplification and contract pass over the recent raw pre-entry
attribution helpers.

This advances feature/model research, PnL attribution, and review/simplification
by keeping the raw pre-entry evidence reusable before another model, diagnostic
axis, or GPU training block is added.

## Hard Boundaries

- Do not call KIS APIs.
- Do not place paper or live orders through any broker.
- Do not read credentials, `.env`, or secret-like files.
- Do not expose a public dashboard.
- Do not import v1 modules wholesale.
- Do not create report/gate sprawl.
- Do not create a durable multi-agent platform, scheduler, daemon, or
  auto-commit worker.
- Do not add a new research job kind unless an existing test proves it removes
  more complexity than it adds.
- Do not download market data into the Git workspace.
- Do not store generated GPU/model artifacts in the repo. Use
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`.
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

- Raw pre-entry band-attribution artifact:
  `D:\thericher-v2\model-artifacts\feature-input-ablation\bounded-feature-input-ablation-raw-band-attribution-cross-slice-20260717-r1\metrics.json`
- Raw pre-entry outcome-attribution artifact:
  `D:\thericher-v2\model-artifacts\raw-pre-entry-outcome-attribution\bounded-raw-pre-entry-outcome-attribution-cross-slice-20260717-r1\metrics.json`
- Source stability artifact:
  `D:\thericher-v2\model-artifacts\candidate-depth-target-feature-input-stability\engine-agent-depth-target-explicit-slices-20260717-r1-cross-slice-feature-input-stability\metrics.json`

## Required Work

1. Inventory only the code and artifact subset needed to understand recent raw
   pre-entry attribution:
   - `feature_input_ablation.py`
   - `raw_pre_entry_outcome_attribution.py`
   - focused tests for both helpers
   - the two external raw pre-entry artifacts above.
2. Keep the pass small. Prefer tests, naming cleanup, and shared contract checks
   over new abstractions. Add a shared helper only if it removes meaningful
   duplication or prevents artifact-contract drift.
3. Verify and, if useful, codify the contract between:
   - diagnostic rows (`source: diagnostic_overlay`),
   - raw feature names,
   - unique-signal or observation keys,
   - local-paper outcomes (`source: local_paper`),
   - artifact roots outside Git.
4. Add or tighten focused tests proving:
   - no new job kind or scheduler is introduced,
   - raw-band and raw-outcome payloads remain descriptive-only,
   - local-paper outcome attribution does not import broker submit/order-intent
     paths,
   - missing evidence is reported rather than inferred,
   - artifact paths stay outside Git or are mocked in tests,
   - no threshold/rule/promotion language is introduced in payload scopes.
5. Do not run GPU training. Run only CPU/focused artifact smoke commands if they
   materially verify the simplification.
6. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

## Data Policy

- Prefer existing `D:\market_data` snapshots before acquiring anything new.
- This task should use existing artifacts and data, not expand the dataset.
- Acquire additional data only when it is no-auth, lawful,
  license-compatible, and useful for the active engine loop.
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

Also report any focused CPU smoke, Docker `research`, or GPU command used.

## Suggested Commit Message

`Tighten raw pre-entry attribution contracts`

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
