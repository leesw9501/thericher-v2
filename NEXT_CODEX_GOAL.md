# Next Codex Goal

Read `HANDOFF.md`, `VISION.md`, `ARCHITECTURE.md`, `AGENTS.md`,
`DECISIONS.md`, `RUNBOOK.md`, `agents/README.md`, `agents/data.md`,
`agents/engine-research.md`, `agents/research-steward.md`,
`agents/execution.md`, and `agents/orchestration.md` first. Then continue from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build `kis-mtf-profiled-feature-input-preflight-v1`.

Prove that the six frozen causal `1m/5m/10m/1h/3h` window profiles can form
target-free, completed-bar feature inputs from the already verified local
QQQ/SPY 21-session KIS-shaped cache. This establishes only a real input
boundary for a later frozen model campaign; it is not a model, profile
selection, return study, ranking, PnL claim, Paper action, or source
qualification.

## Boundaries

- Do not call KIS, Norgate, Tiingo, a provider, or a broker. Do not read
  `.env`, credentials, account data, or `KIS_LIVE_*`.
- Read only the existing verified local QQQ/SPY 21-session cache and its named
  availability/lineage contracts. Do not mutate, refresh, copy, extend, or
  write market data under `D:\market_data`.
- Use only the frozen catalog
  `sha256:ba7d1aeffdadad340d87667c7bfc4b16b1d2ce25632f330b597a0e2437e499e0`.
  Iterate all six profiles for structural coverage, but do not select a profile
  or create a `campaign_id` precommit.
- Do not open or construct any target, label, return, cost, score, prediction,
  model weight, GPU job, Paper/local-paper event, broker intent, PnL, or live
  path.
- Generated source-safe evidence belongs only under
  `D:\thericher-v2\model-artifacts`. It may retain hashes, aggregate coverage,
  schema/profile identifiers, categorical statuses, and structural timestamps;
  it must not retain bars, prices, OHLCV, symbols, dates, cache paths, feature
  values, labels, targets, or secrets.
- Keep Norgate membership and every non-PIT/current-listing limitation outside
  this objective. Do not use the Norgate snapshot as a universe, ranking, or
  feature input.
- Do not create a scheduler, generic feature framework, model, ensemble,
  dashboard, report family, or approval gate.

## Required Work

### Data package

1. Reattest the existing local QQQ/SPY intraday availability/lineage contract
   through its verified loader before reading a bar. Read the historical cache
   only; do not invoke a collector or provider client.
2. At the fixed existing regular-session cutoff, materialize the minimal
   read-only `1m/5m/10m/1h/3h` completed-bar inputs for each eligible session
   and each frozen profile. Record only aggregate per-profile/session readiness
   and input identity in an immutable source-safe receipt.
3. Establish constituent containment directly: every selected resampled `1h`
   or `3h` bar must be traceable to exactly 60 or 180 contiguous completed
   minute constituents ending strictly before the feature cutoff, and its full
   OHLCV/volume values must equal a fresh reconstruction from those
   constituents. A bar timestamp or bar-open label alone is insufficient. A
   missing containment or reconstruction proof is `input_unavailable`, not a
   repaired bar or inferred causal claim.

### Engine Research package

1. Add a small typed, deterministic target-free MTF feature-input projection
   on top of `CausalMultiTimeframeSequenceWindow` and the fixed profile catalog.
   Reuse an existing pure feature primitive when one fits; otherwise add only
   the smallest fixed normalized completed-bar projection needed to prove the
   input boundary. Do not introduce a generic feature platform.
2. Bind every projection to its catalog hash, selected window ends, feature
   timestamp, and completed-bar status. The feature timestamp must equal the
   latest actual selected window end under the fixed cutoff. Keep values
   in-memory only; receipts expose structural metadata and hashes only.
3. Require same cutoffs and source identity for both legs when emitting a pair
   fact. A missing or structurally invalid leg yields a categorical no-result
   for that session/profile, while independent ready work continues.

### Validation package

1. Add focused tests for all six profiles, QQQ/SPY pair alignment, catalog
   digest binding, no network/environment/credential/provider/cache-mutation
   path, and source-safe external artifact-root enforcement.
2. Mutate every post-cutoff minute and the next target-shaped minute in a
   fixture: the feature projection and source-safe digest must remain exactly
   unchanged. Mutate a constituent minute inside a selected slow bar and prove
   the containment check rejects it or the feature output changes only when the
   minute is legitimately pre-cutoff.
3. Reject future, incomplete, duplicate, non-contiguous, mismatched-symbol,
   and stale `1h`/`3h` input. Do not test or claim predictive quality.

## Claude Challenge

Claude's preflight verdict is `supported-with-limits`. The decisive guard is
constituent-minute containment for resampled slow bars: this objective becomes
unsupported if a `1h`/`3h` bar stamped before cutoff can include any minute at
or after cutoff, or if its values cannot be reproduced from those exact
constituents. Timestamp equality and ordinary staleness checks alone are not
enough.

## Verification

Run focused Data, Engine, and Validation tests plus a local no-provider smoke,
then:

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example --profile research config --quiet
```

If the clean-root helper is blocked only by known interrupted roots, preserve
that fact and run its fresh-root mode plus the remaining commands.

Commit and push the completion evidence, replace this file with exactly one
next objective, and continue without waiting for a market session.
