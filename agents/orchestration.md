# Codex Orchestration Stateboard (제품개발 총괄)

`AGENTS.md` owns policy and `NEXT_CODEX_GOAL.md` owns the company objective.
This is a current cross-lane projection, not a role queue or history ledger.
Git and external artifacts retain historic receipts and implementation evidence.

## Company Objective

`iwm-m1-prospective-observation-append-v1` will make repeated IWM current-head
observations append-safe. It preserves explicit selection and immutable
snapshot/receipt identity, keeps the exact QQQ/SPY task unchanged, and adds no
historical pagination, account/order route, model, Paper input, qualification,
live-capital surface, or public service.

## Ready / Owned / Due

| Work | Owner | Resource | Current fact and next action |
| --- | --- | --- | --- |
| Exact 06:20 KST recovery | Data / Execution | Existing terminal and capture receipt | Completed: terminal is `recovery/collection_exit_nonzero`, capture binding is `verified/incomplete`, and both target categories are `rejected/minute_duplicate_conflict`; QQQ/v4 stages are `not_applicable`. |
| Collection recovery projection | Data | Existing exact-pointer/capture reader | Completed. It requires `recovery/collection_exit_nonzero`, emits `rejected_duplicate_conflict` only for the exact verified capture chain, and otherwise emits `evidence_unavailable`. |
| Duplicate-conflict provenance | Data | Existing backfill result and session-capture contracts | Completed. Future exact receipts preserve collector-time conflict origin/disposition; historic missing fields are `not_recorded_legacy`, and partial/mixed/unknown future forms fail closed. |
| Intraday M1 head collection | Data | Existing `thericher-kis-paper-intraday-head` task | Next owned invocation is 2026-08-08 00:29 KST. No manual run or duplicate collector. |
| EMA source-local mechanics | Engine Research / Execution | Frozen QQQ/NAS 20-session catalog and existing local replay | Completed: the `20260807-ema-mechanics-r2` external replay is local-paper-only, replayable, and terminal-flat; it has no performance or promotion claim. |
| QQQ multi-timeframe resampling mechanics | Data / Engine Research | Frozen QQQ/NAS M1 catalog and existing session resampler | Completed: immutable `20260807-qqq-mtf-r1` records 20 session-aligned completed-bar inputs with M1/M5/M10/H1/H3 aggregate geometry; H1/H3 terminal 30-minute buckets are explicitly excluded. It is source-local CPU evidence only. |
| QQQ baseline causal MTF windows | Data / Engine Research | Completed `20260807-qqq-mtf-window-r3` receipt | Completed: the fixed M1=30/M5=6/M10=3/H1=2/H3=2 profile has 600/120/60/40/40 aggregate completed windows at 15:30 ET, with H1/H3 terminal partials excluded. Parent receipt hash and external-path integrity are verified. |
| QQQ causal MTF window matrix | Data / Engine Research | Completed `20260807-qqq-mtf-matrix-r2` receipt | Completed: all six canonical profiles are precommitted at 15:30 ET against the reattested 20-session QQQ/NAS input; every profile remains target-free and terminal-partial-safe. |
| EMA local-Paper PnL attribution | Engine Research / Execution | Completed fixed EMA replay and existing local-paper accounting | Completed: `20260807-ema-pnl-attribution-r1` reattested the parent and recorded 76 closed segments, 152 local-paper fills, gross `-26.299200`, fees `10.8932`, net `-37.192400`, zero open quantity, and exact replay parity. It is source-local accounting only. |
| M1 duplicate-conflict recovery | Data | Existing task-owned QQQ/NAS and SPY/AMS collector paths | Completed. The scheduled `session-capture` preserve branch was reattested with a fake-client restart regression: repeat retained-cache conflicts leave the active chunk, manifest/raw bytes, head cursor, and snapshot count unchanged. The current terminal remains provenance-legacy. |
| IWM current-head ingestion | Data | Isolated IWM/AMS route and external market-data store | Completed: one current-day page was accepted at 2026-08-07 01:46 UTC, retained as an immutable source-local snapshot, and made no continuation request. QQQ/SPY state and schedule were untouched. |
| IWM source-local replayability | Data / Validation | Legacy IWM snapshot, v2 receipt writer, and existing `Bar`/resampler contracts | Completed: the historical v1 receipt lacks a snapshot identity, so exact local replay records `completion_evidence_unavailable` and zero completed buckets rather than inventing timing. The v2 writer/reader contract is tested with bound fixtures. |
| IWM v2 bound observation | Data / Execution | Isolated IWM/AMS KIS Paper one-page route | Completed: one accepted no-continuation page reused the immutable snapshot and wrote a v2 content-bound receipt. Local replay produced 120 complete M1, 8 M5, 1 M10, and no H1/H3 bucket. It has no consumer or promotion consequence. |
| IWM v2 observation selector | Data / Validation | Existing immutable IWM snapshots and v2 receipts | Completed: source-safe metadata can enumerate observations and caller-selected v2 replay has no mutable latest fallback. The independent order-versus-hash duplicate defect was fixed before integration. |
| IWM prospective observation append | Data | Isolated IWM/AMS current-head route, immutable external roots, and completed selector | Ready: freeze and test same-content reuse, changed-head isolation, receipt atomicity, and restart behavior before one bounded KIS Paper observation attempt. This is not historical paging. |
| QQQ observed/provisional route | Data / Execution | Existing downstream profile service | Skipped on the 06:20 collection failure; no Paper lifecycle, fill, PnL, alpha, or model result follows. |
| SPY D1 stability observation | Data | Existing virtual-Paper task | First receipt is `stable`, not provider finality or consumer qualification. Its next owned observation is 2026-08-07 23:15 KST. |
| Quote-session lifecycle canary | Execution | Existing virtual-Paper task | The 2026-08-05 receipt reattaches as `cancelled/clean` and attribution-ineligible. Next owned opportunity is 2026-08-07 23:35 KST. |
| GPU allocation | Research Steward / Engine Research | RTX 4090 | No frozen input-qualified predictive campaign is ready. CPU preparation may continue; GPU stays unallocated. |

## Current Bottleneck

Fresh causal KIS-reconstructible input coverage remains the product bottleneck:
the exact QQQ/NAS and SPY/AMS M1 scopes contain only 21 shared complete
regular-session windows, decision-time availability remains `not_observed`, and
the current-head worker's exact latest terminal is
`rejected/minute_duplicate_conflict`. The completed EMA attribution is a
negative source-local accounting baseline; it neither overcomes this input gap
nor warrants extending the strategy.

## Current Reversible Improvement

Use the completed explicit selector to make a small IWM append contract safe:
reuse identical immutable content, isolate changed heads, and keep every
receipt caller-selectable without a mutable latest-record policy or QQQ/SPY
impact.

## Current Recovery Action

Data owns the existing 2026-08-08 00:29 KST QQQ/SPY task invocation and the
bounded IWM append package. Its first recovery decision is exact and local:
reuse an identical snapshot, preserve a changed head as a distinct immutable
observation, or write only a source-safe failure fact. Historical M1 reach
remains a separate endpoint probe, never an inference from IWM current-head
success.
