# Execution Agent Stateboard

AGENTS.md owns policy and NEXT_CODEX_GOAL.md owns the company objective. This
is the current Execution projection, not a broker-event ledger.

## Ownership

Own deterministic orders, fills, positions, cash, reconciliation, accounting
PnL, risk controls, emergency controls, and later KIS adapters. Treat model
output as untrusted input.

## Current Objective

The current KIS Paper read-only account bridge was reattested on the current
local image at 2026-07-31 00:32 KST. Its virtual-only account, position, and
open-order read wrote source-safe external evidence
`execution/kis-paper-console-bridge/20260730T153229125231Z-complete.json`
with hash `sha256:9dfe4e83a1cd7ed33c81930c34e4c9afd430032a3ceb7942fb6149722f3a99b4`.
It is `complete`, `paper_only`, and `submit_capability: false`; its payload
contains only fixed currency/count category keys, never an account identifier,
raw amount, price, position, order, token, or credential. Focused read-only
coverage passed `51` tests before the invocation. The QQQ canary receipt stayed
unchanged as `no_intent/receipt_not_eligible`, so this bridge is read-health
evidence only and does not substitute for the later session's fresh account or
quote reads. The bridge container root remains read-only with `/tmp` tmpfs; its
existing runtime and external artifact mounts are the only writable paths. No
Paper intent, canary, submit, modify, cancel, or live route occurred. KIS Live
remains unavailable.

The next bounded Execution objective is not a new strategy or route: observe
the already-installed freshness-gated QQQ Paper session through its first new
canary lifecycle outcome. The existing session owns one-share target resolution,
durable intent, submit/cancel/reconciliation behavior, and source-safe terminal
projection. It must use only a current eligible intraday receipt, never the
quarantined historical D1 panel. No manual duplicate task, new quota,
decision-table edit, or live route is introduced.

## Current Facts

- The exact prior KIS Paper `outcome_unknown` run
  `canary-20260729T143501313369Z` completed one read-only reconciliation after
  the recovery entrypoint was hardened to bypass every submit/cancel branch.
  Its original evidence remains hash
  `sha256:2e612d02224e768c1f16aeff6a9874bc06cbf549048964795bac8370fae1858c`;
  the separate immutable reconciliation receipt is
  `sha256:c3ec1489d61e23ee82b2986355fafa17298be53c7fb58fe130c6a02103f83b90`.
  The receipt preserves its prior `outcome_unknown/submit_rate_limited` fact
  and records current `outcome_unknown/reconciliation_unresolved` only. No
  submit, cancel, modify, replacement, or live call occurred. This exact
  generic run is not the QQQ lifecycle objective and cannot block it.
- The 2026-07-31 00:31 KST QQQ task had a fresh eligible-exit input and
  terminal `complete`, but its session
  `sha256:4d4be5eaf55c5ddcc8e7d80b0c4af60e53618817521ee47deed67b1c7cb`
  closed `paper_only` `no_intent/account_unavailable`. It created no canary,
  durable intent, submit, cancel, modify, or live action. The separate
  read-only bridge completed one minute later, but its `submit_capability: false`
  scope cannot recover or substitute for this scheduled session's
  account/quote boundary. Claude's falsification-first verdict is
  `unsupported` for treating this pair as exact-session recovery. The next
  scheduler-owned observation is 02:31 KST; no decision-table change or
  replacement intent follows.
- The 2026-07-30 operating review independently reattested the installed QQQ
  path's receipt-derived identity, pre-account and pre-submit freshness,
  virtual-route isolation, intent-before-side-effect, and
  cancel/reconciliation behavior. Its 64 focused tests passed. The required
  serial `pytest -q` reached the 12-minute authority limit and is recorded as
  unavailable, not as a pass; Ruff and both Compose configurations passed.
  This verification fact does not change scheduler ownership, receipt
  eligibility, or any Paper intent.
- Temporary Validation traced `receipt_not_eligible` to the pre-account
  receipt-class gate. The existing fixed table still has reachable fresh
  `enter` and `exit` rows, and its QQQ flat-entry/position-resolution tests
  exercise the complete canary path. A later fresh sign pair can therefore
  create a new eligible QQQ lifecycle without changing table, sizing,
  freshness, scheduler, or strategy. This is an input-scoped no-intent result,
  not a static route contradiction or an order authority hold.
