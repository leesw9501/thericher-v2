# Codex Orchestration Stateboard (제품개발 총괄)

`AGENTS.md` owns policy and `NEXT_CODEX_GOAL.md` owns the company objective.
This is a current cross-lane projection, not a role queue or history ledger.
Git and external artifacts retain historic receipts and implementation evidence.

## Company Objective

`source-local-session-reset-ema-mechanics-v1` will advance the Engine Research
loop with a frozen, CPU-only local-paper mechanics replay of the existing pure
15/30 session-reset EMA rule. It adds no KIS call, task, broker, GPU campaign,
model selection, or data-qualification surface.

## Ready / Owned / Due

| Work | Owner | Resource | Current fact and next action |
| --- | --- | --- | --- |
| Exact 06:20 KST recovery | Data / Execution | Existing terminal and capture receipt | Completed: terminal is `recovery/collection_exit_nonzero`, capture binding is `verified/incomplete`, and both target categories are `rejected/minute_duplicate_conflict`; QQQ/v4 stages are `not_applicable`. |
| Collection recovery projection | Data | Existing exact-pointer/capture reader | Completed. It requires `recovery/collection_exit_nonzero`, emits `rejected_duplicate_conflict` only for the exact verified capture chain, and otherwise emits `evidence_unavailable`. |
| Duplicate-conflict provenance | Data | Existing backfill result and session-capture contracts | Completed. Future exact receipts preserve collector-time conflict origin/disposition; historic missing fields are `not_recorded_legacy`, and partial/mixed/unknown future forms fail closed. |
| Intraday M1 head collection | Data | Existing `thericher-kis-paper-intraday-head` task | Next owned invocation is 2026-08-08 00:29 KST. No manual run or duplicate collector. |
| EMA source-local mechanics | Engine Research | Frozen QQQ/NAS 20-session catalog and existing local replay | Ready. Build one causal 15/30 session-reset mechanics replay with terminal-flat and future-prefix kill tests; CPU only. |
| QQQ observed/provisional route | Data / Execution | Existing downstream profile service | Skipped on the 06:20 collection failure; no Paper lifecycle, fill, PnL, alpha, or model result follows. |
| SPY D1 stability observation | Data | Existing virtual-Paper task | First receipt is `stable`, not provider finality or consumer qualification. Its next owned observation is 2026-08-07 23:15 KST. |
| Quote-session lifecycle canary | Execution | Existing virtual-Paper task | The 2026-08-05 receipt reattaches as `cancelled/clean` and attribution-ineligible. Next owned opportunity is 2026-08-07 23:35 KST. |
| GPU allocation | Research Steward / Engine Research | RTX 4090 | No frozen input-qualified predictive campaign is ready. CPU preparation may continue; GPU stays unallocated. |

## Current Bottleneck

Fresh causal KIS-reconstructible input coverage remains the product bottleneck:
the exact QQQ/NAS and SPY/AMS M1 scopes contain only 21 shared complete
regular-session windows and decision-time availability remains `not_observed`.
The Data recovery contract now has exact collector-time provenance, while the
ready independent work is to prove the existing EMA rule's causal local replay
mechanics without misrepresenting it as predictive evidence.

## Current Reversible Improvement

Reuse the frozen source-local catalog and existing local-paper seam for a
single EMA mechanics module rather than opening a new model family or GPU job.
Its receipt must remain aggregate-only and fail closed on incomplete or
future-contaminated input.

## Current Recovery Action

Data owns the existing 2026-08-08 00:29 KST task invocation; its collector
image is already rebuilt. Engine Research builds the independent EMA mechanics
package now, then Data reattaches only the task's exact source-safe terminal
and capture evidence. Do not infer a broker, fill, PnL, alpha, coverage
qualification, or model result.
