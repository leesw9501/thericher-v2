# Execution Agent Stateboard (Execution)

`AGENTS.md` owns policy and `NEXT_CODEX_GOAL.md` owns the company objective.
This is the current virtual-Paper execution projection, not an order log. Git
and immutable external receipts retain historical lifecycle evidence.

## Ownership And Hard Boundary

Execution owns deterministic sizing/risk, intent persistence, broker routes,
fills, positions, reconciliation, accounting, and emergency controls. It treats
model output as untrusted input. `local_paper`, `kis_paper`, and `kis_live`
are separate routes; local replay fills remain `source: local_paper`. Never
read or route `KIS_LIVE_*`.

## Current Execution Facts

2026-09-22 operator sizing update: approximately 10 percent of virtual cash is
approved as the initial aggregate strategy-Paper allocation, not per-order
spend. The budget mode is implemented and deployed on the existing daily SPY
baseline. One private account-bound initial funding basis stays fixed; accepted
entry costs and residual buy reservations share its cap. Exact owned inventory
and pending intent recovery precede any new daily input/signal. Do not scale
the separate roundtrip diagnostic or await profitability/D1 approval. Other
fixed one-share entry points retain their original behavior.

Final budget verification: 439 focused passed / 1 skipped; 3,903 full passed /
19 skipped, eight workers, 296.58s, helper cleanup/exit zero. Ruff and both
sample-env Compose configurations pass. Seven rebuilt private-state consumer
images have 42 matching source hashes. Daily image:
`sha256:df426086317da543968b1a3c39d0be1eeef7dffc20dcbd96cda00416ed4b9fe4`.
The actual Docker mount probe exposed and repaired the old private-volume path
rejection; only the exact mounted `/app/private/canary` exception is allowed.
The credential-free scoped launcher preview exited zero; its named container
is gone. Source-safe process evidence is at
`D:\thericher-v2\model-artifacts\execution\kis-paper-spy-budget\dispatch.json`.
It is not fill evidence. The daily task now invokes the budget host launcher
with 24 bounded visits and a 25-minute limit. Principal/trigger/last-run/next-run
are unchanged; next due is 2026-09-22 23:50 KST. No task was manually started,
and this implementation package made no broker call or live credential access.
Next: reattach actual decision/order/fill/accounting facts, retaining the same
funding binding and recovering the exact owned intent on incomplete outcomes.

Prior source/account checks below retain their original, narrower scope.
Two direct scoped Paper read-only account checks at 03:38:30 and 03:39:57 UTC
succeeded: USD orderable amounts positive, one position row, no open orders;
the position is neither SPY nor QQQ. No amounts, identities or raw rows were
printed/persisted, and no submit/modify/cancel endpoint was called. The values
were held only in memory; no budget was frozen and these snapshots must not be
reused as fresh facts for tonight's orders. Broker holdings alone do not prove
our strategy's fills or inventory ownership.

2026-09-22 explicit fill cycle: `kis_paper_spy_fill_cycle.py` reuses the existing
session/canary locks, private leg store and virtual client. A private account-
bound identity owns SPY buy-one/sell-one legs across restart. Fresh exact fills
and account position are required before exit/closure; broker IDs and amounts
stay private. The shared new-intent check applies only to currently owned SPY
inventory, never unrelated historical unknowns, existing recovery/cancellation
or other symbols. No-entry-POST paths release ownership before worker exit;
missing asynchronous history is reobserved without duplicate submission.
The legacy immediate-cancel/default nonmarket path is unchanged.

