# Codex Orchestration Stateboard (제품개발 총괄)

`AGENTS.md` owns policy and `NEXT_CODEX_GOAL.md` owns the company objective.
This is a current cross-lane projection, not a role queue or history ledger.
Git and external artifacts retain historic receipts and implementation evidence.

## Company Objective

`intraday-qqq-offline-validation-reliability-v1` will make the existing
explicit-session QQQ validation produce one deterministic source-safe result
or a precise local recovery. It advances the data-to-Paper evidence loop
without creating a broker, model, or scheduling surface.

`intraday-head-capture-receipt-binding-v1` is implemented, independently
reviewed, and rebuilt into the existing collector image. Future task-owned
runs require an exact same-run capture binding; a missing fresh binding is
`recovery/session_capture_binding_unavailable`, while pre-change receipts
remain `legacy_unbound`. This proves provenance only, not data quality.

## Ready / Owned / Due

| Work | Owner | Resource | Current fact and next action |
| --- | --- | --- | --- |
| QQQ offline validation reliability | Data / Execution | Existing offline validator and profile service | Ready. Diagnose the exact 04:24 `no_intent` -> `validation unavailable` path using only source-safe evidence; repair deterministic local behavior and test it. |
| Intraday M1 head collection | Data | Existing `thericher-kis-paper-intraday-head` task | 04:24 receipt is `recovery/prospective_validation_payload_unavailable` with collection `exit_zero` and QQQ `no_intent`. The task alone owns 06:20 KST; no manual run or duplicate collector. |
| QQQ observed/provisional route | Data / Execution | Existing downstream profile service | Exact current outcome is `no_intent`; no Paper lifecycle, fill, PnL, alpha, or model result follows. |
| SPY D1 stability observation | Data | Existing virtual-Paper task | First receipt is `stable`, not provider finality or consumer qualification. Its next owned observation is 2026-08-07 23:15 KST. |
| Quote-session lifecycle canary | Execution | Existing virtual-Paper task | The 2026-08-05 receipt reattaches as `cancelled/clean` and attribution-ineligible. Next owned opportunity is 2026-08-07 23:35 KST. |
| GPU allocation | Research Steward / Engine Research | RTX 4090 | No frozen input-qualified predictive campaign is ready. CPU preparation may continue; GPU stays unallocated. |

## Current Bottleneck

Fresh causal KIS-reconstructible input coverage remains the product bottleneck:
the exact QQQ/NAS and SPY/AMS M1 scopes contain only 21 shared complete
regular-session windows and decision-time availability remains `not_observed`.
The immediate reversible blocker is narrower: a valid scheduled QQQ
`no_intent` has no deterministic offline validation receipt. Repairing it
does not qualify a model, campaign, GPU job, or Paper action.

## Current Reversible Improvement

The terminal-capture chain now distinguishes historical absence from a fresh
binding failure and verifies one deterministic external path rather than a
latest artifact. Keep the next repair similarly explicit-session, offline,
and side-effect-free.

## Current Recovery Action

Data owns the existing 06:20 KST task invocation. Codex continues the ready
offline-validation package rather than waiting in the foreground. If the task
runs, reattach only its exact source-safe terminal evidence and continue all
non-conflicting work; do not infer a broker, fill, PnL, alpha, coverage, or
model result.
