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

## Current Progress (2026-09-23 KST)

Latest same-cycle recovery: the owned SELL was acknowledged but stayed unfilled.
One exact-ID cancellation was accepted; subsequent original-date reads show
remaining zero and one distinct matching cancellation lineage with full
quantity/zero fill/zero amount/no rejection. The cycle still owns one SPY.
The prior generic recovery leaves this history-present cancellation unknown.
The narrow parser/recovery repair and post-entry categorical diagnostics are
implemented with704 focused passing tests. Final authority passes5,097/19
skips in326.74s; seven deployed consumers match28 changed-source hashes.
Runtime reattachment is not complete:14:40Z auth_rejected, then14:44Z SELL
reconciliation unavailable despite later account/history reads succeeding.
Durable SELL remains outcome_unknown, not cancelled. Exact safe receipts are
in Execution. No replacement or new entry was submitted.

Next bounded Execution work after cancellation reattachment: implement a
durable linked exit continuation for the SAME buy inventory. Preserve the
cancelled leg and its raw identity, persist any successor intent before POST,
and reconcile all owned fills/position before pricing the residual exit.
Do not change the old intent, reset the cycle, adopt inventory into the budget
strategy, or treat cancel acknowledgement alone as terminal. Reconcile exact
terminal cancellation first; a fresh priced successor is distinct from retrying
an unknown POST. This is ordinary authorized Paper recovery, not an approval
wait or another market-observation gate. The company objective remains open.

2026-09-23 evening: exact owned cycle spy-fill-20260922-v1 now has a confirmed
full buy fill, persisted original-date/intent binding, matching fresh SPY
position and no SPY open order. Read-only recovery at 10:52:53Z used no order
route. Execution records the exact external receipt. The observed blocker was
a NASD balance response containing another valid US venue, not unavailable
credentials. The parser now preserves row venues and merges only matching
inventory across completed queries; all three queries/pagination and conflict
checks remain. All seven consumers are rebuilt; 507 focused tests pass.
The prior auth/transport failures are preserved as separate observations.

Independent Data continuation: QQQ/SPY v2 now reattests41 common D1 sessions
through September22, not M1 history. Finite D1 observation closed as
disqualified/identity_mismatch without extension. NAS target-local overlap
handling is implemented and deployed, but an actual6-page attempt found all6
targets conflict. The subsequent revision-retaining recovery at13:21:08Z
accepted six pages, preserved six whole-page revisions and appended234 rows:
all six targets now have41 common daily sessions. Original overlap values remain
unchanged. An exact recorded-at/hash reader exposes one whole vintage, while
the mixed first-retained view remains explicitly non-PIT and unresolved for
its old predictive consumer. Continue the existing daily owner, not strict-merge
retry loops, reset history or an invented automatic-finality rule.
No account/order call or Paper schedule change belongs to that Data package.

The SAME fixed-cycle task ran at22:35 and returned recovery_required /
evidence_unavailable after one visit. Exact offline parsing confirms a fresh
full buy-fill observation at13:35:02.799196Z, but no sell state. Its finite
trigger has no next run; do not infer completion from its exit0. Next localize
the failure after entry reconciliation through the existing client path, then
recover this same cycle. Fees, settled cash, net PnL and lifecycle closure
remain unknown. The23:50 10-percent strategy schedule is unchanged; it cannot
take over unresolved SPY inventory. No replacement buy or funding reset.

Parallel research completed model-family-h30-c36-v1:4 LightGBM and16
TCN/Transformer fits,144 cells and84 reproduced parent controls; all20 models
are external and the GPU lock is released. None is positive across both folds
at3/5bps. No model selection or Paper dependency. The next ready research
package compared persistent target positions with repeated H30 roundtrips.
That comparison is now complete: 72 pairs / 72 parent controls, CPU 317.730s,
equal gross exposure and exact eliminated-fee differences. Retained LSTMs have
four isolated trades and no merging benefit; the active rules remain negative
in aggregate at 3/5bps. No training, GPU, winner or Paper replacement. Subsequent
parallel research completed fixed-forecast diagnostics on all28 retained
models in84.497 CPU seconds, reproducing84 parent model/cost cells. Of28 cells,
21 have worse MSE than TRAIN mean; no same-symbol/family/seed improves it in
both folds. Sparse >6bps decisions are consistent with narrow predictions,
not sufficient reason to lower a threshold on these seen outcomes. Next
opening-range CPU package is now complete:12 cells,159 one-share roundtrips,
259.329s. First-fold positive/second-fold negative at3bps for both symbols;
descriptive_criterion_not_met. No statistical rejection or Paper replacement.
Exact immutable contract/results are in Research; do not retune this closed run.
Latest isolated-package verification:127 NAS tests and109 research/runner tests;
Ruff and both sample-env Compose configurations pass. No full-suite rerun.
Preceding shared-Execution verification: 587 focused cases; 4,545 full passed /
19 skips in 317.15s, eight workers, clean helper exit. The actual sell/flat
lifecycle remains open.