The scoped host launcher injects only Paper fields and uses `.env.example`
for Compose, with a single-client, at-most-20-visit worker. Independent
container/host deadlines prevent an orphan indefinitely owning the lock.
Categorical worker/dispatch status is external; exact private legs remain the
fill authority. Focused integration passed 346 tests / 1 skip in 10.92s.
Claude twice returned `supported-with-limits`; the final independent review's
zero-submission cleanup issue is covered by an immediate-release regression.
One real quote-only GET confirmed last/clock/scale in output1 and bid/ask in
output2. No account/order endpoint or order was called during that probe.
No actual fill, settled cash, fee or net-PnL result is claimed yet.
Final clean-root eight-worker authority: 3,707 passed / 19 skipped in 289.48s,
exactly the prior 3,513 plus 194 new cases; helper cleanup exited zero. Ruff,
default/research Compose with `.env.example`, and diff checks pass.
All seven existing private-state consumer images are rebuilt with 35 matching
source hashes. Session image:
`sha256:b0ed763f79e9ed40372dd472e63f12e82b5b236d954a3c9b64e26ed6da7da2d3`.
The credential-free launcher preview exited successfully and wrote `preview`;
the container deadline smoke returned expected code 124. No cycle container
remains. The old quote-task registration now owns only the 2026-09-22 22:35 KST
finite fill invocation (`spy-fill-20260922-v1`), expires 23:10, with no repetition
or retries and a 25-minute task cap. Other tasks and principal are unchanged,
and task last-run did not advance. This supersedes its earlier disabled fact
below only for this finite opportunity; it does not restore recurring canaries.
Resume this exact cycle on an unresolved outcome; do not claim a real fill from
the preview or task installation. Actual daily-SPY remains due at 23:50 KST.

2026-09-22 cumulative-fill package: the existing original-order-date history
GET now also returns a private typed quantity/amount observation. One unique
exact order/date/symbol/exchange/side/requested-quantity/USD row is required;
lineage rows are never summed. Positive amount must match quantity times
reported fill price within USD 0.01. Ambiguous/missing/malformed evidence is
scoped to that observation. The existing atomic state stores cumulative totals,
not added snapshots, so restart/duplicate reads cannot accrue another fill.
Pre-cancel and intermediate recovery observations are persisted before another
read can hide them. Regression/conflict preserves accepted totals, but only a
current available observation exposes signed position/gross-flow contribution.
Read failures and absence do not masquerade as current fills. Fees, settlement,
account cash and net PnL remain unknown; orderable funds are not cash.
New state fields are optional for legacy reads; the strict receipt observer
accepts them without changing its old same-day/structural interpretation.
Independent review found and fixed intermediate-requery loss and run-start
timestamp reuse; progressing-clock/restart synthetic tests cover both.
Changed-path coverage initially passed 228 tests / 1 skip. No new broker call,
live access or deliberately fillable cycle occurred in this source package.
Final integrated eight-worker run: 3,513 passed / 19 skipped, 294.19s; managed
cleanup completed. Ruff, default/research Compose and diff checks pass.
All seven private-state consumer images were rebuilt together using
`.env.example`; 28 networkless/read-only/no-mount source hash comparisons match
the four changed execution modules. Current session image:
`sha256:968dba2d2d5fd622eb705073a08c3f9b939c3ca0a7629f0b6005f9b4b0fbebb9`;
daily-SPY image:
`sha256:0b313ccec4f5a4c8b2efc02b5dca74138a5be9feae2d21c920d1bc568a855fec`.
No owned task was running at dispatch and no task/broker/private-state invocation
was made. The older rollout hashes below describe the previous timestamp fix.

Schedule cleanup (2026-09-22): recurring immediate-cancel `quote-session` is
disabled after its exact latest receipt revalidated `cancelled/clean`.
The explicit diagnostic/recovery command and private state remain available;
this does not declare every historical intent resolved. Execution retains
ownership of exact unresolved intents. Actual `daily-spy-session` remains
enabled at 23:50 KST and account snapshots retain the four-minute cadence.
Cleanup made no direct KIS request, private-state mutation or forced worker
stop. A review probe's accidental task re-registration was corrected; all
last-run timestamps stayed unchanged (see DECISIONS). This supersedes old quote-task
next-due statements below. Metadata/rollback is in
`D:\thericher-v2\model-artifacts\ops\schedule-cleanup-20260922`.

The active objective is `kis-paper-spy-restart-safe-lifecycle-v1`. Source fixes
now retain the original submission attempt date across restart/late-ID recovery
and keep an unrelated-open-order conflict `intent_recorded`, not an invented
unknown submission. Legacy unknown dates are not fabricated; exact ambiguous
side effects still cannot resubmit. The strict receipt observer accepts the
new optional field. Seven existing consumer images are source-compatible and
deployed; complete terminal/accounting closure remains outstanding.

