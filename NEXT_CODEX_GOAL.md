# Next Codex Goal

Read `HANDOFF.md`, `VISION.md`, `ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`,
`RUNBOOK.md`, and the active stateboards in `agents/` first. Then continue from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build `profiled-mtf-forward-ragged-sequence-cpu-campaign-v1`: the first fixed,
CPU-only sequence-family counterpart to the profiled-MTF classical controls.

It must consume the same reattested D:-only forward supervised dataset when it
exists and exercise three independent native-ragged sequence families:
per-timeframe recurrent, causal TCN, and masked cross-timeframe attention.
Implementation and full-session fixture evidence proceed now; the actual
zero-pair source remains scoped input unavailable.

## Boundaries

- Ask Claude for one concise falsification-first check before freezing model
  family structure, temporal/masking semantics, and evaluation interpretation.
- Reattest the forward dataset receipt, Data catalog, first-30 pair identities,
  target/split contract, and D:-only materialization before any target is used.
  Missing/stale/zero input returns scoped unavailable and creates no model or
  GPU artifact.
- Preserve native ragged `short` sequences of lengths `15/3/3/2/2` with the
  existing two causal per-bar features. Do not flatten them, timestamp-align
  distinct timeframe rows, use post-15:30 input bars, or use a 15:45 outcome
  bar as a feature.
- Freeze one small deterministic CPU configuration per family, one seed, one
  bounded epoch count, MSE interpretation, no-trade baseline linkage, pair
  purge exclusion, pair-block target permutation kill test, and a hard stop.
  Do not tune after validation, claim PnL/profitability, select a winner,
  create a Paper intent, or allocate GPU in this objective.
- Do not call KIS, read `.env` or credentials, use broker/account/order/Paper
  routes, enable live behavior, expose a service, download data, or create a
  generic deep-learning platform. Keep model state in memory; no checkpoints
  or generated weights may enter Git or model artifacts.

## Required Work

1. Engine Research: construct a D-only reader-to-ragged-input bridge that
   reuses the canonical causal window and masks. Prove its inputs are derived
   only from completed 15:30 prefixes and reject geometry/split/source drift.
2. Engine Research: freeze the fixed recurrent, causal-TCN, and masked-attention
   CPU campaign contract before opening validation targets. Run exactly one
   fixture-only deterministic pass and its pair-block permutation counterpart.
3. Add focused tests for no cross-timeframe row alignment, mask semantics,
   no feature/target leakage, pair-level purge exclusion, deterministic replay,
   artifact isolation, and no credential/network/execution/GPU route.
4. Reattach the real source once. Record a truthful zero-or-ready source-safe
   receipt, update Data, Engine Research, Research Steward, and orchestration
   stateboards, and leave GPU unappointed.

## Completion Evidence

- a tested D:-only ragged sequence input bridge and fixed CPU family contract;
- deterministic fixture-only recurrent/TCN/attention execution with no
  selection or promotion;
- a real local zero-or-ready receipt with no false training claim;
- no raw/feature/target/model values in Git or model artifacts; commit, push,
  and replace this file with the next single objective.

## Verification

```powershell
uv run --extra dev pytest -q <changed focused tests>
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example --profile research config --quiet
```
