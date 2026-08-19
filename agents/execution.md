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

| Surface | Current fact | Limit |
| --- | --- | --- |
| Private operator dashboard | Loopback-only dashboard and local pause/resume controls are complete. | It has no public bind or broker-order control. `cancel_open_orders_requested` remains a projection-only state until a separately owned consumer can reconcile an exact durable order, so the dashboard does not present a misleading cancellation command. |
| Tiingo prospective EOD ETF snapshot | Data reattached one fixed SPY/QQQ/IWM external prospective snapshot through the existing three-request path. | It remains lineage-only with point-in-time, model, training, campaign, ranking, order, Paper, and GPU eligibility false. It creates no execution input, intent, order route, PnL fact, or KIS recovery. |
| Broker-free local Paper | The existing receipt bridge and event-sourced simulator prove exact receipt identity, deterministic next-bar fills, `source: local_paper`, idempotent replay, and no network/credential access. A synthetic caller-owned two-step policy fixture also proves sequential external decisions retain next-bar, fee/slippage, terminal-flat replay, and realized-after-cost semantics. Account replay rejects an oversell at the offending fill even when a later buy would balance the final position. A pure offline FIFO projection binds every valid local fill to its accepted order and retains entry/exit decision roles plus pair totals; its closed segments can resolve only to exact canonical receipt lineage. Persisted event and accepted-order timestamps now reject timezone-less values rather than interpreting local host time, and a cancellation cannot precede its accepted event. Receipt/price-proof validity expires exclusively at `valid_until` so the exact boundary becomes a deterministic no-intent. The pure target-policy cycle is covered through that bridge only, with no KIS decision. | This is fixture-backed local-simulation interface evidence only; it rejects malformed accounting or missing/duplicate/role/instrument-mismatched receipts and does not claim a current market input, KIS account interaction, Paper submission, fill, broker PnL, causal credit, or model result. |
| Read-only Paper account observer | Exact sidecar receipt reattached as `complete`; dashboard health reports no broker calls. | Marker-present provenance assumes an honest host; it is not cryptographic Scheduler-origin proof. |
| Scheduled Paper mode | The installed quote-session task runs the `kis-paper-session` Compose profile, which pins `THERICHER_MODE: kis_paper`. | The host default `THERICHER_MODE=off` does not disable this virtual-Paper task; the service still has no `KIS_LIVE_*` surface. |
| Scheduled image provenance | On 2026-08-10, the enabled one-action quote-session task reattested to the expected `kis-paper-session` virtual route. Its local image `sha256:6d2bc1131a70...` is present, and the session/canary runtime sources are unchanged from reachable attested revision `586844d`. | The image has no embedded source-revision label, so this is local route/image compatibility evidence, not cryptographic build provenance, a KIS call, submit, fill, account fact, or proof of the next task outcome. |
| Virtual-Paper lifecycle canary | The 2026-08-19 23:35 KST owned quote-session receipt reattached through the offline session and direct lifecycle readers as `canary_completed -> cancelled / clean`, `paper_only`, and attribution `not_eligible`; its hash-bound direct receipt records only an acknowledged order-reference category. The credential-free runtime projection is `unknown`, so it adds no current-state claim. The 2026-08-11 session/direct readers bind the same opaque lineage as `outcome_unknown / unresolved`, `paper_only`, and attribution `unavailable`. Its closed exact-recovery assessment retained that state: no predeclared source-safe prior-reconciliation pointer or private durable-state binding existed, so no repeat KIS read ran. | Neither exact run proves a fill or creates PnL, profitability, alpha, or model evidence; never resubmit either durable intent. A future broker-facing recovery needs a fresh exact durable binding and prior-attempt proof, rather than treating `outcome_unknown` as permission for another read. |
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
| Snapshot observer fixture isolation | The read-only observer retains its production global mutex default; fixture calls pass a unique mutex name so an active task-owned observer cannot turn a fake-host test into `observer_busy`. | It changes no task definition, production mutex default, Docker route, KIS call, account read, submit capability, order behavior, or live route. |
| Historical KIS D1 CPU baseline | QQQ and SPY each completed four fixed offline replay cells under hash-bound external contracts; all fills remained `source: local_paper`. | Every after-cost cell was negative. This is replay-accounting evidence only, never broker PnL, a KIS input, intent, Paper action, or model-selection result. |
| KIS D1 L2 logistic control | The fixed development-only QQQ/SPY control completed two model and six comparator validation replays under hash-bound external evidence; every fill remained `source: local_paper`. | Both model after-cost cells were negative and below the fixed previous-bar-direction comparator. This is replay-accounting evidence only, never broker PnL, an input, intent, Paper action, or model-selection result. |
| KIS D1 regime-tree breadth | The fixed development-only QQQ/SPY shallow-tree reproduction completed two model and six comparator validation replays under hash-bound external evidence; every fill remained `source: local_paper` and no fitted estimator was serialized. | Both model after-cost cells were below the fixed previous-bar-direction comparator. This closes a replay-accounting control only; it is never broker PnL, an input, intent, Paper action, or model-selection result. |
| Tiingo IEX r1 CUDA integration | The fixed source-isolated reconstruction receipt completed outside all execution routes. | It creates no candidate, price/return signal, intent, sizing input, replay-parity claim, or KIS/Paper action. |

## Ready / Owned / Due

| Work | Owner | Next action |
| --- | --- | --- |
| Virtual-Paper lifecycle canary | Existing `thericher-kis-paper-quote-session` task and 23:45 KST result monitor | The 2026-08-19 exact run is `cancelled / clean`, `paper_only`, and `not_eligible` for attribution; its source-safe direct receipt is only an acknowledged order-reference category, while the credential-free runtime projection is `unknown`. The 2026-08-11 exact reader pair remains `outcome_unknown / unresolved`; the closed assessment made no KIS call because it could not prove this would be the first reconciliation. Next owned opportunity: 2026-08-20 23:35 KST. Do not manually invoke, duplicate, or resubmit. |
| Lifecycle closure objective | Execution | Complete. The 2026-08-11 run remains a scoped unresolved outcome, not an eligible retry, fill, or attribution fact. |
| Read-only account snapshot | Existing observer task | The existing four-minute task remains the sole recurring owner. |
| QQQ/SPY intraday causal evidence | Data-owned `thericher-kis-paper-intraday-head` task | The first post-writer bound task path is one comparable `collection_exit_nonzero / reason_unavailable` category. The later successful partial terminal is Data-only and noncomparable, so Execution consumes no causal-qualified model input; the existing QQQ provisional route remains separately task-owned. |
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
