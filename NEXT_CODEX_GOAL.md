# Next Codex Goal

Read `HANDOFF.md`, `VISION.md`, `ARCHITECTURE.md`, `AGENTS.md`,
`DECISIONS.md`, `RUNBOOK.md`, `agents/README.md`, `agents/data.md`,
`agents/engine-research.md`, `agents/research-steward.md`,
`agents/execution.md`, and `agents/orchestration.md` first. Then continue from
`C:\\Users\\Public\\Documents\\thericher-v2`.

## Objective

Build and run `kis-nas-d1-volume-exhaustion-reversal-v1`.

This is one fixed, CPU-only, source-local falsification of a completed-D1
volume-exhaustion reversal rule. It advances Engine Research while independent
Data and Execution schedules wait for fresh sessions. It must not reuse the
already consumed 647-session NAS validation partition, the r4/r5 sealed
results, or any previous candidate outcome as a selection surface.

## Frozen Contract

- Consume only the attested six-symbol KIS NAS D1 `development` phase: 1,510
  common sessions for `AAPL`, `AMZN`, `GOOGL`, `META`, `MSFT`, and `NVDA`.
  Do not access the sequence input's `purge` or `validation` phases in the
  campaign implementation. The historical loader may reattest the parent
  panel, but the campaign must pass only `development` onward.
- Reserve source indices `0..999` for a target-free structural/signal census,
  `1000..1021` as a 22-session purge, and use only decision indices
  `1042..1508` for one fixed falsification. Every target is the next session's
  `open -> close` return at `t+1`; no target is used in the structural census.
- At completed D1 `t`, long only when all are true:
  - `(high - low) / open >= 2.0 * median(prior 20 range/open)`,
  - `close_location = (close - low) / (high - low) <= 0.25`,
  - `close - open < 0`,
  - `volume >= 1.5 * median(prior 20 volume)`, and
  - no close-to-close move with absolute magnitude at least 20 percent exists
    inside the causal `t-20..t` chain.
- A zero range, nonpositive trailing volume median, incomplete/non-D1 bar,
  missing causal chain, or invalid chronology abstains. It must never be
  repaired by looking forward.
- The target-free census requires at least 50 eligible signals spread across
  at least four symbols. Otherwise close `input_unavailable` before opening
  evaluation targets.
- Fixed comparators are `flat` and `candle_only` (the same rule without the
  volume condition). Evaluate round-trip cost bands `10/15/20` bps; 20 bps is
  primary. The candidate is falsified when its 20-bp mean net return is not
  positive, when it does not strictly exceed `candle_only` at every cost, or
  when it does not exceed the fixed null P95 at 20 bps.
- The null is exactly 64 deterministic within-symbol permutations of full
  contiguous 10-session target-return blocks. The final seven-session partial
  block per symbol remains fixed. This preserves each symbol's target blocks
  and signal count while breaking signal-date alignment.
- Any non-falsified result is `inconclusive_non_promoting`, not a winner,
  model, ensemble member, GPU appointment, PnL/profitability claim, or Paper
  input. The source stays current-listing-only, non-PIT, `MODP=0` unadjusted,
  and corporate-action-unqualified.

## Required Work

1. Reuse the existing attested NAS D1 development input and campaign custody
   utilities. Add the smallest dedicated Engine Research leaf plus a narrow
   offline runner; do not create a generic strategy framework, scheduler,
   provider, dashboard, KIS adapter, or model registry.
2. Freeze the rule, split, cost band, null geometry, kill tests, source limits,
   and non-promotion scope into an immutable external artifact under
   `D:\\thericher-v2\\model-artifacts`. Persist only source-safe identities,
   counts, categorical metric relations, and hashes: no rows, dates, OHLCV,
   target values, predictions, account data, or secrets.
3. Add focused tests for causal boundary exclusion, target-free census,
   zero-range/volume/discontinuity abstention, per-symbol block null behavior,
   strict falsification logic, idempotent external custody, and no
   network/environment/KIS/broker/GPU/import route.
4. Run the one frozen CPU attempt after its contract is written. Do not tune
   thresholds, rerun with changed geometry, open the consumed validation phase,
   use CUDA, train a model, write a checkpoint, or submit any Paper intent.
5. Update the Engine Research, Data, orchestration, handoff, and decision
   stateboards with the exact terminal category and the next independent data
   requirement. A target-free/input-unavailable or falsified result must not
   stop other ready lanes.

## Claude Review

The pre-implementation source-safe Claude falsification request for this
candidate exceeded its bounded command timeout, so its result is
`review_unavailable`; do not describe it as endorsement. This is an early,
CPU-only, non-promoting falsification and has no promotion, holdout, GPU,
execution, broker, or authority consequence. Its strongest kill test remains
the fixed 20-bp/candle-only/null triad above.

## Verification

Run focused tests and the frozen offline CPU runner, then:

```powershell
.\\scripts\\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example --profile research config --quiet
```

If the clean-root helper precondition remains blocked by its known interrupted
run roots, do not delete, rename, or bypass them. Record that scoped recovery
fact and run the helper's independent fresh-root mode plus the remaining
verification commands.

## Completion

Report the frozen rule and split, terminal category, artifact hashes/locations,
focused and full verification, and why this result created no GPU/model/PnL/
KIS/Paper/live claim. Commit and push completion evidence before replacing this
file with exactly one next objective and continuing.
