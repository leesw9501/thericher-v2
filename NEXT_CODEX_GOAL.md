# Next Codex Goal

## Objective

Complete `firstrate-m5-trend-rule-after-cost-control-v1`: build and run one
frozen, CPU-only, source-local SPY/QQQ 5m technical trend-rule control after
the closed L2-logistic lineage rejected every nonzero-cost comparison.

## Boundaries

- Run `./scripts/start_next_codex_task.ps1` first, then read `HANDOFF.md`,
  `AGENTS.md`, `RUNBOOK.md`, and the active stateboards. Reuse the current
  source-local limits; ask Claude for a concise falsification-first challenge
  only if the frozen rule or consumer scope materially widens.
- Use only the existing FirstRate SPY/QQQ canonical external data and local
  resampling path. Do not acquire data, read credentials, call KIS, call a
  broker, submit an order, use a network route, or allocate GPU.
- Freeze before replay: complete contiguous 5m windows; a causal 20/60-bar
  same-symbol trend rule; one chronological train-equivalent calibration-free
  development/validation split with an embargo of at least the maximum window
  plus target horizon; no time-of-day, session-reset, cross-feed, or
  cross-symbol feature.
- Freeze `always_flat` and previous-bar-direction baselines, terminal-flat
  `local_paper` replay, and the same synthetic 1/3/5-bps per-side cost band.
  These costs are a source-local falsification band, not KIS execution parity.
- The strongest kill test is that the trend rule fails to beat `always_flat` in
  all six SPY/QQQ nonzero-cost cells. Do not tune rule direction, windows,
  thresholds, costs, or exit after any outcome is read.
- This is one descriptive technical-rule lineage only. It cannot allocate GPU,
  select an architecture, create an ensemble, become a KIS input, or create an
  Execution/Paper consumer. Store all generated artifacts only under
  `D:\thericher-v2\model-artifacts`.

## Required Work

1. Reattest the FirstRate source-local canonical data and complete contiguous
   5m geometry without emitting raw rows, prices, labels, predictions, or
   paths.
2. Implement only the frozen 20/60-bar trend rule and source-safe
   precommit/summary evidence. The rule must be calibration-free and must not
   train a model or allocate GPU.
3. Use temporary Validation to independently reattach the frozen contract and
   classify the result narrowly as `rejected`, `inconclusive`, or
   `eligible_to_propose_gpu`; no result automatically starts a GPU job.
4. Refresh `HANDOFF.md`, `RUNBOOK.md`, and active stateboards with aggregate
   evidence and the non-promoting limitation.
5. Run required verification, commit, push, replace this file with exactly one
   material next objective, and continue.

## Verification

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example --profile research config --quiet
git diff --check
```
