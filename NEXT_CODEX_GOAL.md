# Next Codex Goal

Read `HANDOFF.md`, `VISION.md`, `ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`,
`RUNBOOK.md`, and the active stateboards in `agents/` first. Then continue from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build `kis-broad-d1-panel-and-causal-candidate-v1`: turn the completed,
source-limited KIS Paper broad-D1 cache into one read-only canonical panel and
freeze one distinct KIS-bar causal candidate preflight from the coverage that
actually exists.

The cache completion is a Data fact, not a profitability claim. A coverage gap
closes only the named candidate as `input_unavailable`; it must not trigger
synthetic training, static-source substitution, a duplicate collector, or a
foreground wait.

## Boundaries

- Ask Claude for one concise falsification-first challenge before freezing the
  new target/split/model campaign. A timeout is `review_unavailable`, not an
  approval hold.
- Reattach the completed KIS Paper `dailyprice` cache read-only. Do not call
  account/position/order endpoints, submit/modify/cancel Paper orders, read
  `KIS_LIVE_*`, or enable live behavior. Do not restart a broad collector whose
  durable cursor is complete unless a distinct Data objective establishes a
  new source scope.
- Preserve the exact KIS current-listing/non-PIT, adjustment, corporate-action,
  availability, and historical-membership limitations. The panel and every
  candidate result remain exploratory only: no ranking, selection, ensemble,
  PnL/profitability claim, Paper input, or promotion.
- Engine may use only completed KIS D1 bars from the reattested panel. State
  feature availability, target timing, temporal split/purge, naive baseline,
  strongest kill test, minimum usable coverage, artifact root, and stop rule
  before opening any target.
- Prefer one simple CPU-first KIS-bar classical baseline. Do not rerun a closed
  Chronos, causal-TCN, HMM, candle-noise, or prior rule family merely to occupy
  GPU. CUDA is eligible only after an actual-source CPU receipt and a separate
  frozen GPU contract.
- Keep raw data under `D:\market_data` and artifacts under
  `D:\thericher-v2\model-artifacts`; never put raw rows, credentials, model
  weights, or generated artifacts in Git or a stateboard.

## Required Work

1. Data: reattach the latest broad-D1 receipt and materialize one canonical
   read-only panel from eligible complete-cache symbols. Record only source-safe
   coverage facts: counts, common-session range/count, source-limited count,
   manifest identity, and limitations. Reject symlinks, malformed rows, mixed
   snapshots, and inconsistent completed-bar timing before any consumer opens
   a panel.
2. Engine Research: independently reattest that panel and freeze one distinct
   causal CPU-first candidate preflight. It must use KIS-reconstructible D1
   inputs only, a fixed chronological split/purge, an always-flat or zero
   baseline, a minimum-signal/coverage kill condition, and an availability or
   target-permutation falsifier. Do not fit if the frozen panel fails its
   preflight.
3. Run the actual-source CPU preflight when eligible. If it completes and a
   separate frozen GPU contract is justified, Research Steward may allocate one
   bounded CUDA appointment; otherwise release GPU and dispatch another ready
   non-conflicting package.
4. Update Data, Engine Research, Research Steward, and orchestration
   stateboards with actual evidence. Refresh this file with exactly one next
   objective before completing the bounded objective.

## Completion Evidence

- one reattested, source-safe KIS broad-D1 panel receipt with no network,
  account, order, or live route;
- one frozen KIS-bar causal candidate preflight and either an actual CPU receipt
  or scoped `input_unavailable` result;
- focused tests, full clean-root parallel verification, Ruff, both Compose
  configurations, commit, and push.

## Verification

```powershell
uv run --extra dev pytest -q <changed focused tests>
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example --profile research config --quiet
```
