# Next Codex Goal

Read `HANDOFF.md`, `VISION.md`, `ARCHITECTURE.md`, `AGENTS.md`,
`DECISIONS.md`, `RUNBOOK.md`, `agents/README.md`, `agents/data.md`,
`agents/engine-research.md`, `agents/research-steward.md`,
`agents/execution.md`, and `agents/orchestration.md` first. Then continue from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build `kis-mtf-profiled-prospective-observer-v1`.

Extend the existing data-only QQQ/SPY prospective-observation path so each
future eligible 15:30 ET pair can prove all six frozen causal
`1m/5m/10m/1h/3h` profile inputs using the completed constituent-reconstruction
boundary. This is a forward-input witness for a later frozen model campaign,
not a model, target, return, strategy, profile selection, PnL, or Paper action.

## Boundaries

- During this objective do not call KIS, Norgate, Tiingo, a provider, or a
  broker. Do not read `.env`, credentials, account data, or `KIS_LIVE_*`.
- Reuse the existing prospective observer and attempt-store concepts where they
  fit. Do not create a parallel scheduler, generic event platform, dashboard,
  report family, or approval gate.
- Read only verified local historical/head cache fixtures or existing local
  cache inputs. Do not refresh, collect, copy, extend, or write market data
  under `D:\market_data`.
- Use only the frozen catalog
  `sha256:ba7d1aeffdadad340d87667c7bfc4b16b1d2ce25632f330b597a0e2437e499e0`.
  Observe every profile; do not select one or create a campaign precommit.
- Exclude the completed 21-session historical cache from every forward count.
  A missing or invalid fresh pair is one scoped categorical observation result,
  never a hold on another lane.
- Persist source-safe evidence only under `D:\thericher-v2\model-artifacts`.
  It may contain opaque hashes, profile identifiers, aggregate counts,
  categorical statuses, and structural cutoff geometry. It must not contain
  bars, prices, OHLCV, symbols, dates, cache paths, feature values, targets,
  labels, predictions, secrets, account data, or order data.
- Do not construct a target, label, return, cost, score, prediction, model
  weight, GPU job, local-paper event, broker intent, PnL, or live path.

## Required Work

### Data package

1. Reattest the existing verified historical/head source identities through the
   current local loader and bind the new observer contract to the completed
   `kis-mtf-profiled-feature-input-preflight-v1` summary
   `sha256:ad00069df6c3da2874eca7070c08c07126b56699db0c4cec91a2f30718a8168e`.
2. For one eligible forward session, build all six profile pair projections by
   reusing the existing exact 60/180-minute slow-bar containment guard. The
   historical 21 sessions may prove compatibility but must never count as
   forward observations.
3. Persist one immutable, idempotent source-safe observation commitment per
   session, with per-profile aggregate readiness and opaque content identities.
   Reconciliation of an identical retry must not duplicate a record.

### Engine Research package

1. Reuse the small target-free normalized projection rather than introducing a
   new feature schema. Bind each observed profile to the catalog hash, source
   contract, cutoff, feature timestamp, and completed-bar status in memory.
2. Make a pair `observed` only when both legs share the same source-contract
   identity, cutoff, profile set, and feature timestamp. Otherwise emit the
   narrow categorical no-result for that prospective session.
3. Keep the observer's contract distinct from a future model campaign: no
   profile winner, target, score, fit, comparison, model artifact, GPU request,
   or execution consequence is allowed.

### Validation package

1. Add focused fixture tests for all six profiles, forward-only historical
   exclusion, duplicate-retry idempotence, conflicting-session rejection, and
   external artifact-root/symlink enforcement.
2. Prove post-cutoff and next-target-shaped minutes leave the sealed profile
   commitments unchanged; a pre-cutoff slow constituent mutation must fail
   reconstruction or change the resulting opaque commitment after legitimate
   resampling.
3. Prove no network, provider, environment, credential, cache-mutation,
   model, GPU, local-paper, broker, account, order, or live path is imported or
   called by the new observer run.

## Claude Challenge

Before an observer-contract or store-format change, ask Claude for a concise
falsification-first drift check. The decisive concerns are accidental reuse of
the completed historical 21 sessions as forward evidence, profile-selection
leakage, and any persisted value/date/symbol data. An adverse verdict pauses
only that contract/store decision; independent work continues.

## Verification

Run focused Data, Engine, and Validation tests plus a local fixture-only smoke,
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