- The 2026-07-29 00:31 KST scheduled QQQ route produced an exact
  `paper_only` `no_intent/receipt_not_eligible` session. Its baseline `reduce`
  action correctly narrowed to the non-entry `abstain` receipt; no canary or
  broker lifecycle was created. The initial parent terminal remains
  `recovery/prospective_validation_exit_nonzero` because the old offline
  validator compared those two representations as raw strings. The corrected
  network-disabled validator reattached the same retained session as
  `runtime_recomputed` with no credential, account, quote, KIS, order, or
  local-paper mutation path.
- The 19:22Z manually invoked intraday-head route returned terminal `complete`;
  its prospective QQQ session returned `no_intent/runtime_window_stale` and its
  validator was `validated`. Its source window ended at 19:20Z and the session
  observed it at 19:22:46Z, beyond the fixed two-minute limit. The runtime
  check therefore stopped before any account, position, quote, intent, submit,
  modify, cancel, or live call. This is a truthful terminal outcome, not an
  execution hold or order retry condition.
- The later 19:31Z scheduled route returned terminal
  `recovery/collection_exit_nonzero` from a retained-cache conflict. Its
  embedded session and offline validation still completed as
  `no_intent/runtime_window_stale` and `validated`; the active QQQ window ended
  at 15:30Z. It also made no account, position, quote, intent, submit, modify,
  cancel, or live call. This current Data-local recovery state does not alter
  the immutable earlier terminal receipt.
- A network-disabled `runtime-freshness-v2` Compose reattachment independently
  recomputed the 19:48Z receipt against the recovered cache as `stale/no_intent`,
  with no canary present. It emits the source-safe completed-window end,
  observation time, lag category, and two-minute budget in a contract-namespaced
  immutable artifact. It opened no network, account, credential, or broker
  route.
- The runtime route now rechecks a ready input before constructing the Paper
  account client and passes the same freshness deadline into the canary's
  locked submit predicate. A stale/incomplete input therefore cannot reach an
  account/quote path at the first boundary or submit at the final boundary.
  The two-minute limit applies only to this current QQQ runtime/Paper route;
  offline Research campaigns retain their explicit campaign-owned age inputs.
- At 05:45 KST on 2026-07-28, the selection-scoped scheduler installer rebuilt
  the five intraday-head chain images and updated only the existing named task.
  Its task action still points to the local runner, retains four triggers,
  `IgnoreNew`, `StartWhenAvailable`, and the 90-minute limit; its pre/post last
  run remained 04:31 KST and its next due remained 06:20 KST. The deployment
  itself did not start a container, create an account/quote/order call, or alter
  a Paper intent.
- The first natural post-deployment 06:20 KST run produced one new QQQ session
  with `paper_only: true` and `no_intent/runtime_window_stale`. Its verified
  window was over the two-minute budget, so it created no account snapshot,
  quote, prepared decision, canary, order, modification, cancellation, or live
  route. The normal network-disabled validator reattached the exact session as
  `runtime-freshness-v2/runtime_recomputed`; the parent terminal is
  `recovery/collection_exit_nonzero`, not a retry cue for this session.

- local_paper, kis_paper, and kis_live remain separate routes. Local simulated
  fills retain source: local_paper.
- KIS Paper scheduled tasks and the credential-free local operations console
  already exist. Existing categorical results do not prove a selected model,
  external fill, or realized PnL.
- The current KIS Paper price/account route is private and virtual-only. No
  KIS_LIVE_* value is readable or callable.
- The latest `kis-readonly` Compose invocation completed on 2026-07-28 after
  root-filesystem hardening. It wrote fresh source-safe external evidence
  `20260728T115736150112Z-complete.json`, used the virtual read-only path only,
  and created no intent, submit, modify, cancel, or broker reconciliation.
  The live loopback dashboard smoke consumed the complete projection with
  read-only/no-submission provenance. A later TTL expiry correctly changes only
  that runtime view to unavailable.
- Dashboard `/state` now uses the snapshot's canonical allowlisted serializer
  for the nested Paper account projection. This retains `kis_paper`, read-only,
  and no-submission provenance for local consumers without introducing a KIS
  client, credential, account identifier, raw broker body, or order route into
  the web process.
- A missing or ambiguous exact broker outcome constrains replacement of that
  exact intent until reconciliation, never a distinct authorized Paper action
  or an independent lane.
- The target-position binding is now test-backed: it derives only the delta
  local-paper intent, rejects a pre-decision `as_of`, and emits scoped
  no-intent for an already-satisfied or mismatched target. It does not widen a
  KIS route or make a network call.
