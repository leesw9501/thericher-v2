# Codex Orchestration Stateboard (제품개발 총괄)

`AGENTS.md` owns policy and `NEXT_CODEX_GOAL.md` owns the company objective.
This is a current cross-lane projection, not a role queue or history ledger.
Git and external artifacts retain historic receipts and implementation evidence.

## Company Objective

`task-owned-kis-intraday-causal-evidence-refresh-v1` will classify the next
caller-selected task-owned QQQ/NAS and SPY/AMS completed-session M1 evidence
chain as qualified or scoped `input_unavailable`. The 2026-08-08 terminal is
already closed as `input_unavailable`: its exact hash-bound capture has
`incomplete` cumulative coverage and no recorded decision-time availability or
provider-finality fact. The work must never manually call the KIS collector,
read `KIS_LIVE_*`, create an order, promote a model, or infer any of those
facts from a scheduler result alone.

## Ready / Owned / Due

| Work | Owner | Resource | Current fact and next action |
| --- | --- | --- | --- |
| Exact 2026-08-08 06:20 KST terminal | Data / Execution | Caller-selected terminal and bound capture receipt | Completed classification: the offline terminal reader returned `complete` with `verified/incomplete` coverage binding. This exact QQQ/NAS and SPY/AMS input is `input_unavailable`; it is not a data-quality, finality, model, Paper, fill, or PnL claim. |
| Collection recovery projection | Data | Existing exact-pointer/capture reader | Completed. It requires `recovery/collection_exit_nonzero`, emits `rejected_duplicate_conflict` only for the exact verified capture chain, and otherwise emits `evidence_unavailable`. |
| Duplicate-conflict provenance | Data | Existing backfill result and session-capture contracts | Completed. Future exact receipts preserve collector-time conflict origin/disposition; historic missing fields are `not_recorded_legacy`, and partial/mixed/unknown future forms fail closed. |
| Intraday M1 head collection | Data | Existing `thericher-kis-paper-intraday-head` task | Next owned invocation is 2026-08-11 00:29 KST. No manual run or duplicate collector. |
| Task-owned causal evidence binding | Data | Existing intraday-head task and its existing local-only pair service | Ready for the next owned invocation: one source-local availability receipt is bound by its contract/receipt/precommit/summary hashes, and a pair attempt is accepted only when its immutable contract matches all four. A matching chain still remains `input_unavailable` until decision-time availability and provider finality are observed. No new task, collector, broker route, or model/GPU appointment. |
| EMA source-local mechanics | Engine Research / Execution | Frozen QQQ/NAS 20-session catalog and existing local replay | Completed: the `20260807-ema-mechanics-r2` external replay is local-paper-only, replayable, and terminal-flat; it has no performance or promotion claim. |
| QQQ multi-timeframe resampling mechanics | Data / Engine Research | Frozen QQQ/NAS M1 catalog and existing session resampler | Completed: immutable `20260807-qqq-mtf-r1` records 20 session-aligned completed-bar inputs with M1/M5/M10/H1/H3 aggregate geometry; H1/H3 terminal 30-minute buckets are explicitly excluded. It is source-local CPU evidence only. |
| QQQ baseline causal MTF windows | Data / Engine Research | Completed `20260807-qqq-mtf-window-r3` receipt | Completed: the fixed M1=30/M5=6/M10=3/H1=2/H3=2 profile has 600/120/60/40/40 aggregate completed windows at 15:30 ET, with H1/H3 terminal partials excluded. Parent receipt hash and external-path integrity are verified. |
| QQQ causal MTF window matrix | Data / Engine Research | Completed `20260807-qqq-mtf-matrix-r2` receipt | Completed: all six canonical profiles are precommitted at 15:30 ET against the reattested 20-session QQQ/NAS input; every profile remains target-free and terminal-partial-safe. |
| EMA local-Paper PnL attribution | Engine Research / Execution | Completed fixed EMA replay and existing local-paper accounting | Completed: `20260807-ema-pnl-attribution-r1` reattested the parent and recorded 76 closed segments, 152 local-paper fills, gross `-26.299200`, fees `10.8932`, net `-37.192400`, zero open quantity, and exact replay parity. It is source-local accounting only. |
| M1 duplicate-conflict recovery | Data | Existing task-owned QQQ/NAS and SPY/AMS collector paths | Completed. `session-capture` now quarantines only immutable committed cursor-free heads; it preserves original manifest/raw bytes and rejects the conflict, then a later compatible task-owned capture appends once. Partial/cursor-backed and malformed inputs fail closed. The current terminal remains provenance-legacy. |
| IWM current-head ingestion | Data | Isolated IWM/AMS route and external market-data store | Completed: one current-day page was accepted at 2026-08-07 01:46 UTC, retained as an immutable source-local snapshot, and made no continuation request. QQQ/SPY state and schedule were untouched. |
| IWM source-local replayability | Data / Validation | Legacy IWM snapshot, v2 receipt writer, and existing `Bar`/resampler contracts | Completed: the historical v1 receipt lacks a snapshot identity, so exact local replay records `completion_evidence_unavailable` and zero completed buckets rather than inventing timing. The v2 writer/reader contract is tested with bound fixtures. |
| IWM v2 bound observation | Data / Execution | Isolated IWM/AMS KIS Paper one-page route | Completed: one accepted no-continuation page reused the immutable snapshot and wrote a v2 content-bound receipt. Local replay produced 120 complete M1, 8 M5, 1 M10, and no H1/H3 bucket. It has no consumer or promotion consequence. |
| IWM v2 observation selector | Data / Validation | Existing immutable IWM snapshots and v2 receipts | Completed: source-safe metadata can enumerate observations and caller-selected v2 replay has no mutable latest fallback. The independent order-versus-hash duplicate defect was fixed before integration. |
| IWM prospective observation append | Data / Validation | Isolated IWM/AMS route, immutable external roots, and completed selector | Completed: success receipts append separately from source-safe failure outcomes, stale owned stages cannot poison selection, and the collector returns an opaque selected ID. One bounded request reused the existing snapshot and reattached offline. |
| Alternate IWM collector WIP | Data | Existing IWM v2 append/selector owner | Rejected by independent audit: the untracked alternate route can mix receipt namespaces and relax the approved D: cache boundary. Do not stage or invoke it; retain the existing v2 owner for any later narrow improvement. |
| QQQ/SPY current-day M1 reach probe | Data | Named Paper minute endpoint, isolated external probe roots, and one reusable client | Completed: one blank-cursor current-day page per target was accepted and terminal with no recognized continuation. QQQ issued one token, SPY reused it, both made one minute GET, and no categorical failure occurred. This is exact-route evidence only; prior scope remains `unknown`. |
| QQQ/SPY explicit previous-day M1 scope probe | Data | Named Paper minute endpoint, isolated external probe roots, and one reusable client | Completed: one explicit-previous-day page per target was accepted and terminal with no recognized continuation or multi-date range. QQQ issued one token, SPY reused it, both made one minute GET, and no categorical failure occurred. This remains exact-route evidence only. |
| Donchian local-Paper PnL attribution | Engine Research / Execution | Frozen QQQ/NAS 20-session mechanics receipt and existing FIFO local simulator | Completed: `20260807-donchian-pnl-r1` reattested the parent, recorded 115 closed segments, 230 local-paper fills, gross `-41.984600`, fees `16.5045`, net `-58.489100`, zero open quantity, and exact replay parity. It remains a non-promoting retrospective baseline. |
| Private Paper operator dashboard | Execution / Infra | Existing KIS Paper read-only account contract and local emergency controls | Completed: Docker reattestation requires an explicit container exception, publishes only `127.0.0.1:8787`, renders unavailable facts explicitly, and UI pause/resume changes local state only. |
| Read-only Paper account snapshot refresh | Execution / Infra | Existing named bridge and dashboard snapshot reader | Completed: one actual `kis-readonly` refresh was categorical `complete`; its external receipt is fact-minimized and the loopback dashboard immediately read it as available. |
| Read-only Paper account observer | Execution / Infra | Existing one-shot bridge, 2026 session inspector, and task conventions | Completed: the caller-selected `20260807T141607347092Z-7c9fb50a-81bb-40a8-b72f-49b3e492d773-complete.json` sidecar reattached as `complete` at `2026-08-07T14:16:07Z` after its final bridge SHA-256 and marker/status/time binding passed. The credential-free loopback dashboard `/health` returned only `ok` and `broker_calls:false`. No account fact was inspected. This is marker-present provenance under the assumed-honest host, not cryptographic Scheduler-origin proof; Operational logging is disabled. The existing four-minute task remains sole read-only owner. |
| QQQ observed/provisional route | Data / Execution | Existing downstream profile service | Skipped on the 06:20 collection failure; no Paper lifecycle, fill, PnL, alpha, or model result follows. |
| SPY D1 stability observation | Data | Existing virtual-Paper task | The exact 2026-08-07 `d1-stability-20260807T141501Z-attempt-04-c5e2cd1a0693` receipt reattaches as `stable`: one unadjusted GET, zero retries/foreground wait, and provider finality `not_observed`. It is not provider-finality or consumer qualification. Next owned observation is 2026-08-10 23:15 KST. |
| Quote-session lifecycle canary | Execution | Existing virtual-Paper task | The exact 2026-08-07 session is `canary_completed/intent_recorded`; its direct lifecycle is `not_submitted/unresolved`, attribution unavailable, with no submit, fill, PnL, or model result. The 2026-08-05 `cancelled/clean` result remains historic. Next owned opportunity is 2026-08-10 23:35 KST; any new outcome needs its own source-safe receipt and offline validation. |
| GPU allocation | Research Steward / Engine Research | RTX 4090 | No frozen input-qualified predictive campaign is ready. The five legacy frozen custody records are terminally `non_promoting_abandoned` under the external reconciliation receipt; CPU preparation may continue and GPU stays unallocated. |
| MTF feature-schema expansion | Engine Research | Existing matrix, feasibility, and profiled-input contracts | Rejected as a duplicate target-free implementation. Reuse the existing owners; do not add a new feature-schema artifact path until a frozen predictive campaign needs it. |

