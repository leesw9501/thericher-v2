# Next Codex Goal

Read `HANDOFF.md`, `VISION.md`, `ARCHITECTURE.md`, `AGENTS.md`,
`DECISIONS.md`, `RUNBOOK.md`, `agents/README.md`, `agents/data.md`,
`agents/engine-research.md`, `agents/research-steward.md`,
`agents/execution.md`, and `agents/orchestration.md` first. Then continue from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build and run `kis-d1-candle-noise-floor-v1`: one bounded CPU-only Engine
Research campaign that determines whether a fixed, adjustment-robust
daily-candle logistic baseline has validation association distinguishable from
its predeclared contiguous-block label null on the existing KIS-shaped D1
six-symbol development source.

This is a signal/noise-floor and data-shape result only. It cannot select an
architecture, claim alpha, profitability, PnL, ranking, portfolio allocation,
ensemble membership, Paper input, broker action, or live behavior. A later
encoder campaign requires a new objective even if this one passes.

## Frozen Contract

- Reattest only `load_kis_paper_daily_history_sequence_input` against
  `kis.paper.private.daily.nas.history.panel-v1` and exact dataset hash
  `sha256:7e8d6fe54dd5252fc4b9548b70e3bb31aefcd282922a50c1ca7c58a94d57dc8e`.
  Use its completed-D1 development phase only for `AAPL`, `AMZN`, `GOOGL`,
  `META`, `MSFT`, and `NVDA`. Do not materialize the source's named purge or
  validation phases.
- Each decision uses exactly 32 prior completed D1 candles. Its input contains
  only same-candle log high/open, log low/open, and log close/open values. It
  excludes price levels, prior-close returns, cross-session gaps, volume,
  corporate-action fields, and any data not available by the previous close.
  This narrows, but does not qualify, the source's unverified adjustment and
  availability semantics.
- The in-memory target is only the next completed D1 candle's open-to-close
  direction. No target, prediction, probability, raw bar, date, price, feature
  value, or per-symbol result may be written to Git or an artifact.
- Freeze source-time geometry before target access: per symbol, source sessions
  `0..999` supply training examples (anchors `31..998`), sessions `1000..1032`
  are a 33-session purge, and sessions `1033..1509` supply validation examples
  (anchors `1064..1508`). Missing identities, nonconsecutive sessions, invalid
  OHLC ratios, or insufficient rows end `input_unavailable` before fitting.
- Fit exactly five CPU-only L2 logistic models with the existing project
  dependency, fixed `C=0.1`, no class weighting, threshold `0.50`, and seeds
  `20260802..20260806`. Normalize only from the pooled training examples. The
  fixed non-model comparator is always-long.
- Build exactly 64 validation-label nulls by permuting labels in independent,
  within-symbol contiguous blocks of ten decision sessions. Keep each model's
  predictions fixed while scoring the null labels. Do not shuffle timestamps,
  pool symbols before permutation, tune block length, tune `C`, alter the
  threshold, or add another model family after observing results.
- The strongest kill test is precommitted: `noise_not_separable` unless the
  median actual-label balanced accuracy exceeds the 95th-percentile block-null
  balanced accuracy by at least 0.015 and the five-seed spread is strictly less
  than that excess. A pass is still source-local, non-promoting CPU evidence;
  it only makes a later, separately frozen encoder-feasibility objective
  eligible for consideration.
- Write one immutable contract and aggregate-only result below
  `D:\thericher-v2\model-artifacts\research\kis-d1-candle-noise-floor-v1`.
  Retain hashes, counts, categorical outcome, seed-count, block/null geometry,
  and rounded aggregate metric categories only. Generated artifacts remain
  outside Git; this CPU objective writes no model checkpoint.

## Boundaries

- Do not call KIS, Norgate, Tiingo, or another network provider; read no
  `.env`, credentials, account, position, or order state.
- Do not submit, modify, cancel, prepare, replay, or simulate any Paper or
  broker order. Do not enable or read any live route.
- Do not use GPU, train an LSTM/TCN/Transformer, reuse the completed causal-TCN
  weights, open a sealed holdout, or start a scheduler. GPU work is deferred
  only for this exact next-step decision, not as a global resource hold.
- Do not add a generic benchmark framework, dashboard, public dependency, or
  data-cleaning/source-promotion path. Keep one typed input preparation, one
  fixed logistic/null evaluation, one runner, and focused tests.

## Required Work

1. Engine Research: implement the typed candle-only input preparation, fixed
   logistic/null runner, aggregate-only immutable evidence, and source-safe
   outcome categories.
2. Research Steward: record this as CPU-only, with no GPU appointment or
   sealed-evaluation spend. Preserve the completed representation artifact as
   a separate non-reusable runtime result.
3. Validation: add focused tests for source hash pinning, chronological split
   and purge exclusion, candle-ratio-only features, train-only normalization,
   block-local null construction, fixed kill test, artifact redaction and
   immutability, and absence of network/KIS/credential/account/order/Paper/
   broker/GPU/live surfaces.
4. Run the real CPU campaign against the retained D: source. Update only the
   relevant stateboards, handoff, decisions, and orchestration with source-safe
   aggregate facts. Record any encoder follow-up only as a conditional next
   research item; do not implement it here.

## Claude Context

Claude returned `uncertain` for directly comparing LSTM, TCN, and Transformer
arms on this source. It identified current-listing survivorship, unqualified
corporate-action handling, reused source-slice selection pressure, and roughly
one-to-two effective cross-sectional units as the material concerns. Codex
accepts its bounded recommendation: first characterize the CPU noise floor
with a simple fixed baseline and block-permuted-label null. The same-candle
ratios deliberately avoid cross-session split jumps, but do not promote the
source or resolve its broader limitations. A failed null test ends this family;
a passed test does not rank models or authorize GPU/Paper work.

## Verification

Run focused tests, then:

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example --profile research config --quiet
```

## Completion

Report the frozen source/split/null contract, source-safe CPU result, external
artifact hash/root, tests, commit hash, intentional omissions, and the next
recommended objective. Replace this file with exactly one next objective only
after completion evidence is committed and pushed.