New-image runtime check (2026-09-22 00:54 KST): one explicit, standing-authorized
invocation of the existing quote-session path, after checking task/container
ownership, reached `acknowledged_order_reference`, `cancelled/clean`. Its exact
session/direct readers independently validated matching run/phase/reconciliation
and timestamps. This was a direct invocation, not a Scheduler-origin claim.
Evidence under `D:\thericher-v2\model-artifacts\execution`:
- `kis-paper-canary-session\paper-session-20260921T155423665718Z\evidence.json`,
  SHA256 `067700162f733047034692559b23edc4dba0932c7c814d207c5d1f6911a297ac`;
- `kis-paper-canary\canary-20260921T155423665718Z\evidence.json`,
  SHA256 `06512035ec16a8d7c8958cc6b5946dff8f211f1b3281ebe1a7833026dec9b160`.
A separate networkless/read-only private-state parse confirmed
`submission_started_at` present, equal to `submitted_at`, and inside the intent
lifetime. It emitted only booleans/phase, not private values. This proves current
runtime persistence, not an actual date-crossing restart, fill quantity or PnL.

Rollout covers `kis-paper-session`, `kis-paper-daily-spy-session`,
`kis-paper-prospective-qqq-session`, `kis-paper-prospective-spy-cycle`,
`kis-paper-canary`, `kis-paper-receipt-observer`, and
`kis-paper-terminal-field-probe`. All 21 baked checks matched the three changed
sources, including both read-only private-state consumers. Session image:
`sha256:f9851c34757f6b1e126423c946d393c303100a3196b610ff52055a05c3b5a025`.
Source SHA256 values, respectively canary, readonly, receipt observer:
`e202286515bd01a26c381263b52e8b2e51a2868ff903578af741cd63d1d47f21`,
`26eb18818d99ca83224136f81d5b0fc851aa797c29dbd2951d5aad6dfed2bca4`,
`16358d71ce79b44388fc4683b710348c67b5d058ba8d09a44adec33e3ec22982`.
No new schedule, live route, strategy selection or fill-accounting claim.

Fresh existing-task evidence (2026-09-21 23:35 KST, old image):
`paper-session-20260921T143502071908Z` and
`canary-20260921T143502071908Z` independently parse with matching run, phase,
reconciliation and subsecond timestamps: `acknowledged_order_reference`,
`cancelled/clean`. Session SHA256:
`7d2cdbacba8638253d955925c7a85be1be22576285d2f1c3792996c0743cdd83`;
direct SHA256:
`44471f1a860eae7e39c79aedf974e6f61b5bd84fa02e40b68961bdfd706dbebf`.
Exact paths are under `D:\thericher-v2\model-artifacts\execution`, respectively
`kis-paper-canary-session\paper-session-20260921T143502071908Z\evidence.json`
and `kis-paper-canary\canary-20260921T143502071908Z\evidence.json`.
These are application-receipt bindings, not cryptographic scheduler-origin
proof. They prove neither new-patch restart behavior nor fills, account PnL,
profitability, or the complete company outcome. The recurring quote task is now
disabled; D1 remains independent and older table rows are historical.

One standing-authorized, exact-run read-only history field probe at
2026-09-21T15:02:13.669177Z used the installed virtual-only terminal-probe
profile with the private-state volume read-only. It returned
`observed/history_observed`, `identity_match: absent`, complete pagination and
no observed quantity/amount fields; terminal support remains unqualified and
PnL unobserved. Do not infer a fill or zero fill from this absence. No account
endpoint or submit/modify/cancel ran in this probe. Its exact source-safe receipt:
`D:\thericher-v2\model-artifacts\execution\kis-paper-terminal-field-probe\run-6f6e1d51f2689201\20260921T150213669177Z-b61bd1d5488ee055.json`.
The initial Docker dispatch failed before a container started: the minimal
environment omitted Windows Compose plugin discovery variables. Restoring
standard Windows/Docker connection variables fixed dispatch; only the four
authorized Paper values were loaded by the existing scoped loader, with
`.env.example` passed to Compose. No live value or raw error was exposed.
Next terminal/accounting work must obtain positive quantity/position/cash
evidence for its exact lifecycle, not repeat this absent cancelled-row probe
as a company-wide wait or permission check.

