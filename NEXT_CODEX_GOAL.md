# Next Codex Goal

## Objective

Complete `kis-paper-iwm-m1-caller-derived-temporal-reach-probe-v1`: build and
run one isolated KIS Paper capability probe for exactly `IWM/AMS/1m`. Use one
in-memory client for one current-head page and at most one continuation page.
The second page is permitted only after a recognized response `tr_cont` header;
it uses a caller-derived in-memory key from the first page's oldest exchange
timestamp and is necessarily `PINC=1` previous-day-inclusive. The probe
resolves only this endpoint's immediate continuation semantics and aggregate
relation to its head page. It is not a historical-data completion,
finality/availability observation, qualified dataset, model result, Paper
input, order, or live route.

The earlier `kis-intraday-later-terminal-reattachment-v1` remains an existing
task-owned monitor. Do not foreground-wait for it or manually invoke it.

## Standing Authorization And Boundaries

- `KIS_PAPER_*` may be read only by the named probe path for this one bounded
  KIS Paper market-data invocation. Never read or route `KIS_LIVE_*`; never
  print, log, commit, or send credentials, account identifiers, raw rows,
  compressed payloads, broker bodies, private intents, or tokens to Claude.
- Preserve the existing shared request gate and one in-memory client. The probe
  may issue one initial current-head request and at most one header-gated,
  caller-derived continuation request. It has no retry, loop, historical
  collector, scheduler, Docker, account, or order path. The default IWM route
  must remain one current-day page for every non-probe caller.
- Do not retain probe raw pages or create a raw cache. Keep only its source-safe
  receipt beneath `D:\thericher-v2\model-artifacts`; never store raw data or
  generated artifacts in Git. Do not mutate the completed IWM current-head or
  legacy IWM replay cache/receipt roots.
- Retain only target identity, token/page request counts, accepted-page count,
  categorical continuation disposition, aggregate page yield/overlap direction,
  elapsed-time bucket, and `model_input_eligibility: false`. Do not expose
  dates, timestamps, prices, volumes, filenames, cursor values, row hashes, or
  raw contents.
- Do not submit/modify/cancel an order or enable live behavior. A positive
  continuation result proves neither usable historical coverage, session
  finality, decision-time availability, cadence, model eligibility, nor a
  Paper consumer.

## Required Work

1. Record the resolved Claude falsification-first drift check, then implement
   the smallest explicit IWM probe intent and client state machine. It must
   enforce a current-head first request, a header-gated second request, exactly
   two total minute attempts, and no standalone/third continuation.
2. Add focused tests proving no provider/credential/order access is needed for
   offline cases, default IWM callers cannot issue a continuation, the second
   request is impossible without the first recognized header and a strictly
   older caller-derived key, and an invalid or non-older continuation cannot
   produce a `reachable` result. Verify the transport rejects every other IWM
   `PINC=1` shape.
3. Run the probe once. If it yields a valid older non-conflicting continuation,
   record only its narrow aggregate reach result. Otherwise record the scoped
   `input_unavailable` or `continuation_not_observed` outcome. Never retry or
   turn either result into a collector schedule.
4. Refresh Data, orchestration, and `HANDOFF.md` with the result. Run
   goal-boundary verification, commit, push, replace this file with exactly one
   material next company objective, and continue.

## Completion Evidence

- One source-safe categorical outcome from at most two minute-page attempts and
  one in-memory client, with no live route, order, raw persistence, or raw
  cache.
- Strongest kill test: no accepted valid continuation page with a directionally
  older, non-conflicting relation to the head page. That closes only this
  endpoint's expansion path and does not block another lane.
- No raw values, credential values, account identifiers, model/PnL claim, or
  predictive/Paper/GPU eligibility claim is retained in Git or stateboards.
