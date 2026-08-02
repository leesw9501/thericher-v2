# Next Codex Goal

Read `HANDOFF.md`, `VISION.md`, `ARCHITECTURE.md`, `AGENTS.md`,
`DECISIONS.md`, `RUNBOOK.md`, `agents/README.md`, `agents/data.md`,
`agents/engine-research.md`, `agents/research-steward.md`,
`agents/execution.md`, and `agents/orchestration.md` first. Then continue from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build `source-and-window-contract-preparation-v1`.

Advance two independent, non-promoting inputs for later model research in
parallel:

1. a read-only reattestation of the existing external Norgate S&P 500 Current
   & Past membership snapshot; and
2. a hash-sealed, target-free causal `1m/5m/10m/1h/3h` window-profile catalog
   that a later frozen campaign can select from exactly once before opening its
   target or evaluation slice.

This is one preparation objective, not a Norgate qualification, predictive
campaign, window search, model selection, or execution change.

## Boundaries

- Do not call a provider, KIS, Norgate, Tiingo, or a broker. Do not read
  `.env`, credentials, account data, or `KIS_LIVE_*`.
- Do not modify, rebuild, refresh, re-pull, or copy the Norgate snapshot. Read
  only the known external snapshot at
  `D:\market_data\us_equities\norgate_membership\canonical\sp500_current_past\snapshot=2026-07-18-norgate-sp500-membership-r1`.
- Do not print or persist raw membership rows, candidate symbols, OHLCV,
  prices, labels, returns, targets, predictions, fitted parameters, or local
  paths in generated receipts. Source-safe derived receipts belong only under
  `D:\thericher-v2\model-artifacts`.
- Preserve every membership manifest ineligibility: no PIT, publication-time,
  historical-universe, delisting, adjustment, corporate-action, model,
  ranking, campaign, sealed-holdout, or Paper eligibility follows from this
  work.
- The MTF catalog may use only deterministic synthetic `Bar` fixtures and the
  existing pure sequence-window contract. It must not read a local cache,
  dataset, target, return, prior result, model artifact, or GPU.
- Do not create a scheduler, queue, generic experiment framework, model,
  ensemble, PnL claim, Paper/local-paper action, or live behavior.
- Keep the D: storage policy intact. Current free space is an observed
  `40.42%`; stop only the package that would cross the documented floor.

## Required Work

### Data package: `norgate-membership-source-reattest-v1`

1. Reuse `verify_norgate_sp500_membership_snapshot()` as the sole snapshot
   reader. Verify the existing snapshot's path containment, file hashes,
   counts, manifest identity, sparse date range, package metadata, immutable
   ineligibility flags, and free-space fact without importing `norgatedata` or
   creating any network, environment, credential, or provider path.
2. Add only the minimal source-safe immutable receipt/runner if the existing
   verifier cannot expose a reattestation record. Its payload may contain
   hashes, aggregate counts, aggregate date bounds, categorical integrity
   status, and scope flags, but never raw rows, symbols, paths, or secrets.
   Capture a pre/post read-only file identity so reattestation cannot silently
   mutate the snapshot.
3. Treat an unavailable, changed, malformed, or out-of-root snapshot as its
   own `input_unavailable` or `integrity_mismatch` result. Do not recollect or
   repair it. The Engine package continues independently.
4. Add focused tests for lazy Norgate import, no network/environment access,
   external artifact-root enforcement, immutable/write-free source handling,
   source-safe redaction, and a manifest that remains ineligible.

### Engine package: `causal-mtf-window-profile-feasibility-v1`

1. Add a small immutable profile catalog built on
   `CausalMultiTimeframeSequenceWindow`. Freeze this ordered profile set before
   any consumer exists:

   - `short`: `15/3/3/2/2`
   - `kis_baseline`: `30/6/3/2/2`
   - `one_hour`: `60/12/6/2/2`
   - `medium`: `90/18/12/2/2`
   - `long`: `120/36/12/2/2`
   - `extended`: `180/36/18/2/2`

   Each tuple is in canonical `1m/5m/10m/1h/3h` order. Do not add, remove,
   reorder, or tune cells after seeing any target, return, label, or prior
   result.
2. Give the catalog a deterministic SHA-256 identity and a source-safe,
   timestamped external pre-registration receipt. A future predictive campaign
   must record exactly one catalog cell and this catalog identity before it
   opens a target, split, cost model, or evaluation output; this objective must
   not create or choose such a campaign.
3. Prove with deterministic synthetic bars that every profile builds only from
   completed, contiguous, single-symbol bars at one cutoff. Fail the entire
   profile on future, incomplete, duplicate, non-contiguous, or stale `1h`/
   `3h` input. Preserve the existing `30/6/3/2/2` compatibility behavior.
4. Add focused tests that the catalog and receipt do not touch network,
   environment, credentials, provider, cache, labels, targets, model weights,
   GPU, local paper, or broker code; that the catalog digest is stable; and
   that a forged or altered profile cannot pass as the frozen catalog.

## Claude Challenge

Claude's compact preflight verdict is `supported-with-limits`. Preserve its
two guards: the catalog must be hash-sealed and timestamped before a consumer,
and later campaigns need one-cell-per-campaign selection custody. The proposal
is invalid if profile geometry came from labels, returns, or prior evaluation,
or if Norgate reattestation can mutate or re-pull the snapshot.

## Verification

Run focused Data and Engine tests plus a local no-provider smoke, then:

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
