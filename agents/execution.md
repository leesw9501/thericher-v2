# Execution Agent Stateboard

AGENTS.md owns policy and NEXT_CODEX_GOAL.md owns the company objective. This
is the current Execution projection, not a broker-event ledger.

## Ownership

Own deterministic orders, fills, positions, cash, reconciliation, accounting
PnL, risk controls, emergency controls, and later KIS adapters. Treat model
output as untrusted input.

## Current Objective

The current read-only account diagnostic and first target-local Data recovery
receipt are complete; the current head cache has recovered under Data ownership.
The prospective QQQ scheduler has been simplified and reinstalled:
the executed virtual-only session owns its embedded `local_paper` replay, images
are built during task update rather than at due time, and the older observer is
conditional on its Data pair. Preserve the local dashboard boundary and existing
Paper recovery invariants. The latest fresh QQQ receipt is a validated scoped
no-intent; next work calibrates its runtime freshness classification rather
than forcing a canary. A recurring fixed Paper baseline follows only from
reliable execution evidence and remains independent of model promotion. KIS
Live remains unavailable.

## Current Facts

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

- local_paper, kis_paper, and kis_live remain separate routes. Local simulated
  fills retain source: local_paper.
- KIS Paper scheduled tasks and the credential-free local operations console
  already exist. Existing categorical results do not prove a selected model,
  external fill, or realized PnL.
- The current KIS Paper price/account route is private and virtual-only. No
  KIS_LIVE_* value is readable or callable.
- One existing `kis-readonly` Compose invocation completed on 2026-07-27 with
  a fresh sanitized runtime projection and external source-safe evidence
  `20260727T020227800614Z-complete.json` (`sha256:39eacd...6e8db`). It used the
  virtual read-only path only; no intent, submit, modify, cancel, or broker
  reconciliation ran. A later TTL expiry correctly changes only that runtime
  view to unavailable.
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
- A separate Docker `kis-readonly` bridge completed at 2026-07-28 00:58 KST.
  Its external source-safe record is
  `execution/kis-paper-console-bridge/20260727T155823938788Z-complete.json`.
  It proves only current virtual Paper read health, USD currency categories,
  one position, zero open orders, and `submit_capability: false`. It had no
  intent, order, modification, cancellation, or reconciliation effect and does
  not repair, replay, or supply authority for the prior QQQ receipt.
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
3. Preserve exact ambiguous Paper evidence without replacing that exact intent.
   A read-only snapshot neither reconciles it nor blocks another correctly
   scoped authorized Paper action.
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

Current class: complete for the fresh read-only account bridge, cross-fold
verifier, account diagnostic, recovered QQQ/SPY head cache, and first
contract-v2 QQQ terminal reattachment. The account runtime expires normally
after its TTL; a later refresh is a new read-only observation, not recovery of
an order.
Preserve exact ambiguous Paper evidence for the owned reconciliation route and
continue independent Data, Research, and authorized Paper work. The new QQQ
route has a complete offline and unit-tested recovery path;
`account_unavailable` constrains only the completed receipt that recorded it.

The retained-cache conflict remains historical evidence owned by the head cache.
The rebuilt image has restored a scoped head input while retaining exact
fail-closed quarantine behavior for a legacy unscoped page. Keep the virtual
route attached only to a fresh eligible receipt; do not read an account or
construct a replacement intent merely because a collection retry is scheduled.

## Next Handoff

Return any future Data/Research integration request with the existing target
binding and route boundaries intact. The completed cross-fold verifier never
acquired an account, order, KIS, Tiingo, or replay path; preserve that boundary.
The next bounded package deploys this verified contract to the existing
lane-owned schedule and observes a future regular-session result without
forcing an intent. When a fresh QQQ receipt is eligible, its canary must use a
new exact durable Paper intent and re-read the current Paper account and fresh
quote at its own call site; no stale account snapshot or historical Data receipt
may act as permission or order input.
The later recurring baseline must use the same call-time technical checks and
never reuse a stale account projection or an unknown exact intent.
