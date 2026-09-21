# Next Codex Goal

## Objective

Complete `kis-paper-spy-restart-safe-lifecycle-v1`: make one existing SPY KIS
Paper baseline cycle recoverable across restart and the order-date boundary,
with exact submission/cancellation/fill facts connected to position, cash, and
accounting. This is execution readiness, not a profitable-model or live claim.
Target a material readiness improvement in the first 1-3 working days; an
unavailable broker observation is not successful completion.

## Reassignment

The operator approved a partial reset on 2026-09-21. The previous
`kis-paper-d1-prospective-observation-pair-result-v1` is superseded while
incomplete, not completed or qualified. D1 pairing remains a Data-owned
measurement. Its receipts, quarantine, reader binding, and owned `next_due`
remain unchanged; its result is not a prerequisite for this company objective.

The bootstrap fixes only the D1 shared-client page budget and safe error
classification, plus these policy conflicts. It does not deploy an image,
invoke a broker/task, fix the Paper state machine, train, or prove a pair result.
See `HANDOFF.md` for the verified bootstrap and remaining implementation work.

## Role-Owned Work

### Execution: Main Path

1. Recheck owned tasks, private-state ownership, and current source-safe status
   before any runtime work. Do not compete with an existing worker or create a
   second scheduler. Use the existing virtual-only routes and durable store.
2. Reproduce and repair date-crossing reconciliation: use persisted submission
   identity/time for history queries, not the date of the recovery invocation.
   Keep unavailable/ambiguous evidence unknown rather than guessing a fill.
3. Reproduce and repair the never-submitted-intent case: an unrelated open
   order is not proof that this intent was submitted. Preserve exposure checks,
   but distinguish an actual unknown side effect from a pre-submit conflict.
4. Verify restart boundaries, duplicate-submit prevention, cancellation,
   partial fills, and exact terminal facts with synthetic offline transports.
   Preserve required order, position, cash, and exposure facts; do not let an
   optional account-reporting field become a global execution prerequisite.
5. Through the existing owned Paper path, observe one bounded SPY lifecycle.
   Bind terminal order/fill evidence to its intent, deduplicate fills, and
   reconcile position/cash accounting. A task exit or `canary_completed` alone
   is not a submission, terminal fill, realized PnL, or completed lifecycle.

### Data: Independent Support

- Reattach the D1 patch's tests, then verify the installed runtime source before
  claiming that scheduled observations use it. Any bounded deployment/recovery
  stays with the existing task owner; do not add a schedule or widen symbols.
- Validate later D1 outcomes with the existing exact reader. Preserve old
  receipts and quarantine. A missing/changed/invalid pair narrows that session
  only; a match remains measurement-only, not finality or model qualification.
- Reattach only the existing lawful ETF snapshots needed for the Engine
  package, exposing event, timestamp, gap, and already-seen-data limitations.

### Engine Research: Parallel Preparation

- Freeze one development-only comparison on existing ETF data: a small rule
  and linear baseline with the same feature timing, target payoff, replay,
  costs, naive comparator, temporal split, and finite window/trial budget.
- Already-seen data may be development data, never a fresh holdout or a way to
  reverse an old frozen result. Preserve family lineage and report exclusions.
- Run CPU feedback first. A ready, independently scoped small LSTM/TCN campaign
  may use the existing exclusive GPU allocation without waiting for D1; do not
  allocate compute to fill utilization. No large ensemble search or new runtime.
- This package does not gate the baseline Paper cycle. Temporary Validation
  is invoked only when there is suitable frozen evidence to evaluate.

## Boundaries And Completion Evidence

- Existing `KIS_PAPER_*` authority covers owned market/account reads and virtual
  submit/modify/cancel/reconciliation. Never read or route `KIS_LIVE_*` or enable
  real-money behavior. No new paid commitment, unclear rights, public exposure,
  or major runtime replacement without the operator.
- Never print credentials, account/order identifiers, raw broker bodies, or
  private intent contents. Market data stays under `D:\market_data`; generated
  artifacts stay under `D:\thericher-v2\model-artifacts`.
- Completion needs the offline recovery tests plus exact runtime evidence of
  the owned Paper lifecycle and position/cash reconciliation. An unresolved
  intent remains open; do not label partial preparation as a completed goal.
- Strongest kill tests: duplicate side effect, wrong intent/date binding,
  unexplained exposure/accounting difference, live-route reachability, or a
  claimed fill without evidence. Contain/reconcile that exact execution path;
  independent Data and Research continue.
- Do not wait in the foreground for a market session. Preserve the owner's
  `next_due`, dispatch the ready parallel package, and keep completion honest.

## Verification And Handoff

Use focused serial tests for each isolated repair. At company-goal integration,
run changed-path serial coverage plus the existing authority sequence:

~~~powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example --profile research config --quiet
git diff --check
~~~

Commit/push verified owned changes and refresh current stateboards. Only when
this objective has completion evidence replace it with one material next
company objective and continue. Suggested later outcomes are a reproducible
same-payoff research comparison and a frozen strategy's prospective Paper PnL
record; neither is an additional active goal.
