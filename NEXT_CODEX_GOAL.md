# Next Codex Goal

## Objective

Complete `kis-paper-iwm-current-head-cache-mechanics-reattachment-v1`: add and
run the smallest offline, source-safe reattachment of the accepted isolated
IWM/AMS current-head cache. It must reuse the existing generic verified private
intraday cache path to prove only cache/index/manifest/raw-file integrity and
aggregate page geometry. This is not a KIS call, historical-reach claim,
finality/availability observation, qualified dataset, model result, Paper
input, order, or live route.

The earlier `kis-intraday-later-terminal-reattachment-v1` remains an existing
task-owned monitor. Do not foreground-wait for it or manually invoke it.

## Standing Authorization And Boundaries

- Do not read credentials or `.env`; call neither KIS nor any other provider.
  Never read or route `KIS_LIVE_*`; never print, log, commit, or send raw rows,
  compressed raw payloads, credentials, account identifiers, broker bodies,
  private intents, or tokens to Claude.
- The offline verifier may read only the existing external IWM current-head
  cache beneath `D:\market_data` internally to reattest its existing index,
  manifest, and raw-file integrity. It may return or persist only categorical
  integrity status and aggregate geometry such as retained chunk/page count,
  total row count, target identity, and collection scope. Do not expose dates,
  timestamps, prices, volumes, filenames, row hashes, or raw contents.
- Keep any new source-safe mechanics receipt beneath
  `D:\thericher-v2\model-artifacts`; keep raw market data only beneath
  `D:\market_data`. Never store raw data or generated artifacts in Git. Do not
  use the legacy IWM replay receipt reader or alter its cache/receipt roots.
- Do not schedule a worker, start Docker, paginate, retry the collector,
  submit/modify/cancel an order, or enable live behavior. The completed one-page
  capture remains immutable evidence and cannot gain predictive, Paper, or GPU
  eligibility from this reattachment.

## Required Work

1. Add the smallest public Data-owned offline inspector using the generic
   verified private-intraday loader plus its source-safe metadata validator for
   exactly `IWM/AMS`. It must fail closed before producing an outcome on any
   index, manifest, raw-file, target, or scope mismatch.
2. Emit or persist a replay-isolated source-safe mechanics result containing
   only integrity category, aggregate geometry, `session_finality:
   not_observed`, `decision_time_availability: not_observed`, and
   `model_input_eligibility: false`.
3. Add focused tests proving the accepted IWM cache reattaches only aggregate
   mechanics and that a tampered compressed raw file fails before a source-safe
   result is produced. Preserve legacy IWM replay-reader compatibility.
4. Refresh Data, orchestration, and `HANDOFF.md` with the narrow result. Run
   goal-boundary verification, commit, push, replace this file with exactly one
   material next company objective, and continue.

## Completion Evidence

- One source-safe offline mechanics result whose verifier internally reattests
  the existing external cache and reports no raw rows.
- A tamper test fails closed before output.
- No provider call, credential read, raw-data exposure, model/PnL claim,
  broker order, or live route occurs.