The current quote-session and receipt preparation both derive a below-last
buy limit; the quote task then cancels immediately. That is useful transport
and cancellation evidence, not a design for accumulating fill/PnL observations.
After recovery rollout, the next implementation must connect exact terminal
quantities to private position/cash accounting and exercise a deliberately
fillable bounded Paper cycle. Do not silently change the existing canary's
pricing or infer a zero fill from cancellation/absence alone.
The existing numeric `ord_psbl_frcr_amt` is orderable funds, not settled cash
or equity. The next private accounting adapter must bind order/date/instrument/
side/currency/quantities, make duplicate observations no-ops, and reject only
the exact regressive/conflicting observation. Broker fills stay `kis_paper`,
never `local_paper`. Unknown fee or settlement semantics cannot become invented
zero fees or broker net PnL. A fillable cycle may exit only its own confirmed
inventory; it need not wait for the old cancelled row to reappear.

| Surface | Current fact | Limit |
| --- | --- | --- |
| Private operator dashboard | Loopback-only dashboard and local pause/resume controls are complete. | It has no public bind or broker-order control. `cancel_open_orders_requested` remains a projection-only state until a separately owned consumer can reconcile an exact durable order, so the dashboard does not present a misleading cancellation command. |
| Tiingo prospective EOD ETF snapshot | Data reattached one fixed SPY/QQQ/IWM external prospective snapshot through the existing three-request path. | It remains lineage-only with point-in-time, model, training, campaign, ranking, order, Paper, and GPU eligibility false. It creates no execution input, intent, order route, PnL fact, or KIS recovery. |
| Broker-free local Paper | The existing receipt bridge and event-sourced simulator prove exact receipt identity, deterministic next-bar fills, `source: local_paper`, idempotent replay, and no network/credential access. A synthetic caller-owned two-step policy fixture also proves sequential external decisions retain next-bar, fee/slippage, terminal-flat replay, and realized-after-cost semantics. Account replay rejects an oversell at the offending fill even when a later buy would balance the final position. A pure offline FIFO projection binds every valid local fill to its accepted order and retains entry/exit decision roles plus pair totals; its closed segments can resolve only to exact canonical receipt lineage. Persisted event and accepted-order timestamps now reject timezone-less values rather than interpreting local host time, and a cancellation cannot precede its accepted event. Receipt/price-proof validity expires exclusively at `valid_until` so the exact boundary becomes a deterministic no-intent. The pure target-policy cycle is covered through that bridge only, with no KIS decision. | This is fixture-backed local-simulation interface evidence only; it rejects malformed accounting or missing/duplicate/role/instrument-mismatched receipts and does not claim a current market input, KIS account interaction, Paper submission, fill, broker PnL, causal credit, or model result. |
| FirstRate 5m CPU cost controls | The completed source-local L2 and fixed 20/60 technical-trend controls produced 18 aggregate-only replay cells each; the fixed Wilder-RSI mean-reversion control produced 12. Every cell reattached with `source: local_paper`, replayable accounting, and terminal-flat position. | All three are rejected descriptive research results, not Execution inputs: none made a KIS/broker call, persisted a raw local-paper event stream, or can create an intent, order, Paper consumer, PnL claim, or GPU promotion. |
| Tiingo D1 trend-pullback rotation | The completed frozen retrospective rotation stopped at `input_unavailable/insufficient_validation_active_decisions` before any replay or PnL computation. Its aggregate audit consistently attributed all validation exclusions to the event mask and closed the lineage. | It created no Execution input, intent, local-paper fill, order, PnL, KIS, Paper, or GPU claim. No execution behavior changes from this result. |
| Read-only Paper account observer | Exact sidecar receipt reattached as `complete`; dashboard health reports no broker calls. | Marker-present provenance assumes an honest host; it is not cryptographic Scheduler-origin proof. |
| Scheduled Paper mode | The installed quote-session task runs the `kis-paper-session` Compose profile, which pins `THERICHER_MODE: kis_paper`. | The host default `THERICHER_MODE=off` does not disable this virtual-Paper task; the service still has no `KIS_LIVE_*` surface. |
| Scheduled image provenance | On 2026-08-10, the enabled one-action quote-session task reattested to the expected `kis-paper-session` virtual route. Its local image `sha256:6d2bc1131a70...` is present, and the session/canary runtime sources are unchanged from reachable attested revision `586844d`. | The image has no embedded source-revision label, so this is local route/image compatibility evidence, not cryptographic build provenance, a KIS call, submit, fill, account fact, or proof of the next task outcome. |
| Virtual-Paper lifecycle canary | The 2026-09-01 23:35 KST owned session (`sha256:d63b537ce4aeabbb4c556863e6864f37fb9903c53116f8642bef35890e03b68d`) reattached its matching direct lifecycle receipt (`sha256:16494b8ac6961c375867e026a4e3add1087edbdbf6b1d647d622ea443e279255`) as `canary_completed -> not_submitted / unresolved`, `paper_only`, `pre_submit_disposition: reconciliation_unavailable`, and `submit_response_category: not_observed`; offline validation matched the lifecycle projection. The credential-free runtime projection is absent. | This exact run proves neither a broker submission nor a fill, PnL, profitability, alpha, or model fact. Do not resubmit its durable intent; its exact recovery class remains reconciliation-unavailable. |
| Intraday QQQ/SPY data chain | The 2026-08-17 task-owned terminal is `complete` with verified coverage/availability bindings, matching the 2026-08-15 `incomplete/current_session_short` category; the optional pair binding is `legacy_unbound`, so Data retains `input_unavailable/session_coverage_incomplete`. A separate direct host collection completed its bounded two-target scope but has no Task/Docker causal provenance. The first direct container attempt yielded at the shared token-start gate; a due-gate attempt quarantined conflicting retained head entries, and the one allowed later direct Compose recovery completed cleanly. The embedded QQQ runtime route separately retains `observed_provisional` input evidence. | Neither the short-session category nor any collector/quarantine/recovery probe can create an Execution consumer. The v5 session/validator grade stays non-promoting with provider availability/finality and PnL unobserved. |
| Intraday dispatcher markers | The first post-writer marker binds one exact `collection_exit_nonzero / reason_unavailable` terminal. The later hash-bound marker is `retained_partial/current_session_not_complete` with a successful collection outcome, so its compatibility-default category is noncomparable. | Neither record is collector/provider cause attribution or a recovery premise. Neither called a broker, changed a Paper route, altered an intent, or qualified an Execution consumer. Marker provenance assumes an honest host and is not Scheduler-origin proof. |
| KIS broad D1 continuation | The 2026-08-19 direct daily-broad continuation reattached an all-terminal current-listing historical index and exited with zero chunks/pages, so it constructed no KIS client. | It is not a current daily input, Execution consumer, order route, or Paper claim. A separate QQQ/SPY forward cache remains Data-owned. |
| KIS QQQ/SPY D1 forward refresh | The 2026-08-19 direct two-target attempt deferred at `token_request_not_due` with zero new pages and zero changed targets. | It creates no execution input, intent, order route, Paper claim, or PnL fact; the existing Data task owns a later retry. |
| KIS D1 forward causal qualification | Data completed one offline predicate for the current QQQ/SPY cache. It is `input_unavailable` because named clock/session, decision-time availability, and provider finality are unobserved; no credential, collection, KIS client, Docker, scheduler, GPU, research, or execution path ran. | Its result is input provenance only. It cannot create an intent, sizing input, broker route, Paper action, PnL fact, or model-selection result. |
| KIS QQQ/SPY D1 one-shot collection | The required preflight was `collection_required`; exactly one KIS Paper collector then closed `unavailable/collector_unavailable` with no cache payload. A static search found no Research/Execution `latest_session` consumer. | No Execution consumer, intent, order route, Paper action, PnL fact, or model-selection result followed. |
| KIS QQQ/SPY D1 runtime-image provenance | Data/Infra completed a common local image tag plus one credential-free networkless `collection_required` preflight whose payload stage-contract hash matches the host contract. It did not call the collector. | It is not full image freshness, data availability, finality, an Execution input, intent, order route, Paper action, PnL fact, or model-selection result. |
| KIS QQQ/SPY D1 stage-aware one-shot collection | The one shared-tag collector closed `unavailable/collector_unavailable/failure_stage=commit` with a matching static contract hash, no cache payload, and no observed cache-file/index write in its invocation window. | This is an unknown Data commit-stage result only. It creates no Execution input, intent, order route, Paper action, PnL fact, or model-selection result. |
| KIS QQQ/SPY D1 commit failure classification | The source/fixture-only v2 static contract adds an optional fixed kind only to future commit-stage Data receipts. | It leaves the prior failure unknown and creates no Execution input, intent, order route, Paper action, PnL fact, or model-selection result. |
| KIS QQQ/SPY D1 v2 one-shot collection | The matching credential-free preflight permitted exactly one collector call, which closed as `unavailable/collector_unavailable/failure_stage=commit/commit_failure_kind=cache_contract`; its cache reattest is unchanged with seven common sessions. | This is a Data-only failure-family fact. It creates no Execution input, intent, order route, Paper action, PnL fact, or model-selection result. |
| KIS QQQ/SPY D1 commit-phase diagnostic | Static v3 permits a future `cache_contract` receipt to carry one fixed cache-operation phase only. It does not reinterpret the v2 result. | It creates no Execution input, intent, order route, Paper action, PnL fact, or model-selection result. |
| KIS QQQ/SPY D1 v3 one-shot collection | The matching credential-free preflight permitted exactly one collector call, which closed as `commit/cache_contract/cache_prepare`; the cache reattest is unchanged with seven common sessions. | This is a Data-only prepare-phase fact. It creates no Execution input, intent, order route, Paper action, PnL fact, or model-selection result. |
| KIS QQQ/SPY D1 prepare-subphase diagnostic | Static v4 permits only a source-region label on a future exact `commit/cache_contract/cache_prepare` receipt; it leaves the completed v3 result subphase-unknown. | It creates no Execution input, intent, order route, Paper action, PnL fact, or model-selection result. |
| KIS QQQ/SPY D1 v4 one-shot collection | One v4 preflight permitted one collector, which deferred with source-safe authentication/token-gate target states and no v4 subphase. | This is a Data-only route fact. It creates no Execution input, intent, order route, Paper action, PnL fact, or model-selection result. |
| KIS Paper authentication capability probe | One token-only virtual-host receipt reattached as `authenticated`; no daily/minute market data, account, position, quote, order, or live route is recorded. | This is a Data-only endpoint-capability fact. It creates no Execution input, intent, order route, Paper action, PnL fact, or model-selection result. |
| KIS QQQ/SPY D1 v5 readiness and one-shot collection | Gate-open readiness made no network/cache write; one daily collector then failed at the source-safe `incoming_merge` cache-prepare region and the prior cache reattached unchanged. The source/fixture reconciliation keeps a conflicting retained row immutable, quarantines only that target, and rejects it at the causal reader boundary. | This remains a Data-only cache-recovery fact. It creates no Execution input, intent, order route, Paper action, PnL fact, or model-selection result. |
| KIS QQQ/SPY D1 post-reconciliation observation | One fixed-pair collector retained two revision conflicts and quarantined both targets; the offline causal reader returned `input_unavailable` with source-pair identity unsatisfied. | This is still Data-only. It creates no Execution input, intent, order route, Paper action, PnL fact, or model-selection result. |
| KIS QQQ/SPY D1 v2 fresh cache | Data bootstrapped a separately identified QQQ/NAS + SPY/AMS cache with one `ready` daily-market-data receipt and a credential-free `cache_current` reattach. The v1 cache was not mounted or changed. | The v2 cache is not an Execution input: it has no point-in-time availability, provider-finality, or corporate-action qualification, and it created no intent, order route, Paper action, PnL, or model-selection result. |
| KIS D1 prospective observation pairing | The approved offline reader validates the completed-session 2026-09-04 first-stage receipt as `input_unavailable/first_observation_target_failure` (`sha256:a7d54a2220bb5f7ca78a9e34a48c827fbe6c03d4c5f575c5c23a0d12519af401`), with no first-receipt binding or later observation; it is not a pair result. | It can only identify a changed or missing observation as a Data disqualification. A matching pair is not an Execution input, intent, order, Paper action, PnL result, or model-selection claim. |
| Snapshot observer fixture isolation | The read-only observer retains its production global mutex default; fixture calls pass a unique mutex name so an active task-owned observer cannot turn a fake-host test into `observer_busy`. | It changes no task definition, production mutex default, Docker route, KIS call, account read, submit capability, order behavior, or live route. |
| Historical KIS D1 CPU baseline | QQQ and SPY each completed four fixed offline replay cells under hash-bound external contracts; all fills remained `source: local_paper`. | Every after-cost cell was negative. This is replay-accounting evidence only, never broker PnL, a KIS input, intent, Paper action, or model-selection result. |
| KIS D1 L2 logistic control | The fixed development-only QQQ/SPY control completed two model and six comparator validation replays under hash-bound external evidence; every fill remained `source: local_paper`. | Both model after-cost cells were negative and below the fixed previous-bar-direction comparator. This is replay-accounting evidence only, never broker PnL, an input, intent, Paper action, or model-selection result. |
| KIS D1 regime-tree breadth | The fixed development-only QQQ/SPY shallow-tree reproduction completed two model and six comparator validation replays under hash-bound external evidence; every fill remained `source: local_paper` and no fitted estimator was serialized. | Both model after-cost cells were below the fixed previous-bar-direction comparator. This closes a replay-accounting control only; it is never broker PnL, an input, intent, Paper action, or model-selection result. |
| Tiingo IEX r1 CUDA integration | The fixed source-isolated reconstruction receipt completed outside all execution routes. | It creates no candidate, price/return signal, intent, sizing input, replay-parity claim, or KIS/Paper action. |

