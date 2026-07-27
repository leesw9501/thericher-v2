# Next Codex Goal

## Objective

Freeze one reusable, source-local six-symbol NAS D1 sequence campaign contract
from the newly attested historical panel.

This goal makes the next CPU/GPU model comparison eligible by fixing the causal
feature window, target, chronological split, cost model, naive comparators, and
input identities. It does not train, select, replay, rank, ensemble, promote,
or route a model.

## Start

1. Run `./scripts/start_next_codex_task.ps1` and read `HANDOFF.md`, `AGENTS.md`,
   `DECISIONS.md`, and the active stateboards.
2. Reattest the materialized NAS history manifest and its source cache before
   consuming a bar. The active panel identity is
   `sha256:7e8d6fe54dd5252fc4b9548b70e3bb31aefcd282922a50c1ca7c58a94d57dc8e`.
3. Ask Claude for a short falsification-first drift check only if the work opens
   a sealed holdout, moves a screened candidate into depth training, changes
   source/ranking/Paper authority, or changes a major runtime. Ordinary offline
   contract preparation does not wait on the expired local Claude OAuth session.

## Frozen Contract

- Use only the six source-local NAS streams: `AAPL`, `AMZN`, `GOOGL`, `META`,
  `MSFT`, and `NVDA`. Their current-listing provenance is not a point-in-time
  universe, cross-sectional rank, liquidity claim, or Paper input.
- Use the verified 2,179-session common D1 subset only. Keep the source's
  `MODP=0_unadjusted`, corporate-action, and terminal source-limitation facts.
- For each symbol, use exactly 20 completed daily close-return observations at
  `t-19..t`, with no cross-symbol feature, target, rank, or action.
- Define the later binary target strictly from one-share `t+1` open to `t+2`
  open after the existing 1 bps fee and 2 bps slippage per fill. Target labels
  are development-only and may not be exposed in the validation input.
- Use chronological `1,510 / 22 / 647` common sessions for development / purge /
  validation. A validation sample is eligible only when its full 20-session
  feature window and both later execution bars remain inside validation.
- Fix the later per-symbol comparators as `flat`, `always_long`, and
  `previous_bar_direction`, with two-session non-overlapping decision slots.

## Work

1. **Data:** expose a narrow reattested phase-local adapter over the NAS panel.
   It must reject index/hash drift, source-path changes, incomplete bars, phase
   leakage, and source misalignment before Research receives samples.
2. **Engine Research:** implement immutable campaign/input dataclasses and a
   source-safe external precommit receipt. The receipt may identify source
   hashes, counts, split geometry, feature schema, costs, and comparators; it
   must not retain raw bars, feature values, labels, per-decision values, model
   weights, checkpoints, or replay events.
3. **Validation:** add focused offline tests for exact split geometry,
   phase-local windows, withheld validation labels, per-symbol isolation,
   source-limited propagation, cost/comparator binding, immutable external
   output, and no network/credential/KIS/broker access.
4. **Infra/Research:** do not train or use GPU in this objective. After a
   successful contract, record the exact CPU-smoke and GPU-breadth package that
   becomes eligible; do not dispatch it yet.

## Boundaries

- No KIS call, credential or `.env` read, provider download, paid asset, public
  service, account/quote/order route, or live behavior.
- No model fitting, checkpoint, probability output, local-paper replay, PnL
  result, parameter sweep, ensemble, ranking, or Paper order.
- Do not blend another provider, repair corporate actions, or infer historical
  membership or executable liquidity.
- Keep data under `D:\market_data` and artifacts under
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`; never commit
  either.

## Completion

- The six-symbol D1 sequence campaign contract reattests the panel and exposes
  only phase-local development/validation samples to its named consumer.
- A source-safe external precommit proves the fixed split, target, costs, and
  comparators without raw/model/replay output.
- The Research stateboard names the next eligible CPU smoke and GPU breadth
  package, but no training or broker side effect occurs in this goal.
- Refresh stateboards and replace this file with exactly one next company
  objective before ending.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Freeze NAS D1 sequence campaign contract`
