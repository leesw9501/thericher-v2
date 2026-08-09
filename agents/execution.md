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
| Read-only Paper account observer | Exact sidecar receipt reattached as `complete`; dashboard health reports no broker calls. | Marker-present provenance assumes an honest host; it is not cryptographic Scheduler-origin proof. |
| Scheduled Paper mode | The installed quote-session task runs the `kis-paper-session` Compose profile, which pins `THERICHER_MODE: kis_paper`. | The host default `THERICHER_MODE=off` does not disable this virtual-Paper task; the service still has no `KIS_LIVE_*` surface. |
| Scheduled image provenance | On 2026-08-10, the enabled one-action quote-session task reattested to the expected `kis-paper-session` virtual route. Its local image `sha256:6d2bc1131a70...` is present, and the session/canary runtime sources are unchanged from reachable attested revision `586844d`. | The image has no embedded source-revision label, so this is local route/image compatibility evidence, not cryptographic build provenance, a KIS call, submit, fill, account fact, or proof of the next task outcome. |
| Virtual-Paper lifecycle canary | The latest exact canary is `canary_completed/intent_recorded` with direct lifecycle `not_submitted/unresolved`; its offline source-safe lifecycle fact now classifies the pre-submit disposition as `reconciliation_unavailable`. The 2026-08-10 complete immutable-corpus audit validated all 19 session envelopes, all 11 direct lifecycle bindings, and every reader hash binding; direct categorical states were eight `cancelled`, one `not_submitted`, and two `outcome_unknown`. | The latest anomaly is exact-run scoped, not evidence that the schedule or Paper route is globally disabled. The reader emits only a closed disposition, never a raw broker or reconciliation reason; it is not a submit, fill, PnL, profitability, or model result. |
| Intraday QQQ/SPY data chain | Latest chain is Data `input_unavailable`; its optional offline causal-attestation binding is `not_recorded`. The embedded QQQ runtime route separately retains `observed_provisional` input evidence. | Only the existing task-owned QQQ route may use its current runtime cache for one virtual-Paper observation. Its v5 session/validator grade stays non-promoting with provider availability/finality and PnL unobserved. |
| Tiingo IEX r1 CUDA integration | The fixed source-isolated reconstruction receipt completed outside all execution routes. | It creates no candidate, price/return signal, intent, sizing input, replay-parity claim, or KIS/Paper action. |

## Ready / Owned / Due

| Work | Owner | Next action |
| --- | --- | --- |
| Virtual-Paper lifecycle canary | Existing `thericher-kis-paper-quote-session` task, 23:45 KST result monitor, and one-shot Tuesday 06:35 KST thread fallback | Static reattestation found no newer direct or session receipt after the 2026-08-07 task result. Next owned opportunity: 2026-08-10 23:35 KST. The fallback first branches on the actual current goal, so it reattaches a still-active canary lifecycle before its original intraday follow-up. Do not manually invoke or duplicate any worker. |
| Lifecycle closure objective | Execution | Reattach the next eligible existing canary receipt as source-safe operational evidence. Any scoped unknown uses its exact durable recovery path; it never authorizes a repeat submission. |
| Read-only account snapshot | Existing observer task | The existing four-minute task remains the sole recurring owner. |
| QQQ/SPY intraday causal evidence | Data-owned `thericher-kis-paper-intraday-head` task | Execution consumes no causal-qualified model input during the current objective; the existing QQQ provisional route remains a separate, task-owned observation. |
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