## Ready / Owned / Due

| Work | Owner | Next action |
| --- | --- | --- |
| Virtual-Paper lifecycle canary | Execution / existing quote-session owner | New-image direct session is `cancelled/clean` with valid durable attempt time; seven private-state consumers are compatible. Next: exact terminal quantity/accounting support and a fillable cycle. Do not duplicate an active worker or resubmit an unresolved intent. |
| Historical lifecycle closure | Execution | The 2026-08-11 assessment closed its evidence review only, leaving an unresolved intent. Repeated exact-bound read-only reconciliation is permitted; runtime recovery is still outstanding under the new company objective. |
| Read-only account snapshot | Existing observer task | The existing four-minute task remains the sole recurring owner. |
| QQQ/SPY intraday causal evidence | Data-owned `thericher-kis-paper-intraday-head` task | The first post-writer bound task path is one comparable `collection_exit_nonzero / reason_unavailable` category. The later successful partial terminal is Data-only and noncomparable, so Execution consumes no causal-qualified model input; the existing QQQ provisional route remains separately task-owned. |
| QQQ/SPY D1 prospective pairing | Data-owned observer | Independent measurement; current source-safe status is in `agents/data.md`. Its result is not a prerequisite for the baseline Paper lifecycle and is not itself Execution input. |
| QQQ provisional runtime observation | Embedded existing intraday-head child | The v5 validation contract recomputes the fixed non-promoting grade. Do not manually invoke, duplicate, or interpret it as model/PnL evidence. |
| Any unknown exact Paper outcome | Execution reconciliation path | Reconcile the exact durable intent; never infer success or create a fresh action from ambiguity. |