- The prospective QQQ session preserves its original target proposal in external
  `local_paper` state, including replay recovery and `source: local_paper`. It
  is the only scheduled decision computation and uses verified cache evidence
  only for a current `enter` or `exit` receipt.
- The installed intraday-head task prebuilds its images on task update, then runs
  without a market-time Docker build. Its terminal receipt records the embedded
  prospective computation, session, validator, and optional observer as
  source-safe stage facts. A required technical fault is task recovery, not a
  new broker retry, approval gate, or replacement-intent path.
- QQQ/NASD one-share position resolution is now explicit: a fresh flat account
  permits only a buy, a fresh one-share QQQ/NASD account permits only a sell,
  and an incompatible position or QQQ open order is a target-local no-intent.
  It never reads a live credential or treats an old account view as a target.
- The installed prospective-session container has KIS Paper credentials only.
  Its embedded local replay precedes every virtual route use, while the trailing
  offline validator independently recomputes retained cache/session lineage and
  has no credential, network, local-paper mutation, account, or order surface.
- The first fresh scheduled QQQ cycle on 2026-07-28 KST had a current ready
  90-minute runtime window and a fixed `eligible_exit` receipt. Its virtual
  session read returned `account_unavailable`, emitted `no_intent`, and created
  no canary, order, modification, cancellation, or reconciliation side effect.
  The isolated validator independently reattested the same no-intent and the
  terminal schedule receipt closed `complete` with scheduler exit zero. This is
  an exact account-read availability fact, not a model result, route promotion,
  or a permission hold on a later fresh intent.
- The next naturally due 02:31 KST intraday-head task also closed with source-safe
  terminal receipt `intraday-head-20260727T1731094626565Z`, terminal
  `complete`, and Task Scheduler result zero. It is lane-owned scheduler
  evidence only; it does not alter model evidence, broker-route authority, or
  the source-scoped universe contract.
- The prior virtual-only bridge receipts remain historical evidence only. The
  current fresh console projection does not repair, replay, or supply authority
  for a QQQ receipt, intent, or later Paper order.
- The new Data session-capture receipt uses only the KIS Paper market-data
  route and has no Execution account, position, intent, order, or live effect.
- Temporary Execution and independent Validation both passed the new
  six-symbol daily-history profile: its only permitted external paths are token
  POST and fixed NAS daily-price GET; it receives only the Paper App Key/Secret,
  uses a read-only root with three dedicated mounts, and has no account,
  position, open-order, quote, intent, submit, cancel, modify, reconciliation,
  dashboard, or live route. The first real cycles remain Data-owned facts only.
- The final fixed-target recovery admitted only `MSFT/NAS` and `NVDA/NAS` and
  completed without account, position, open-order, quote, intent, submit,
  cancel, modify, reconciliation, or live activity. It cannot become a broker
  permission, order input, or execution dependency.
- The completed QQQ/SPY daily sequence screen used the existing offline
  `local_paper` replay path only. Its six replay cells did not read a KIS
  credential, call a broker/account endpoint, create an intent, or widen an
  Execution route.
- The completed six-symbol CPU control likewise used broker-free `local_paper`
  replay only. Its twelve fixed replay cells were independently reconstructible
  and flat after replay; no KIS credential, account/order endpoint, intent, or
  Paper action was involved.
- The completed daily catch-up emitted an external source-safe `drained`
  receipt with `client_constructed: false`; it had no account, position, intent,
  order, cancellation, modification, or live effect. Its next offline event
  window remains an input contract only, not an Execution route change.
- The active v2 joint event-window contract fresh-imports without Data or
  Execution modules and its metadata-only script path is equally pure. Its
  artifact is candidate-only with `review_unavailable`; it has no credential,
  account, order, intent, local-paper replay, or live effect.
- Its reattested `expanding-1` fold input is equally offline and non-executable.
  It exposes only catalog lineage, segment bounds, and exact sparse indices
  after the parent hash/rebuild comparison; it cannot be selected from an
  unverified artifact object and has no KIS, Tiingo, account, intent, replay,
  or live path.
- The first fold-local D1 materializer only exposes transient feature rows and
  future open references after verified reattestation. Its source-safe receipt
  is `sha256:247142...6b2f748`; it has no label value, intent, account, order,
  local-paper replay, KIS, or live effect.
- Its v2 target/cost adapter uses only transient QQQ `t+1/t+2` opens with fixed
  local-paper-style two-fill economics. Its receipt is `sha256:90be...d7486`;
  it persists no label, price, PnL, intent, account, order, replay, KIS, or
  live effect. A later candidate-only model screen remains equally outside the
  Execution route.
