# Codex Orchestration Stateboard (제품개발 총괄)

`AGENTS.md` owns policy and `NEXT_CODEX_GOAL.md` owns the company objective.
This is a current cross-lane projection, not a role queue or history ledger.
Git and external artifacts retain historic receipts and implementation evidence.

## Company Objective

`source-local-qqq-mtf-resampling-mechanics-v1` will advance the Data and Engine
loops with a frozen, CPU-only attestation of session-aligned M1/M5/M10/H1/H3
input geometry from the existing local QQQ/NAS catalog. It adds no KIS call,
task, broker, GPU campaign, model selection, or data-qualification surface.

## Ready / Owned / Due

| Work | Owner | Resource | Current fact and next action |
| --- | --- | --- | --- |
| Exact 06:20 KST recovery | Data / Execution | Existing terminal and capture receipt | Completed: terminal is `recovery/collection_exit_nonzero`, capture binding is `verified/incomplete`, and both target categories are `rejected/minute_duplicate_conflict`; QQQ/v4 stages are `not_applicable`. |
| Collection recovery projection | Data | Existing exact-pointer/capture reader | Completed. It requires `recovery/collection_exit_nonzero`, emits `rejected_duplicate_conflict` only for the exact verified capture chain, and otherwise emits `evidence_unavailable`. |
| Duplicate-conflict provenance | Data | Existing backfill result and session-capture contracts | Completed. Future exact receipts preserve collector-time conflict origin/disposition; historic missing fields are `not_recorded_legacy`, and partial/mixed/unknown future forms fail closed. |
| Intraday M1 head collection | Data | Existing `thericher-kis-paper-intraday-head` task | Next owned invocation is 2026-08-08 00:29 KST. No manual run or duplicate collector. |
| EMA source-local mechanics | Engine Research / Execution | Frozen QQQ/NAS 20-session catalog and existing local replay | Completed: the `20260807-ema-mechanics-r2` external replay is local-paper-only, replayable, and terminal-flat; it has no performance or promotion claim. |
| QQQ multi-timeframe resampling mechanics | Data / Engine Research | Same frozen QQQ/NAS M1 catalog and existing session resampler | Ready. Attest causal session-aligned M1/M5/M10/H1/H3 bucket geometry and fail closed on partial input; CPU only. |
| QQQ observed/provisional route | Data / Execution | Existing downstream profile service | Skipped on the 06:20 collection failure; no Paper lifecycle, fill, PnL, alpha, or model result follows. |
| SPY D1 stability observation | Data | Existing virtual-Paper task | First receipt is `stable`, not provider finality or consumer qualification. Its next owned observation is 2026-08-07 23:15 KST. |
| Quote-session lifecycle canary | Execution | Existing virtual-Paper task | The 2026-08-05 receipt reattaches as `cancelled/clean` and attribution-ineligible. Next owned opportunity is 2026-08-07 23:35 KST. |
| GPU allocation | Research Steward / Engine Research | RTX 4090 | No frozen input-qualified predictive campaign is ready. CPU preparation may continue; GPU stays unallocated. |

## Current Bottleneck

Fresh causal KIS-reconstructible input coverage remains the product bottleneck:
the exact QQQ/NAS and SPY/AMS M1 scopes contain only 21 shared complete
regular-session windows and decision-time availability remains `not_observed`.
The completed EMA replay proves one local execution seam only; the ready
independent work is to make every supported timeframe consume the same
completed-bar/session-boundary semantics before any model compares them.

## Current Reversible Improvement

Reuse the frozen source-local catalog and existing session resampler rather
than inventing a new multi-timeframe provider or model layer. Its receipt must
remain aggregate-only and fail closed on incomplete, partial-bucket, or
future-contaminated input.

## Current Recovery Action

Data owns the existing 2026-08-08 00:29 KST task invocation; its collector
image is already rebuilt. Data and Engine Research now attest the independent
multi-timeframe geometry package, then Data reattaches only the task's exact
source-safe terminal and capture evidence. Do not infer a broker, fill, PnL,
alpha, coverage qualification, or model result.
