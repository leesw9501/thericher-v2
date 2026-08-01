# Next Codex Goal

## Objective

Connect the fixed prospective SPY intraday baseline to one source-safe
observation receipt and the existing broker-free `local_paper` replay path.
This is an engineering and replayability target, not a historical backtest,
profitability result, KIS Paper order, or live-trading action.

## Start

1. Run `./scripts/start_next_codex_task.ps1`, then read `HANDOFF.md`,
   `AGENTS.md`, `ARCHITECTURE.md`, `DECISIONS.md`, `RUNBOOK.md`, and the active
   Data, Engine Research, Research Steward, Execution, and orchestration
   stateboards.
2. Ask Claude for a concise falsification-first drift check before changing a
   receipt/replay contract or execution boundary. Never include credentials,
   raw prices, account facts, fills, or labels.

## Boundaries

- `KIS_PAPER_*` market-data reads are authorized only if Data needs to attach a
  newly completed SPY session. Do not read `KIS_LIVE_*`, submit a KIS order, or
  query account state in this objective.
- Retain raw market data only under `D:\market_data`. Keep source-safe receipts
  and generated artifacts only under `D:\thericher-v2\model-artifacts` or
  `/app/model_artifacts`; never store them in Git.
- Use only the existing local simulator for any replay. Every simulated fill
  must remain `source: local_paper` and must not be relabeled as KIS Paper.
- The fixed baseline may not be trained, tuned, selected, ensembled, or used to
  claim PnL or profitability. Do not allocate GPU work from this objective.
- A missing fresh session is local to capture. It must not make Codex wait or
  block another ready package.

## Work

1. **Data:** define a source-safe observation receipt from a verified
   `ProspectiveSpyIntradaySessionRecord`. It may contain only identities,
   structural timestamps, completeness/status, and categorical decision facts;
   reject raw OHLCV values, provider credentials, file paths, account data, and
   mutable duplicate identifiers. Prepare the Data-owned fresh-session adapter
   without waiting for a market session.
2. **Engine Research:** evaluate the frozen SPY baseline exactly once per
   immutable record and bind its target proposal to the receipt. Preserve its
   fixed 30/6/3/2/2 structure, 2 percent target, abstain path, TTL, cost
   metadata, and always-flat comparator. Do not change its rule after observing
   an outcome.
3. **Execution:** use the existing target-proposal-to-local-paper replay seam
   with injected completed bars. Prove an eligible `enter` has a deterministic,
   replayable local-paper lifecycle and an abstain creates no intent/fill. Do
   not invoke the KIS Paper route or create a durable broker intent.
4. **Validation:** add focused tests for idempotent receipt identity, raw-value
   exclusion, no provider/network/credential/broker access in unit tests,
   duplicate-record rejection, and local-paper fill provenance. A fresh KIS
   session capture may remain `not_yet_observed` after its adapter is prepared.

## Completion

- The baseline-to-receipt-to-local-paper contract is deterministic and tested.
- Raw data remains external and every receipt is source-safe.
- No KIS order, account read, live route, model training, GPU artifact, or PnL
  claim occurs.
- Refresh this file with exactly one next objective, verify, commit, push, and
  continue without foreground waiting for market time.

## Verification

```powershell
uv run --extra dev pytest -q <changed paths>
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
docker compose --profile research config --quiet
```

## Suggested Commit Message

`Connect prospective baseline to local paper`
