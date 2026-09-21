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
See `HANDOFF.md` for the verified bootstrap and subsequent implementation work.

## Current Progress (2026-09-22 KST)

Operator-approved schedule cleanup now leaves six operational recurring tasks.
The two exhausted historical backfills, finite stability/prefix studies and
immediate-cancel quote diagnostic are disabled with state/evidence preserved.
The existing D1 study has only its 2026-09-22 23:20 KST later observation left;
both triggers expire at 2026-09-23 00:00 KST. The reader currently reports
`first_recorded`, not a pair. The pair-forward runner now targets v2; its next
natural run is 2026-09-23 06:55 KST and is not yet runtime-verified. NAS forward
needs scoped recovery of `nas_forward_cache_unavailable/reconcile`, not another
approval or company hold. Actual daily-SPY Paper and account-observer schedules
remain active. This maintenance package does not complete or replace this goal.

The operator resumed implementation without waiting for a Terra switch.
Order-date and never-submitted-state repairs passed integrated verification;
all seven existing Execution images sharing private state have matching source.
One explicit existing-path SPY Paper session on the new image reached
acknowledged-submit/cancelled-clean. A read-only state check confirmed the new
original-attempt timestamp. This is not a date-crossing runtime test or fill/PnL
result; complete lifecycle/accounting remains open. Exact evidence is in
`agents/execution.md`. Data deployed the D1-only image with source parity;
its observation remains independently due.
The fixed FirstRate CPU rule/linear comparison completed 48 development-only
cells. Its separate H30 comparison then completed 8 Ridge/16 LSTM fits and 108
CPU/CUDA cost cells, preserving all 16 final models externally. These are not
robust-edge or Paper-input claims. The completed train-only diagnostic found
real parameter movement but all 16 final train MSEs worse than the train-mean
baseline; eight epochs meant only 16 optimizer updates per fit. The subsequent
four-fit CUDA learnability check demonstrated basic learning and tiny-batch
memorization at 256 updates, not predictive skill. Next Research work is one
new frozen full-cohort H30 DEVELOPMENT comparison (context12, 8 fits at 256
updates, <=180 CUDA seconds), preserving closed r1 and seen-data limitations.
Next main work is a deliberately fillable one-share
Paper cycle with exact fill/position/accounting facts, not another D1 gate or
immediate-cancel repetition. Use existing ownership, locks and virtual routes;
do not change the current canary's semantics silently.

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
   First connect exact order/date/instrument/side-bound quantity observations
   to private accounting, then use an explicit fresh ask/bid-based one-share
   cycle without changing the canary default. Exit only this cycle's confirmed
   inventory. Orderable funds are not settled cash; unknown fees/settlement
   stay unknown. Reuse existing locks/store/routes, not a new report or gate.

### Data: Independent Support

- Reattach the D1 patch's tests, then verify the installed runtime source before
  claiming that scheduled observations use it. Any bounded deployment/recovery
  stays with the existing task owner; do not add a schedule or widen symbols.
- Validate later D1 outcomes with the existing exact reader. Preserve old
  receipts and quarantine. A missing/changed/invalid pair narrows that session
  only; a match remains measurement-only, not finality or model qualification.
  After the final owned opportunity above, close the finite study with whatever
  evidence exists; do not extend its schedule simply to keep observing.
- Confirm v2 forward collection on its next natural run and diagnose the NAS
  cache failure separately. Exhausted historical cursors are not ongoing daily
  refreshers and remain on demand until a useful new scope is established.
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
.\scripts\run_parallel_tests.ps1 -Workers 8 -RequireCleanTempRoot -PytestArgs @('--maxfail=1','--durations=15')
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