## Deterministic Controls

- Persist intent before a broker side effect and reconcile a prior unknown
  outcome before retrying that exact intent.
- Keep Paper virtual-host identity, route allowlist, state root, and task
  ownership exact. A distinct correctly scoped Paper action is not blocked by
  unrelated evidence.
- Dashboard/UI actions change local controls only unless a separately owned,
  deterministic execution route is explicitly invoked.
- No model, public code, or arbitrary checkpoint runs inside Execution.
- Research promotion evidence must reattest cost, latency, fill, and
  availability assumptions through Execution before comparison, ensemble, or
  Paper-candidate use.

## Current Evidence

- Source-safe Paper observer evidence:
  `D:\thericher-v2\model-artifacts\execution\kis-paper-snapshot-observer`.
- Intraday terminal reader:
  `scripts\project_kis_paper_intraday_head_schedule_receipt.py`.
- Docker dashboard contract is loopback-only and credential-free for its health
  path; no account values are retained in this stateboard.

## Handoff

When Engine Research supplies a frozen candidate, independently reattest its
replay parity before any Paper-candidate claim. A failed attestation narrows
only that candidate; it is never a general Paper approval hold. Live capital,
live credentials, and live routing remain operator-only boundaries.

The bounded Claude CLI drift-check for the local decision-PnL projection
returned no response, so its status is `review_unavailable`; no Claude verdict
was relied on for this offline, non-promoting implementation.
