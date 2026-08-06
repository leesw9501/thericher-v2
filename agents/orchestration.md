# Codex Orchestration Stateboard (제품개발 총괄)

`AGENTS.md` owns policy and `NEXT_CODEX_GOAL.md` owns the company objective.
This is a current cross-lane projection, not a role queue or history ledger.
Git and external artifacts retain historic receipts and implementation evidence.

## Company Objective

`intraday-head-source-safe-collection-recovery-projection-v1` will extend the
existing exact-pointer reader with one hash-bound, same-run capture projection.
It turns the completed 06:20 KST `collection_exit_nonzero` observation into a
deterministic source-safe category without adding a KIS call, task, broker,
model, or data-qualification surface.

## Ready / Owned / Due

| Work | Owner | Resource | Current fact and next action |
| --- | --- | --- | --- |
| Exact 06:20 KST recovery | Data / Execution | Existing terminal and capture receipt | Completed: terminal is `recovery/collection_exit_nonzero`, capture binding is `verified/incomplete`, and both target categories are `rejected/minute_duplicate_conflict`; QQQ/v4 stages are `not_applicable`. |
| Collection recovery projection | Data | Existing exact-pointer/capture reader | Ready. Verify the terminal's hash-bound same-run receipt and emit only categorical target recovery without latest-artifact or mutable-index fallback. |
| Intraday M1 head collection | Data | Existing `thericher-kis-paper-intraday-head` task | Next owned invocation is 00:29 KST. No manual run or duplicate collector. |
| QQQ observed/provisional route | Data / Execution | Existing downstream profile service | Skipped on the 06:20 collection failure; no Paper lifecycle, fill, PnL, alpha, or model result follows. |
| SPY D1 stability observation | Data | Existing virtual-Paper task | First receipt is `stable`, not provider finality or consumer qualification. Its next owned observation is 2026-08-07 23:15 KST. |
| Quote-session lifecycle canary | Execution | Existing virtual-Paper task | The 2026-08-05 receipt reattaches as `cancelled/clean` and attribution-ineligible. Next owned opportunity is 2026-08-07 23:35 KST. |
| GPU allocation | Research Steward / Engine Research | RTX 4090 | No frozen input-qualified predictive campaign is ready. CPU preparation may continue; GPU stays unallocated. |

## Current Bottleneck

Fresh causal KIS-reconstructible input coverage remains the product bottleneck:
the exact QQQ/NAS and SPY/AMS M1 scopes contain only 21 shared complete
regular-session windows and decision-time availability remains `not_observed`.
The immediate engineering gap is narrower: a verified capture receipt already
contains the 06:20 duplicate-conflict category, but the compact terminal fact
currently exposes only the parent nonzero exit.

## Current Reversible Improvement

The terminal-capture chain already binds one immutable receipt. Reuse that
binding to project a strict source-safe collection category, rejecting any
hash/run/time/coverage mismatch rather than falling back to latest or mutable
state.

## Current Recovery Action

Data owns the existing 00:29 KST task invocation. Codex builds and verifies the
read-only recovery projection now, then reattaches only the next task's exact
source-safe terminal and capture evidence. Do not infer a broker, fill, PnL,
alpha, coverage qualification, or model result.