Earlier package verification:
Final integration: 718 changed-path serial tests; 4,405 full passed / 19 skips,
eight workers, 339.16s, clean helper exit. This package is verified, but the
company objective is not complete until its actual lifecycle is reconciled.

Operator priority update: implement an approximately 10-percent aggregate
virtual-cash strategy trial under the sizing instruction in `AGENTS.md`.
This is already approved; no further capital/profitability/D1 gate applies.
The new opt-in daily-session mode now implements that budget, with an immutable
initial funding basis, entry-cost/reservation replay from existing intents,
owned inventory and recovery before new input checks. It consumes the existing
baseline's direction only; its 10-percent allocation is a distinct execution
policy, not the old fixed-lot result. Final integration passed 439 / 1 skip;
full eight-worker authority passed 3,903 / 19 skips in 296.58s, with managed
cleanup. Ruff and both Compose configurations pass. Seven images contain the
six changed modules (42 matching hashes); the actual Docker mount check and
credential-free launcher preview passed. The existing daily task now uses
the budget launcher, 24 bounded visits and a 25-minute limit, without changing
its principal or 23:50 KST weekday trigger. First due: 2026-09-22 23:50 KST.
No task was started manually and no broker call was made in this package.
See Execution/RUNBOOK for recovery and exact runtime scope. Do not enlarge the
separate diagnostic cycle or claim budget orders/fills from source tests.
Keep this lifecycle objective open until its runtime evidence exists.

The explicit fresh-ask/bid SPY cycle is implemented in the existing session
CLI, with a scoped host launcher, account-bound private identity, shared
new-intent ownership, same-leg restart recovery and bounded asynchronous fill
observation. A real quote-only structure check confirmed bid/ask in output2;
the parser and fixtures now match. No order/account call was made by that
check. Focused integration passed 346 tests / 1 skip. Actual fill/flat/gross
accounting evidence is still required; this does not complete the goal.
Final integration passed 3,707 tests / 19 skips with eight workers in 289.48s;
the managed helper cleaned its run and exited zero. Ruff and both Compose
configurations pass.
The next owned runtime action uses one fixed cycle ID, not another immediate-
cancel canary. See RUNBOOK and Execution for deployment and finite dispatch.
All seven state consumers are deployed with source parity. The existing
quote-task registration owns one 2026-09-22 22:35 KST fill invocation, expiring
23:10, with fixed cycle ID `spy-fill-20260922-v1`. No new recurring task exists.
Reattach its categorical worker result and exact private-leg/account evidence;
an incomplete outcome resumes the same cycle, not a new ID or a claimed fill.

Exact cumulative fill accounting is now connected to the existing canary and
restart reconciliation, using the same original-date history GET and atomic
private state. Unique order/date/instrument/side/currency/quantity binding,
quantity/price/amount consistency, duplicate no-accrual, monotonic conflict
handling and pre-cancel persistence have focused coverage. Missing/failed
observations preserve historical totals but do not present them as current.
This is source/integration work, not a real fill or settled-cash/PnL result.
Seven Execution and two NAS images were rebuilt; 34 baked-source checks match.
That foundation is now consumed by the explicit one-share cycle above;
existing canary pricing remains unchanged outside that named mode.

