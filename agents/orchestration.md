# Codex Orchestration Stateboard (제품개발 총괄)

`AGENTS.md` owns policy and `NEXT_CODEX_GOAL.md` owns the company objective.
This is a current cross-lane projection, not a queue or history ledger. Git and
external source-safe receipts retain completed evidence.

## Company Objective

`firstrate-source-local-timeframe-mechanics-v1` follows the completed FirstRate
normalization. It consumes only the two hash-bound canonical FirstRate SPY/QQQ
M1 files through the existing 1m/5m/10m/1h/3h resampler and records aggregate
geometry. It is retrospective Data mechanics only: no densification, KIS join,
availability/finality claim, strategy, PnL, Paper action, or live route.

## Ready / Owned / Due

| Work | Owner | Resource | Current fact and next action |
| --- | --- | --- | --- |
| Tiingo IEX r1 integration | Data / Engine Research | Immutable r1 snapshot and external artifact root | Closed: host and container reattested the same raw, manifest, gzip, and canonical payload identities. CPU and CUDA fixed matrices completed; only categorical completion and cleanup receipts exist. |
| FirstRate free M1 normalization | Data | Hash-bound external ZIPs, canonical CSVs, and source-safe receipt | Closed: archive hashes, expected entries, strict decode, canonical hashes, and exact timestamp-set equality reattached. Local provider round-trip counts are 207,824 SPY and 210,482 QQQ M1 Bars. |
| FirstRate source-local timeframe mechanics | Data / Codex | Existing local provider/resampler and immutable normalization receipt | Ready: create an aggregate 1m/5m/10m/1h/3h geometry manifest with no generated bars, filling, coverage inference, or research/execution consumer. |
| GPU custody | Research Steward | RTX 4090 | Released: one source-isolated target-free appointment spent no sealed evaluation and retained no weights. No predictive GPU appointment is active. |
| KIS Paper lifecycle canary | Execution | Existing `thericher-kis-paper-quote-session` task | The 2026-08-17 23:35 KST receipt is bound offline to its direct receipt as `canary_completed -> cancelled / clean`, `paper_only`, and attribution `not_eligible`; the direct receipt contains only an acknowledged order-reference category. The 2026-08-11 unknown remains separately owned by its reconciliation path. No manual task, container, duplicate submission, fill, PnL, or model inference. Next task-owned opportunity: 2026-08-19 23:35 KST. |
| Norgate local readiness | Data | Existing NDU updater | The 2026-08-14 provisioned-host reader returned `local_api_not_ready` and wrote no receipt. It does not establish a process, update, subscription, expiry, vendor-access, or rights cause. This does not block the Paper canary. The one operator-visible diagnostic is the already-running NDU update plus database/subscription-state panes, then minimize it. |
| Intraday M1 coverage | Data | Existing task image and source-safe terminal projection | The 2026-08-17 task-owned terminal reattached as `complete` with verified coverage/availability bindings, matching the 2026-08-15 `input_unavailable/session_coverage_incomplete/current_session_short` topology. The new writer leaves it unbound by default. |
| Capture topology and markers | Data / Codex | Existing task, cache metadata, external artifact root | The first post-writer marker is one comparable `collection_exit_nonzero / reason_unavailable` binding. The later hash-bound marker is successful but `retained_partial`, so its default category is noncomparable. No recovery proposal exists. |
| D1 stability and quote-session lifecycle | Data / Execution | Existing scheduled observers | Each owns its next due time and reattaches only source-safe scoped evidence. Neither blocks the completed Tiingo integration or next ready objective. |
| Loopback Paper dashboard | Execution / Infra | Existing loopback service | Available as a credential-free operational surface; the Tiingo receipt has no execution consumer. |

## Current Bottleneck

Fresh, KIS-reconstructible causal input coverage remains the predictive-engine
bottleneck. The first post-writer task path has one comparable
`reason_unavailable` nonzero category, while the later terminal is successful
but `retained_partial`; its default category is noncomparable. Coverage remains
`incomplete/current_session_short`, decision-time availability and provider
finality are unobserved, and no model input exists. Paper lifecycle reliability
has a separate proof path and does not depend on resolving this Data diagnosis.

## Current Cross-Lane Decision

The topology audit rejected an unmeasured timing/paging/downstream change. The
first post-writer marker supplies one closed `reason_unavailable` category for a
task-stage nonzero, not a capture cause. The later successful partial terminal
does not supply a second category. The diagnostic preserves the original nonzero
and has no free-text exception/log path. Separately, FirstRate canonical M1
output is usable only as source-isolated mechanics, not a qualified input. This
does not qualify research input or change Paper behavior.

## Current Reversible Improvement

The FirstRate batch normalizer reattests each staged ZIP, rejects unexpected
archive shape/time semantics, and proves the emitted canonical timestamp set
equals the decoded source set before writing a source-safe receipt. It adds a
real local 1m data path without treating omitted source minutes as gaps or
promoting the data to a KIS/Paper/model consumer.

## Current Recovery Action

No category-based recovery proposal is active. A later recovery investigation
would need two independently hash-validated matching *comparable* nonzero
bindings plus a fresh Claude falsification-first verdict. The current next
action is the independent FirstRate source-local timeframe mechanics package;
it needs no Task or foreground wait.
