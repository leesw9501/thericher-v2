# Next Codex Goal

Read `HANDOFF.md`, `VISION.md`, `ARCHITECTURE.md`, `AGENTS.md`,
`DECISIONS.md`, `RUNBOOK.md`, `agents/README.md`, `agents/data.md`,
`agents/engine-research.md`, `agents/research-steward.md`,
`agents/execution.md`, and `agents/orchestration.md` first. Then continue from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build and run `tiingo-d1-trio-intraday-compression-continuation-falsification-v1`.

This is one CPU-only, repeat-source, non-promoting falsification of a distinct
completed-D1 price-compression and intraday-strength hypothesis. It uses an
already immutable local Tiingo `SPY/QQQ/IWM` snapshot, while Data and Execution
continue their independent work. It is not an independent holdout, model
selection surface, or a retry of any closed Tiingo family.

## Hard Boundaries

- Do not call Tiingo, KIS, or another network service.
- Do not read `.env`, credentials, tokens, account facts, or secret-like files.
- Do not submit, modify, cancel, or simulate a broker/Paper order.
- Do not use CUDA, train a model, load public weights, create a checkpoint, or
  allocate the GPU.
- Do not inspect prior Tiingo result artifacts, metrics, or summaries to select
  the rule, thresholds, symbols, split, or outcome interpretation.
- Do not reuse an existing target-day event mask. A target may not be excluded
  using any `t+1` fact.
- Keep raw data on `D:\market_data`; keep new artifacts only under
  `D:\thericher-v2\model-artifacts`; never write artifacts in Git.

## Frozen Contract

- Reattest only the immutable local snapshot
  `D:\market_data\us_equities\tiingo_etf_daily\canonical\snapshot=20260801T173121Z-tiingo-etf-d1-r1`
  with dataset hash
  `sha256:b47539a373bf2d625ad2380376808cf412219f6c5d932b66631bb3aa553683cf`.
  Pin its manifest identity. Align only common completed D1 sessions for
  `SPY`, `QQQ`, and `IWM`; do not blend any source.
- At completed D1 `t`, a symbol qualifies only when all are true from data at
  or before `t`:
  - `(high - low) / open <= 0.75 * median(prior 20 completed range/open)`,
  - `close_location = (close - low) / (high - low) >= 0.75`,
  - `close > open`, and
  - every bar in the causal `t-20..t` chain is valid, has positive OHLCV, has
    no dividend/split marker, and has no absolute close-to-close move of at
    least 20 percent.
- A zero range, nonpositive value, invalid chronology, incomplete common
  session, non-D1 row, event marker, discontinuity, or missing causal history
  abstains. Nothing may be repaired by a forward value.
- The candidate equal-weights every qualifying ETF at `t`; no qualifying ETF
  means flat. Each target is the selected ETF basket's `t+1 open -> close`
  return. The active equal-exposure comparator is an equal-weight basket of
  all three ETFs on exactly the candidate-active decision dates; the other
  comparator is flat.
- Split the common chronology into first 70 percent development, then a fixed
  61-session purge, then the remaining validation segment. Enforce the actual
  feature/target dependency separation rather than trusting the label alone.
  Use development only for a target-free structural signal census requiring at
  least 100 eligible signals across all three symbols. Do not open a target if
  that census fails.
- Validation requires at least 60 candidate-active decision dates before any
  target is opened. Evaluate the fixed all-in round-trip cost band `10/15/20`
  bps; `20` bps is primary.
- The null is exactly 64 deterministic permutations of full, joint
  cross-sectional 10-session target-return blocks within validation. The final
  partial block remains fixed. It preserves all three-symbol return vectors,
  block structure, and candidate signal dates while breaking date alignment.
- The candidate is `falsified` when its 20-bp mean net return is nonpositive,
  it does not strictly exceed the equal-exposure comparator at every cost, or
  it does not strictly exceed the fixed null P95 at 20 bps. Otherwise the
  result is `inconclusive_non_promoting`; it cannot become a model, ensemble,
  GPU appointment, PnL/profitability claim, Paper input, or order decision.

## Required Work

1. Add the smallest dedicated Engine Research leaf and offline runner. Reuse
   only the verified Tiingo loader, external artifact custody, and causal split
   idioms needed for this contract. Do not expand an old campaign or build a
   generic strategy framework.
2. Write an immutable external precommit before target evaluation. Persist only
   source identities, frozen geometry, categorical counts/relations, and
   hashes; never rows, dates, OHLCV, target values, predictions, numeric result
   values, credentials, or account data.
3. Add focused tests for common-session alignment, target-free census, exact
   causal and purge boundaries, full abstention conditions, no target-day
   filtering, joint-block null behavior, strict kill logic, direct import
   isolation, external/idempotent redacted artifacts, and a runner with no
   network/environment/broker/GPU route.
4. Run one frozen CPU attempt after precommit. Do not tune or rerun altered
   geometry. A same-contract reattachment may prove idempotence.
5. Update the Engine Research, Data, orchestration, handoff, and decision
   stateboards with the terminal category, repeat-source limitation, and next
   independent data requirement. An `input_unavailable` or `falsified` result
   must not stop another ready lane.

## Claude Review

The pre-implementation source-safe falsification request for this contract
timed out after its bounded command window. Record `review_unavailable`; do not
claim Claude endorsement. This early, CPU-only, non-promoting falsification has
no promotion, holdout, GPU, execution, broker, or authority consequence. Its
strongest kill test remains the fixed 20-bp/equal-exposure/null triad.

## Verification

Run focused tests and the frozen offline CPU runner, then:

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example --profile research config --quiet
```

If the clean-root helper remains blocked by its known interrupted run roots,
do not delete, rename, or bypass them. Record that scoped recovery fact and run
the helper's independent fresh-root mode plus the remaining verification
commands.

## Completion

Report the frozen rule and split, terminal category, artifact hashes/locations,
focused and full verification, and why the result created no GPU/model/PnL/
KIS/Paper/live claim. Commit and push completion evidence before replacing this
file with exactly one next objective and continuing.
