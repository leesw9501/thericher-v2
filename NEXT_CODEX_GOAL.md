# Next Codex Goal

## Objective

Establish the first non-promoting, KIS-reconstructible D1 opportunity-selection
development campaign from the existing frozen Norgate trial broad panel.

`D:\market_data\us_equities\norgate_trial_broad_development_panel` already
contains a frozen 523-symbol, 483-common-session D1 panel spanning 2024-07-18
through 2026-06-22. It is static development-only evidence. It must not be
treated as a point-in-time universe, a runtime KIS input, paper-trading evidence,
or a promoted model source.

## Start

1. Run `./scripts/start_next_codex_task.ps1` and read `HANDOFF.md`, `AGENTS.md`,
   `ARCHITECTURE.md`, `DECISIONS.md`, `RUNBOOK.md`, and active stateboards.
2. Reattach the frozen Norgate panel, membership/calendar lineage, existing
   derived feature artifact, prior Norgate development receipts, and existing
   KIS daily field contract. Do not print raw rows, symbols, prices, or volumes.
3. Ask Claude for one short falsification-first drift check before freezing the
   campaign or relying on any result. Include the survivorship, adjustment,
   temporal-split, and KIS-runtime-reconstructibility kill tests; do not include
   raw rows, credentials, account identifiers, or sealed labels.

## Authority And Boundaries

- This is offline local Data and Engine Research work. Do not read `.env`, call
  KIS or another provider, use the Norgate SDK/network, call account/order
  endpoints, or enable Paper/live behavior.
- Preserve source separation: no row-level mixing with KIS, Tiingo, Yahoo, or
  the frozen NAS panel. Generated artifacts stay under
  `D:\thericher-v2\model-artifacts`; source bytes stay under `D:\market_data`.
- Only completed D1 OHLCV fields demonstrably available from the existing KIS
  daily contract may enter the feature schema. Keep the unadjusted/corporate-
  action limitation explicit.
- The campaign is development-only: no ranking, model selection, ensemble,
  PnL, Paper order, promotion, or live inference claim follows from it.
- One GPU job may run only after the reattached source and a deterministic CPU
  baseline succeed. Use an existing, unambiguous artifact run identity and do
  not overwrite prior artifacts.

## Work

1. **Data:** reattest the existing Norgate panel and feature artifact without
   materializing raw rows in Git/logs. Record only source-safe hashes, geometry,
   field availability, and limitations.
2. **Engine Research:** freeze one small daily opportunity-selection campaign
   contract using a completed-bar, KIS-reconstructible D1 feature schema, an
   explicit next-session target, temporal split, costs, naive baseline, and
   stop rule. It may use the Norgate panel only as a source-separated
   development input.
3. Run the deterministic CPU baseline. If it is sound and no duplicate run
   exists, run one bounded CUDA breadth job from that same frozen contract;
   retain weights/checkpoints only outside Git.
4. **Validation:** independently check the campaign’s source separation,
   temporal boundaries, artifact placement, and non-promotion scope. A strong
   result requires the Claude verdict before any follow-up, not a new approval
   gate for unrelated work.

## Completion

- A source-safe Data reattestation and campaign contract identify the exact
  frozen D1 input and its KIS-runtime limitations.
- CPU baseline evidence exists; any CUDA evidence is linked to it and stays
  non-promoting.
- No provider/broker/credential call, raw-row Git artifact, source blend,
  Paper order, model promotion, or new approval gate exists.
- Refresh Data, Engine Research, and orchestration stateboards, replace this
  file with exactly one next objective, then continue.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Bind Norgate D1 development campaign`
