# Next Codex Goal

Read `HANDOFF.md`, `VISION.md`, `ARCHITECTURE.md`, `AGENTS.md`,
`DECISIONS.md`, `RUNBOOK.md`, `agents/README.md`, `agents/data.md`,
`agents/engine-research.md`, `agents/research-steward.md`,
`agents/execution.md`, and `agents/orchestration.md` first. Then continue from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build and verify `kis-paper-canary-idless-orphan-recovery-v1`: a narrow KIS
virtual-paper execution recovery repair for the case where a paper order may
have reached KIS but the submit response did not yield a broker order ID.

The outcome is deterministic recovery capability for one exact persisted
virtual-paper intent, not an alpha, Paper profitability, PnL, strategy,
portfolio, sizing, or live milestone. The next regular-session canary remains
one share and virtual-only after this repair; no stale receipt or historical
account snapshot can create an intent.

## Frozen Contract

- Repair only the existing `outcome_unknown` / missing-`broker_order_id`
  lifecycle path in `kis_paper_canary`. Preserve the current persisted intent
  identity and its virtual-host, symbol, exchange, side, quantity, and limit
  semantics. Do not change model decisions, sizing, freshness policy, or the
  normal accepted-response path.
- A recovery attempt reads the current KIS virtual account/open-order snapshot
  at its own call time. It may bind a missing broker ID only when exactly one
  open order matches the persisted exact canary attributes. Zero or multiple
  matches remain `outcome_unknown`; never guess, create a replacement order,
  or inspect a later intent.
- Once one exact match is bound, use the existing virtual-paper cancellation
  route when the persisted intent requires cancellation. Persist the recovered
  order reference before a cancellation side effect, then reconcile the same
  exact intent. A clean terminal cancellation is evidence; an unresolved or
  contradictory response remains local to that intent.
- The repair must preserve KIS virtual-host pinning and reject nonvirtual TR
  IDs. It must never read `KIS_LIVE_*`, route live, place a replacement order,
  widen a symbol/quantity/price match, or turn an unknown outcome into a
  future-session permission hold.
- Claude returned `supported-with-limits` for this repair. Its strongest
  falsifier is a simulated accepted-but-ID-less submission followed by a
  matching resting virtual order: recovery must bind, cancel, and reach a clean
  terminal state in the same exact lifecycle. If that proof fails, retain the
  exact unknown record and do not schedule a new canary submit from it.

## Standing Authorization For This Goal

- `KIS_PAPER_*` may be used only through the existing virtual-paper client for
  current account/open-order reads, the exact persisted-intent recovery, and
  paper cancellation required by that recovery.
- The existing one-share KIS virtual-paper canary may be reinstalled for the
  next regular session only after its recovery tests pass. It may submit only
  when its already-existing fresh same-session receipt and call-time checks are
  eligible.
- Do not use `KIS_LIVE_*`, real capital, live routes, or any paid service.
- Do not print or persist credentials, account identifiers, raw prices, raw
  broker payloads, or full order records in Git, logs, Claude, or artifacts.

## Required Work

1. Execution: trace the exact ID-less `outcome_unknown` state, implement the
   smallest deterministic virtual-paper attribute-match and cancellation
   recovery, and preserve no-replacement/idempotent behavior.
2. Validation: add focused simulated KIS tests proving a unique exact match
   reaches clean cancellation; zero/multiple/contradictory matches stay scoped
   unknown; stale or nonvirtual routes fail before side effects; and no live or
   replacement order path exists.
3. Infra: reattest or reinstall only the existing goal-owned virtual-paper
   schedule after the repair is verified. Do not start it manually while the US
   market is closed or manufacture a fresh receipt.
4. Run focused offline recovery tests. A real KIS Paper account/order call is
   optional only when required by the existing schedule or an exact recovery
   path; record source-safe categorical evidence and leave unrelated Data and
   Engine work running.

## Verification

Run focused tests, then:

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example --profile research config --quiet
```

## Completion

Report the exact recovery behavior, any schedule action, source-safe KIS Paper
facts if invoked, tests, commit hash, intentional omissions, and the next
recommended objective. Replace this file with exactly one next objective only
after completion evidence is committed and pushed.
