# Next Codex Goal

## Objective

Complete `kis-paper-canary-unknown-run-reconciliation-v1`: reconcile exactly
one existing `2026-08-11` KIS Paper canary durable intent through its existing
reconciliation path, or retain its scoped `outcome_unknown` result when exact
evidence is unavailable. This advances Paper-trading recovery and later PnL
attribution custody. It must never create a new order, duplicate a session,
or turn an ambiguous historical outcome into a fill, PnL, alpha, or model
claim.

The IWM/AMS temporal-reach probe is closed: its one accepted head did not carry
a recognized continuation header, so it issued no second request and has no
retry path. The existing QQQ/SPY intraday monitor remains task-owned and is not
a foreground dependency.

## Standing Authorization And Boundaries

- `KIS_PAPER_*` may be read only through the existing named reconciliation
  path for this one exact durable Paper intent. It may perform only the existing
  read-only account, position, and open-order checks required by that path.
  Never read or route `KIS_LIVE_*`; never print, log, commit, or send
  credentials, account identifiers, order identifiers, broker bodies, private
  intent contents, or tokens to Claude.
- Do not submit, modify, cancel, replace, or resubmit any order. Do not create
  a scheduler, invoke an existing scheduled session manually, widen a Docker
  service, or use a current/"latest" artifact selector. A Docker invocation,
  if the existing reconciliation path requires one, is a single bounded
  read-only reconciliation of the exact durable intent only.
- First bind the exact persisted intent, route, and opaque lineage offline. A
  missing, duplicate, mismatched, or unreplayable binding is a valid
  `outcome_unknown` completion, not a reason to guess, retry, or create a new
  Paper action.
- Retain only source-safe lifecycle/reconciliation categories and immutable
  receipt pointers under `D:\thericher-v2\model-artifacts`. Do not store raw
  broker/account responses or generated artifacts in Git. Keep all resulting
  statements `paper_only`; do not claim a fill, PnL, profitability, model
  validity, or live readiness.

## Required Work

1. Ask Claude for a concise falsification-first drift-check of the exact-run
   recovery scope before a broker-facing reconciliation call. Include the
   strongest kill test, route isolation, and the fact that reverses any
   `resolved` interpretation, but no secret, identifier, or raw broker data.
2. Reattest the exact historical durable intent and its lifecycle evidence with
   the existing offline readers. Prove that a failure remains fail-closed and
   does not consume a fresh order path.
3. If the exact durable binding is eligible, execute the existing reconciliation
   exactly once. If it is not eligible, preserve a source-safe
   `outcome_unknown` result without calling a broker. In either branch, do not
   retry or resubmit.
4. Validate the resulting exact lifecycle projection through the existing
   reader, refresh Execution, orchestration, `HANDOFF.md`, and `RUNBOOK.md`,
   run required verification, commit, push, replace this file with exactly one
   material next company objective, and continue.

## Completion Evidence

- One exact durable-intent binding and one reproducible source-safe lifecycle
  result: either reconciled under the existing path or explicitly
  `outcome_unknown` with a categorical reason.
- Strongest kill test: absent, duplicate, route-mismatched, or lineage-mismatched
  evidence remains fail-closed and produces no broker submission/cancel/modify
  request.
- No live route, new Paper intent, raw account/broker data, order identifier,
  model/PnL claim, or predictive/GPU eligibility claim appears in Git or a
  stateboard.