## Current Bottleneck

Fresh causal KIS-reconstructible input coverage remains the product bottleneck:
the exact 2026-08-08 chain is explicitly `incomplete`, the QQQ/NAS and SPY/AMS
M1 scopes still have only 21 shared complete regular-session windows, both
bounded historical starting scopes are terminal, and decision-time availability
and provider finality remain `not_observed`. The existing task owns the next
forward observation. The fixed Donchian baseline is now accounted and negative,
so it cannot consume more research-selection effort; independent execution
observability can still improve Paper readiness without claiming model validity.

## Current Reversible Improvement

Do not wait for the task-owned collection. The existing Data task will
materialize one source-local historical availability receipt in its own run,
bind its four immutable hashes into the terminal, and bind any eligible pair
attempt to that same contract. An unavailable local receipt stays a scoped
`not_observed` result; a malformed receipt remains task-local recovery. This
does not add a scheduler, collector, broker route, or promotion path. Claude's
bounded drift-check timed out, so it is `review_unavailable`, not agreement.

## Current Recovery Action

Data owns the existing 2026-08-11 00:29 KST QQQ/SPY task invocation; it is the
only owner of a later actual KIS collection. The 2026-08-08 chain's bound
identities and hash are verified offline, while its incomplete coverage closes
only that exact input as `input_unavailable`. A conflicted, incomplete, late,
unbound, or availability-hash-mismatched later result remains scoped and is
never a global hold. Execution continues to own the installed observer cadence;
Infra is invoked only for existing Docker/task runtime. IWM current-head
success remains unrelated to historical M1 reach.
