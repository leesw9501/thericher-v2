# Codex Orchestration Stateboard (제품개발 총괄)

`AGENTS.md` owns policy and `NEXT_CODEX_GOAL.md` owns the company objective.
This is a current cross-lane projection, not a role queue or history ledger.
Git and external artifacts retain historic receipts and implementation evidence.

## Company Objective

`intraday-qqq-v4-scheduled-validation-observation-v1` will reattach one exact
task-owned QQQ v4 terminal/session/validation chain after the existing 06:20
KST invocation. It advances the data-to-Paper evidence loop without creating a
broker, model, scheduler, or data-qualification surface.

`intraday-head-capture-receipt-binding-v1` is implemented, independently
reviewed, and rebuilt into the existing collector image. Future task-owned
runs require an exact same-run capture binding; a missing fresh binding is
`recovery/session_capture_binding_unavailable`, while pre-change receipts
remain `legacy_unbound`. This proves provenance only, not data quality.

## Ready / Owned / Due

| Work | Owner | Resource | Current fact and next action |
| --- | --- | --- | --- |
| QQQ v4 validation observation | Data / Execution | Existing offline validator and profile service | Ready. The v4 validator emits top-level `validated` status inside its immutable identity, preserving v3 evidence. Reattach one exact task-owned next receipt only. |
| Intraday M1 head collection | Data | Existing `thericher-kis-paper-intraday-head` task | 04:24 receipt is `recovery/prospective_validation_payload_unavailable` with collection `exit_zero` and QQQ `no_intent`. The task alone owns 06:20 KST; no manual run or duplicate collector. |
| QQQ observed/provisional route | Data / Execution | Existing downstream profile service | Exact current outcome is `no_intent`; no Paper lifecycle, fill, PnL, alpha, or model result follows. |
| SPY D1 stability observation | Data | Existing virtual-Paper task | First receipt is `stable`, not provider finality or consumer qualification. Its next owned observation is 2026-08-07 23:15 KST. |
| Quote-session lifecycle canary | Execution | Existing virtual-Paper task | The 2026-08-05 receipt reattaches as `cancelled/clean` and attribution-ineligible. Next owned opportunity is 2026-08-07 23:35 KST. |
| GPU allocation | Research Steward / Engine Research | RTX 4090 | No frozen input-qualified predictive campaign is ready. CPU preparation may continue; GPU stays unallocated. |

## Current Bottleneck

Fresh causal KIS-reconstructible input coverage remains the product bottleneck:
the exact QQQ/NAS and SPY/AMS M1 scopes contain only 21 shared complete
regular-session windows and decision-time availability remains `not_observed`.
The immediate observation is narrower: the next task-owned QQQ `no_intent`
must carry the v4 validation contract through the scheduler. It does not
qualify a model, campaign, GPU job, or Paper action.

## Current Reversible Improvement

The terminal-capture chain now distinguishes historical absence from a fresh
binding failure, and the validator now supplies the exact status consumed by
the scheduler in a new immutable namespace. Reattach only an explicit session,
offline and side-effect-free.

## Current Recovery Action

Data owns the existing 06:20 KST task invocation. Codex does not wait in the
foreground. If the task runs, reattach only its exact source-safe terminal,
session, validation, and capture-binding evidence; do not infer a broker, fill,
PnL, alpha, coverage, or model result.