- The completed `expanding-1` candidate-only CPU/CUDA screen imported neither
  Execution nor `local_paper`, created no replay, intent, fill, position, cash,
  or PnL object, and wrote only external aggregate classification evidence.
- The completed `expanding-2` candidate-only CPU/CUDA screen remained outside
  every Execution route. Its source-safe aggregate artifacts have no account,
  order, intent, replay, KIS, Tiingo, or live effect. The next independent
  fold contract must retain that boundary.
- The completed `expanding-3` CPU/CUDA screen remains outside every Execution
  route. Its fold/materializer/target receipts and aggregate artifacts have no
  account, order, intent, replay, KIS, Tiingo, or live effect.
- The completed fixed cross-fold verifier also remained offline and
  non-executable. Its result identity is `sha256:1bbbc7...18bc5d`; it made no
  account, order, intent, replay, KIS, Tiingo, or live call. A fixed-pair
  falsification does not alter standing KIS Paper authority or create a broker
  input.

## Ready Queue

1. Keep the existing virtual-only read-only bridge available for a later
   bounded refresh. A stale runtime view is evidence only and never a broker
   permission, order input, or Data collector dependency.
2. Keep the completed decision-to-target-weight-to-local-paper-intent contract
   separate from this read-only run and every failed model result, replay,
   account, intent, and broker route.
3. Preserve the reconciled exact ambiguous Paper run without replacing it. Its
   primary and recovery receipts remain immutable, and its unresolved result
   neither retries that intent nor blocks another correctly scoped authorized
   Paper action.
4. At a later fresh QQQ runtime receipt, let the existing receipt canary own
   only its new exact persisted intent and cancellation/reconciliation lifecycle.
   Reattach the matching terminal dispatch receipt before interpreting that
   scheduled session as complete.
5. After the exact canary lifecycle has durable evidence, prepare a recurring
   low-frequency fixed Paper baseline using the existing intent, route, risk,
   and reconciliation boundaries. It must collect execution evidence, not
   promote a model or infer profitability from one outcome.

## Durable Constraints

- Persist intent before a KIS Paper side effect and reconcile an unknown
  outcome before replacing that exact intent.
- Never route a request to live or read KIS_LIVE_*.
- Keep credentials, account identifiers, private intents, broker payloads, and
  raw prices out of Git, logs, and public surfaces.

## Recovery

Current class: `recovery` only for the exact 2026-07-28 06:20 KST parent
collection worker; its matched QQQ `no_intent` session and v2 validator are
complete for their own stale-input scope. The exact prior generic canary
reconciliation is also complete as a read-only observation, but its durable
intent remains `outcome_unknown`; it never receives a replacement submit.
The fresh read-only account bridge, cross-fold verifier, account diagnostic,
recovered QQQ/SPY head cache, and first contract-v2 QQQ terminal reattachment
remain complete. The account runtime expires normally after its TTL; a later
refresh is a new read-only observation, not recovery of an order.
Continue independent Data, Research, and authorized Paper work. The new QQQ
route has a complete offline and unit-tested recovery path;
`account_unavailable` constrains only the completed receipt that recorded it.

The retained-cache conflict remains historical evidence owned by the head cache.
The rebuilt image has restored a scoped head input while retaining exact
fail-closed quarantine behavior for a legacy unscoped page. Keep the virtual
route attached only to a fresh eligible receipt; do not read an account or
construct a replacement intent merely because a collection retry is scheduled.

The 00:31 KST parent recovery is also closed for its exact validator-contract
fault: the immutable parent receipt remains unchanged, while the matching
retained no-intent session now has successful independent offline validation.
It does not authorize a replacement intent or alter a later scheduled session.

## Next Handoff

Return any future Data/Research integration request with the existing target
binding and route boundaries intact. The completed cross-fold verifier never
acquired an account, order, KIS, Tiingo, or replay path; preserve that boundary.
The verified contract is deployed to the existing lane-owned schedule; observe
its future regular-session result without forcing an intent. The bounded QQQ
canary objective remains open until a later fresh QQQ receipt owns its new
exact durable Paper intent and terminal lifecycle evidence. It must re-read the
current Paper account and fresh quote at its own call site; no stale account
snapshot or historical Data receipt may act as permission or order input.
The later recurring baseline must use the same call-time technical checks and
never reuse a stale account projection or an unknown exact intent.
