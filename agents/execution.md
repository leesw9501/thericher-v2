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
| Broker-free local Paper | The existing receipt bridge and event-sourced simulator prove exact receipt identity, deterministic next-bar fills, `source: local_paper`, idempotent replay, and no network/credential access. A synthetic caller-owned two-step policy fixture also proves sequential external decisions retain next-bar, fee/slippage, terminal-flat replay, and realized-after-cost semantics. A pure offline FIFO projection binds every valid local fill to its accepted order and retains entry/exit decision roles plus pair totals; its closed segments can resolve only to exact canonical receipt lineage. Persisted event and accepted-order timestamps now reject timezone-less values rather than interpreting local host time, and a cancellation cannot precede its accepted event. Receipt/price-proof validity expires exclusively at `valid_until` so the exact boundary becomes a deterministic no-intent. The pure target-policy cycle is covered through that bridge only, with no KIS decision. | This is fixture-backed local-simulation interface evidence only; it rejects malformed accounting or missing/duplicate/role/instrument-mismatched receipts and does not claim a current market input, KIS account interaction, Paper submission, fill, broker PnL, causal credit, or model result. |
| Read-only Paper account observer | Exact sidecar receipt reattached as `complete`; dashboard health reports no broker calls. | Marker-present provenance assumes an honest host; it is not cryptographic Scheduler-origin proof. |
| Scheduled Paper mode | The installed quote-session task runs the `kis-paper-session` Compose profile, which pins `THERICHER_MODE: kis_paper`. | The host default `THERICHER_MODE=off` does not disable this virtual-Paper task; the service still has no `KIS_LIVE_*` surface. |
| Scheduled image provenance | On 2026-08-10, the enabled one-action quote-session task reattested to the expected `kis-paper-session` virtual route. Its local image `sha256:6d2bc1131a70...` is present, and the session/canary runtime sources are unchanged from reachable attested revision `586844d`. | The image has no embedded source-revision label, so this is local route/image compatibility evidence, not cryptographic build provenance, a KIS call, submit, fill, account fact, or proof of the next task outcome. |
| Virtual-Paper lifecycle canary | The 2026-08-17 23:35 KST owned quote-session receipt reattached through the offline session and direct lifecycle readers as `canary_completed -> cancelled / clean`, `paper_only`, and attribution `not_eligible`; the bound direct receipt records only an acknowledged order-reference category. The earlier 2026-08-11 `outcome_unknown / unresolved` remains separately reconciled. | Neither exact run proves a fill or creates PnL, profitability, alpha, or model evidence; never resubmit either durable intent, and let each existing reconciliation path own its run. |
| Intraday QQQ/SPY data chain | The 2026-08-17 task-owned terminal is `complete` with verified coverage/availability bindings, matching the 2026-08-15 `incomplete/current_session_short` category; the optional pair binding is `legacy_unbound`, so Data retains `input_unavailable/session_coverage_incomplete`. The embedded QQQ runtime route separately retains `observed_provisional` input evidence. | The matching short-session category cannot create an Execution consumer. The v5 session/validator grade stays non-promoting with provider availability/finality and PnL unobserved. |
| Intraday dispatcher markers | The first post-writer marker binds one exact `collection_exit_nonzero / reason_unavailable` terminal. The later hash-bound marker is `retained_partial/current_session_not_complete` with a successful collection outcome, so its compatibility-default category is noncomparable. | Neither record is collector/provider cause attribution or a recovery premise. Neither called a broker, changed a Paper route, altered an intent, or qualified an Execution consumer. Marker provenance assumes an honest host and is not Scheduler-origin proof. |
| Tiingo IEX r1 CUDA integration | The fixed source-isolated reconstruction receipt completed outside all execution routes. | It creates no candidate, price/return signal, intent, sizing input, replay-parity claim, or KIS/Paper action. |

## Ready / Owned / Due

| Work | Owner | Next action |
| --- | --- | --- |
| Virtual-Paper lifecycle canary | Existing `thericher-kis-paper-quote-session` task and 23:45 KST result monitor | The 2026-08-17 exact run is `cancelled / clean`, `paper_only`, and `not_eligible` for attribution; its source-safe direct receipt is only an acknowledged order-reference category. The 2026-08-11 unknown remains with its own reconciliation path. Next owned opportunity: 2026-08-19 23:35 KST. Do not manually invoke, duplicate, or resubmit. |
| Lifecycle closure objective | Execution | The 2026-08-10 closure remains historical evidence. The 2026-08-11 exact run is separately unresolved and must reconcile its own durable intent; it does not revise, fill, or attribute either receipt. |
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
