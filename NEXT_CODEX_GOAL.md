# Next Codex Goal

## Objective

Complete `firstrate-5m-after-cost-control-v1`: build and run one frozen,
CPU-only, source-local SPY/QQQ 5m predictive control that determines whether a
simple fixed model can survive explicit nonzero costs before any FirstRate GPU
architecture matrix is proposed.

## Boundaries

- Run `./scripts/start_next_codex_task.ps1` first, then read `HANDOFF.md`,
  `AGENTS.md`, `RUNBOOK.md`, and the active stateboards. Reuse the recorded
  Claude `supported-with-limits` review; ask again only if scope materially
  widens.
- Use only the existing FirstRate SPY/QQQ canonical external data and local
  resampling path. Do not acquire data, read credentials, call KIS, call a
  broker, submit an order, or use a network route.
- Freeze before fitting: contiguous complete 5m windows; a past-60-bar
  observation window; one-5m-bar forward direction target; one chronological
  train/validation split with an embargo of at least the observation plus target
  horizon; no time-of-day, session-reset, cross-feed, or cross-symbol feature.
- Freeze `always_flat` and previous-bar-direction as baselines, one L2-logistic
  control, a 0.5 decision threshold, terminal-flat `local_paper` replay, and a
  synthetic 1/3/5-bps per-side cost-sensitivity band. These costs are a
  source-local falsification band, not KIS execution parity.
- The strongest kill test is that every modeled control fails to beat
  `always_flat` after every nonzero cost. Positive zero-cost-only behavior is a
  rejection. An input geometry failure returns `input_unavailable` before any
  fit. Do not tune windows, thresholds, signs, costs, or model parameters after
  observing output.
- This is one descriptive control lineage only. It cannot allocate GPU, select
  an architecture, create an ensemble, become a KIS input, or create an
  Execution/Paper consumer. Store any model artifact and source-safe receipt
  only under `D:\thericher-v2\model-artifacts`.

## Required Work

1. Reattest the FirstRate source-local canonical data and 5m contiguous-window
   geometry without emitting raw rows, prices, labels, predictions, or paths.
2. Implement only the frozen CPU control and its source-safe precommit/summary
   evidence. Validation must not tune the fixed configuration.
3. Use temporary Validation to independently reattach the frozen contract and
   classify the result narrowly as `rejected`, `inconclusive`, or
   `eligible_to_propose_gpu`; no result automatically starts a GPU job.
4. Refresh `HANDOFF.md`, `RUNBOOK.md`, and active stateboards with only
   aggregate evidence and the non-promoting limitation.
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
