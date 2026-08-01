# Next Codex Goal

## Objective

Build one bounded, source-separated Tiingo EOD daily research input and CPU
baseline for SPY, QQQ, and IWM.

This is the first small daily model-validation loop that uses the already
approved free Tiingo token without mixing the source into KIS Paper runtime
inputs. It must produce useful causal data and a reproducible baseline before
any GPU appointment is considered.

## Start

1. Run `./scripts/start_next_codex_task.ps1` and read `HANDOFF.md`, `AGENTS.md`,
   `ARCHITECTURE.md`, `DECISIONS.md`, `RUNBOOK.md`, and active stateboards.
2. This goal explicitly authorizes reading only `TIINGO_API_TOKEN` from the
   local `.env` for the Tiingo general EOD endpoints for `SPY`, `QQQ`, and
   `IWM`. Never print, log, artifact, commit, or send that token to Claude.
3. Ask Claude for a short falsification-first review before freezing the daily
   target, split, adjustment, or timestamp contract. A failed review is
   `review_unavailable`, not a hold on unrelated work.

## Work

1. **Data:** add a bounded Tiingo EOD collector that uses one reusable client,
   stores raw provider rows only under `D:\market_data`, and writes a
   source-safe external manifest/receipt under
   `D:\thericher-v2\model-artifacts`. Use only no-cost API access, preserve the
   20% storage warning and 15% floor, and never write raw rows, tokens, or
   request URLs to Git or stateboards.
2. **Data:** collect the available daily OHLCV history for exactly SPY, QQQ,
   and IWM, record only aggregate coverage, field names, source/version facts,
   hashes, and categorical errors, and keep the three symbols source-separated
   from KIS and Norgate. Do not use a static-universe fallback or purchase data.
3. **Engine Research:** freeze a small CPU-only campaign contract before any
   outcome is read: completed D1 raw-OHLCV features only, a chronological split
   with a lookback-plus-horizon purge, explicit next-session direction target,
   fixed transaction-cost band, always-flat and simple momentum baselines, one
   structural leakage kill test, and a finite daily lookback matrix. Reject or
   segment discontinuities rather than silently treating adjustment behavior as
   KIS-compatible.
4. **Engine Research:** run one deterministic CPU baseline only if the frozen
   Tiingo input is complete enough for its own stated split. Store source-safe
   precommit and aggregate result artifacts outside Git. The result may be
   `input_unavailable`, `no_structure`, or descriptive baseline evidence; it
   must not select a winning model, create an ensemble, make a profitability
   claim, submit a Paper order, or start a GPU job automatically.
5. **Research Steward:** if and only if the CPU contract and result satisfy the
   predeclared GPU eligibility rule, record one bounded candidate appointment
   for a later goal. Do not train merely because the GPU is idle.
6. Add focused tests for token redaction, no KIS/broker/live path, raw-data
   external storage, deterministic source-safe manifest behavior, causal
   split/purge, discontinuity rejection, and CPU-baseline no-promotion output.
7. Record the dataset limitation and one exact recovery fact in the Data and
   Engine Research stateboards. Do not add a report family, approval gate,
   durable worker, or dashboard.

## Completion

- The Tiingo EOD scope is reproducibly collected or categorically unavailable
  without exposing credentials or storing raw data in Git.
- One frozen CPU baseline is complete or truthfully `input_unavailable`.
- KIS Paper, live routes, Norgate inputs, and model/GPU artifacts remain
  separate from this source-local daily research loop.
- Refresh this file with exactly one next objective, verify, commit, push, and
  continue. Data-worker waits remain lane-local.

## Verification

```powershell
uv run --extra dev pytest -q <changed paths>
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Add causal sequence window contract`
