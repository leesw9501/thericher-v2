# Next Codex Goal

Read `HANDOFF.md`, `VISION.md`, `ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`,
`RUNBOOK.md`, and the active stateboards in `agents/` first. Then continue from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build `forward-capture-and-broad-model-cadence-v1`: make the existing KIS
intraday-head collection deliver the new profiled-MTF forward capture at its
eligible session slots, while Engine starts one independent, source-local,
exploratory broad-D1 model campaign from already retained data.

This is one operating cadence: future KIS-shaped data accumulates without
idling Engine development. The broad-D1 campaign is engineering research only;
it is not a ranking, profitability, Paper-intent, or promotion path.

## Boundaries

- Ask Claude for one concise falsification-first check before changing the
  collection-to-capture lifecycle or freezing the broad-D1 target/split/model
  campaign. A timeout is `review_unavailable`, not an approval hold.
- Reuse the existing KIS intraday-head collector and its measured pacing,
  durable recovery, and cache semantics. It may use only standing-authorized
  `KIS_PAPER_*` market-data access. Do not call account/order endpoints,
  submit/modify/cancel Paper orders, read `KIS_LIVE_*`, or enable live behavior.
- The post-collection capture service must have no network, credentials,
  account, broker, or model/GPU route. It must consume local cache only and
  preserve the capture cycle's exact-slot no-op behavior.
- The broad-D1 campaign may use only an already retained, hash-reattested,
  source-local Norgate current-build panel. Keep current-listing, non-PIT,
  availability, adjustment, and corporate-action limitations explicit. It may
  train/evaluate only a frozen exploratory model contract and may not create a
  rank, order, Paper input, PnL/profitability claim, or promotion decision.
- Store all generated contracts, scalar summaries, and any safe model artifacts
  only under `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`; do not
  store raw market rows, credentials, or generated artifacts in Git.

## Required Work

1. Data: add a small post-collection, network-disabled Docker service and wire
   it into the existing intraday-head schedule only after a successful
   collection. It must invoke the new capture-cycle runner once, surface a
   source-safe categorical status in the existing schedule receipt or a narrow
   compatible extension, and preserve recovery if collection or capture fails.
   Test KST/ET slot behavior, no collection-to-capture call after collection
   failure, no duplicate provider call, source-safe output, and Docker profile
   configuration.
2. Engine Research: inventory the existing broad current-build D1 reader and
   freeze one causal exploratory campaign that has a fixed dataset identity,
   label availability rule, chronological split/purge, naive baselines, feature
   window(s), model family/parameters, cost-free model metrics, strongest
   leakage/null kill test, artifact root, and bounded CPU-first/GPU compute
   rule. Prefer a simple tabular baseline plus one sequence or neural baseline
   only when both consume the identical frozen rows. Do not tune after seeing
   validation results.
3. Run a CPU smoke with the actual retained source. If its frozen contract is
   satisfied and CUDA is available, run one bounded Docker CUDA appointment;
   otherwise record the categorical reason and leave GPU free. Preserve only
   source-safe aggregate outcomes and provenance.
4. Update Data, Engine Research, Research Steward, and orchestration stateboards
   with the two independent results. A collector retry, missing forward pair,
   or unavailable GPU cannot stop the other package.

## Completion Evidence

- the installed intraday-head path has a tested, source-safe collection-to-local
  capture handoff with no account/order/live surface;
- one actual-source exploratory CPU campaign receipt, plus a bounded CUDA
  receipt when eligible, with explicit non-promoting status;
- focused tests, full clean-root parallel verification, Ruff, both Compose
  configurations, commit, push, and this file replaced with one next objective.

## Verification

```powershell
uv run --extra dev pytest -q <changed focused tests>
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example --profile research config --quiet
```
