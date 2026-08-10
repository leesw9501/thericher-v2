# Codex Orchestration Stateboard (제품개발 총괄)

`AGENTS.md` owns policy and `NEXT_CODEX_GOAL.md` owns the company objective.
This is a current cross-lane projection, not a queue or history ledger. Git and
external source-safe receipts retain completed evidence.

## Company Objective

`kis-intraday-causal-observation-closure-v1` will reattach the next terminal
chain from the existing intraday-head task. Its external due time belongs to
that task; the objective must not turn it into foreground idle. It is data
availability evidence only, never a strategy, PnL, or live claim.

## Ready / Owned / Due

| Work | Owner | Resource | Current fact and next action |
| --- | --- | --- | --- |
| Tiingo IEX r1 integration | Data / Engine Research | Immutable r1 snapshot and external artifact root | Closed: host and container reattested the same raw, manifest, gzip, and canonical payload identities. CPU and CUDA fixed matrices completed; only categorical completion and cleanup receipts exist. |
| GPU custody | Research Steward | RTX 4090 | Released: one source-isolated target-free appointment spent no sealed evaluation and retained no weights. No predictive GPU appointment is active. |
| KIS Paper lifecycle canary | Execution | Existing `thericher-kis-paper-quote-session` task | Closed for the 2026-08-10 owned receipt: `canary_completed -> cancelled / clean`, `paper_only`, and attribution `not_eligible`. Future evidence remains task-owned; no manual task, container, or duplicate submission. |
| Norgate local readiness | Data | Existing NDU updater | The responsive NDU instance predates the 2026-08-09T18:34:14Z `UPDATE DONOTSHOW` request. Its status-only response is HTTP `402`, categorized as `subscription_or_update_unavailable` without an expiry claim; a later hidden start only joined the existing instance. This does not block the Paper canary. The daily operating review may recheck the local reader without duplicate starts or triggers; if still unavailable, one operator-visible NDU update plus database/subscription-state diagnostic is available. |
| Intraday M1 head collection | Data | Existing `thericher-kis-paper-intraday-head` task | Independently owned next four-run sequence begins 2026-08-11 00:29 KST. Its post-close terminal remains the only candidate for the scoped causal reader. No manual duplicate collector. |
| D1 stability and quote-session lifecycle | Data / Execution | Existing scheduled observers | Each owns its next due time and reattaches only source-safe scoped evidence. Neither blocks the completed Tiingo integration or next ready objective. |
| Loopback Paper dashboard | Execution / Infra | Existing loopback service | Available as a credential-free operational surface; the Tiingo receipt has no execution consumer. |

## Current Bottleneck

Fresh, KIS-reconstructible causal input coverage remains the predictive-engine
bottleneck. The prior QQQ/SPY input is scoped `input_unavailable` because its
coverage is incomplete and provider decision-time availability/finality remain
unobserved. Paper lifecycle reliability has a separate ready proof path and
does not depend on resolving that prediction-input limitation.

## Blocked-Goal Alternatives

The current intraday observation objective has no foreground block: the
installed task owns its 2026-08-11 00:29 KST collection sequence and 06:20 KST
terminal. Original dependency order: owned collection -> terminal receipt ->
capture/availability bindings -> optional pair binding -> offline causal
reader. Until then, the task `next_due` is an owned fact, not a failure or an
orchestration wait.

| Recovery package | Owner / resource | Completion evidence | Strongest kill test / recovery |
| --- | --- | --- | --- |
| Reattach intraday terminal chain | Data / existing 2026-08-11 06:20 KST terminal | Exact terminal, capture, availability, and optional pair bindings through the existing reader. | Any missing binding yields scoped `input_unavailable`; do not duplicate collection. |
| Reattach D1 stability observation | Data / existing 23:15 KST observer | Its existing categorical source-safe receipt. | Missing or unavailable record remains local to D1 finality; leave predictive inputs unchanged. |
| Reattach next quote-session result | Execution / existing 2026-08-11 23:35 KST task | One fresh task-time-bound source-safe session and direct receipt when named. | No unique fresh receipt: preserve task `next_due`; never infer an outcome or resubmit. |

Claude challenge: `review_unavailable` because its CLI timed out; this is not
treated as agreement, a hold, or a change to the standing authority.

## Current Reversible Improvement

Tiingo IEX snapshot reattestation now preserves the pinned compressed artifact
hash while independently checking the exact canonical gzip payload. This removes
a Python/zlib cross-runtime encoding false negative without changing snapshot
bytes, provider scope, KIS behavior, or promotion conditions. The next
reversible focus is source-safe reattachment of the existing intraday terminal.

## Current Recovery Action

Execution closed the existing quote-session lifecycle offline: the owned
2026-08-10 receipt binds `canary_completed` to `cancelled / clean`, and the
reader, image-presence, and loopback health reattested without a network client
or broker call. The next recovery action is Data's existing intraday terminal;
any missing or unavailable evidence remains local to that input path.