Earlier schedule-cleanup evidence (superseded by current results above):
operator-approved cleanup left six operational recurring tasks.
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
memorization at 256 updates, not predictive skill. The separate frozen full-
cohort H30 DEVELOPMENT comparison completed 8 fits/2,048 updates in 27.336
supervised CUDA seconds, plus four Ridge fits and 72 replay-parity cells.
All eight final models are retained externally. TRAIN loss improved, but every
3/5-bps LSTM cell is negative. Do not extend this closed trial or equate the
1-bps positives with skill; the next research question should address costs
and turnover against matched controls rather than repeat tiny-batch learning.
The linked fixed nominal 6-bps hurdle comparison completed all eight retained
models and 84 development cells on CPU, reproducing 60 old sign/control cells.
Trading fell substantially; one symbol/seed aggregation is positive at 3/5 bps
but the gain is not uniform by fold. No model was selected or promoted.
Next main work is the actual runtime result of the fillable cycle, followed
by exact fill/position/accounting comparison. Use existing ownership, locks
and virtual routes; do not silently change the old canary's semantics.

## Role-Owned Work

### Execution: Main Path

Implemented package: connect the existing baseline decision to aggregate
budget-based integer sizing, durable same-account reservations and exact owned
inventory. Reuse the existing intent/fill store and writer locks; no new broker
backend, recurring diagnostic or approval workflow. Preserve the legacy fixed
one-share diagnostic. Prove restart/overlapping attempts cannot double-reserve
or double-submit, a sell cannot consume unowned holdings, and multiple entries
cannot repeatedly claim 10 percent. Deploy through the existing strategy owner
with fresh buying-power/quote facts, and report orders, fills and attributable
results separately. Recover existing owned intents before daily input/target
checks can skip them. No research profitability claim is required. The current
default Python entry remains one-share unless `--budget-trial` is selected;
the existing daily task is the deployment owner. Next reattach that owner's
actual budget decision/order/fill/accounting result without resetting its
funding binding or inventing another manual-approval or profitability gate.

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
- Finite D1 is closed with a validated later identity mismatch; preserve its
  immutable receipts and expired triggers. It is not a company prerequisite.
- V2 forward collection is confirmed at41 sessions. NAS revision retention also
  advanced all six targets to41 sessions, with old values and whole new vintages
  preserved. Continue collection through its existing owner. A future consumer
  must explicitly bind one snapshot and its recorded-at limitation, not treat
  the mixed first-retained view as historical PIT data. Exhausted historical cursors
  are not daily refreshers and remain on demand until useful scope is assigned.
- Reattach only the existing lawful ETF snapshots needed for the Engine
  package, exposing event, timestamp, gap, and already-seen-data limitations.

### Engine Research: Parallel Preparation

- Operator priority: broaden model families beyond LSTM configurations.
  The linked LightGBM/TCN/compact-attention comparison and fixed-weight
  persistent-position and fixed-forecast comparisons are complete above.
  The fixed opening-range-breakout DEVELOPMENT study also completed with
  exact next-open/exit timing and matched long/cash controls. Its descriptive
  criterion was not met; do not retune the closed matrices or change tonight's
  baseline Paper strategy. A later research package needs a separate declared
  mechanism or replication, preserving seen-data and source-clock limitations.
  TimesFM 2.5 is selected as the public-model runtime; 3.0's separate
  noncommercial/nonproduction restrictions are not waived by personal use.
  The pinned 2.5 synthetic CPU/CUDA check is runtime evidence only, not a
  predictive benchmark. Source/pretraining scope affects only that public
  model's claims, not the ready locally trained comparison. See DECISIONS.
- `regular-session-cost-matrix-v2` completed on 2026-09-22 without changing
  tonight's Paper paths. Full regular-session TRAIN windows grew support to
  2,232-6,732 rows per fit; contexts12/36 and horizons30/60/120 share fixed costs.
  CPU completed 24 Ridge fits/216 cells; CUDA completed 48 eight-epoch LSTMs/
  144 cells and 13,248 updates. All 48 models are retained externally. Results
  are cost-sensitive and often inactive; no robust winner or Paper input.
  Detailed custody, hashes and limitations are in Research. This closed run
  is not a fresh holdout and must not be silently rerun or retuned. The linked
  H30/context36 persistent-position comparison is now complete above; its cost
  identity is not a predictive-skill result.
- A one-shot thread follow-up (`thericher-paper`) is installed for
  2026-09-23 00:20 KST to reattach both existing Paper opportunities. It does
  not start another worker/order or expand the Windows task schedules.
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
