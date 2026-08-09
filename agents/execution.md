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
| Private operator dashboard | Loopback-only dashboard and local pause/resume controls are complete. | It has no public bind and no broker-order control. |
| Read-only Paper account observer | Exact sidecar receipt reattached as `complete`; dashboard health reports no broker calls. | Marker-present provenance assumes an honest host; it is not cryptographic Scheduler-origin proof. |
| Virtual-Paper lifecycle canary | The latest exact canary is `canary_completed/intent_recorded` with direct lifecycle `not_submitted/unresolved`. A bounded, source-safe audit of the latest eight exact receipts found five acknowledged submissions that later cancelled cleanly, two scoped `outcome_unknown` results, and this one `not_submitted` result. | The latest anomaly is exact-run scoped, not evidence that the schedule or Paper route is globally disabled. The fact-minimized receipt does not expose a pre-submit cause; it is not a submit, fill, PnL, profitability, or model result. |
| Intraday QQQ/SPY data chain | Latest chain is Data `input_unavailable`. | Execution must not consume it without a later qualified objective and replay parity. |

## Ready / Owned / Due

| Work | Owner | Next action |
| --- | --- | --- |
| Virtual-Paper lifecycle canary | Existing `thericher-kis-paper-quote-session` task | Next owned opportunity: 2026-08-10 23:35 KST. Do not manually invoke or duplicate it; validate its own source-safe receipt independently. |
| Read-only account snapshot | Existing observer task | The existing four-minute task remains the sole recurring owner. |
| QQQ/SPY intraday causal evidence | Data-owned `thericher-kis-paper-intraday-head` task | Execution consumes nothing during the current objective. |
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
