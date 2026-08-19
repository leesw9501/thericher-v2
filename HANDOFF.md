# TheRicher v2 Handoff

## Product Direction

TheRicher v2 is a private, reproducible U.S.-equity research and KIS Paper
engine. Its product loop is causal market data -> frozen research contract ->
backtest/walk-forward evidence -> local-paper replay -> KIS Paper execution
evidence -> PnL attribution. KIS Paper is early execution evidence, not a
reward for a profitable model. `KIS_LIVE_*` is unavailable.

`AGENTS.md` owns policy. `NEXT_CODEX_GOAL.md` owns the one active company
objective. The stateboards are concise current projections only; Git and
immutable external artifacts retain history.

## Active Company Objective

The completed `kis-intraday-short-session-topology-classification-v1` classified
the bound 2026-08-15 terminal as `current_session_short` solely from source-safe
metadata. The completed `kis-intraday-next-terminal-reattachment-v1` reattached
the later 2026-08-17 terminal through the same projection and found the same
scoped category. The completed
`kis-intraday-causal-attestation-writer-integration-v1` added a networkless,
default-deny future writer with no current task or terminal change. Its
real-artifact smoke returned `not_written/session_coverage_incomplete` for the
current terminal. The next objective,
`kis-intraday-full-session-capture-recovery-v1` completed a metadata-only
topology audit and installed a diagnostic-only invocation receipt path in the
existing dispatcher. The completed
`kis-intraday-invocation-receipt-reattachment-v1` reattached the first later
task-owned marker and found one exact task-stage nonzero without a root-cause
claim. The next objective, `kis-intraday-task-path-failure-localization-v1`,
installed only a closed source-safe reason classification for future task-owned
nonzero runs. The next objective,
`kis-intraday-failure-category-reattachment-v1`, reattached the first
post-writer task-owned marker as one closed `reason_unavailable` category
binding. The completed `kis-intraday-failure-category-confirmation-v1`
reattached a strictly later terminal as
`retained_partial/current_session_not_complete` with a successful collection
outcome. Its compatibility-default `reason_unavailable` is explicitly
noncomparable, so it is neither a second category binding nor a divergence.
No recovery proposal followed. The completed
`firstrate-source-local-normalization-v1` reattached and normalized the two
hash-bound free SPY/QQQ M1 archives into canonical local Bars with exact
decoded/emitted timestamp-set equality. The next objective,
`firstrate-source-local-timeframe-mechanics-v1`, proved their existing local
1m/5m/10m/1h/3h UTC-anchored resampling geometry without persisting resampled
rows. The next objective, `firstrate-source-local-window-preflight-v1`, freezes
target-free, source-local feature-window geometry only; it remains never a
KIS/Paper/model input. The completed window preflight reattached that geometry
into a fixed 32-cell count/hash matrix with no raw rows, features, labels,
predictions, weights, model, GPU, KIS, or Paper consumer. The next objective,
`firstrate-source-semantics-retrieval-v1`, is a primary-source-only check of
timestamp and omission semantics; it cannot itself promote the source. It
completed with a hash-bound, review-limited interpretation: the vendor labels
US Eastern/New York time and declares zero-volume omission, while offset
convention and bar boundary remain `not_disclosed`. The next objective,
`norgate-trial-d1-capability-reprobe-v1`, made one host-only local invocation
after updater work but yielded no parseable source-safe output or task-owned
receipt. The next objective, `norgate-host-readiness-bridge-v1`, separates
runtime/API/catalog/root diagnostics from raw-data capability reads. It
completed with one hash-bound receipt: the isolated host runtime is available,
but the local API is `not_ready`, leaving catalog, update metadata, and active
root `not_checked`. No raw Norgate data was read; no trial capability, updater,
subscription, or rights conclusion follows. The completed source-safe
market-data contract inventory wrote one immutable receipt for all six fixed
classes: three `input_unavailable` entries (KIS M1, KIS D1, Norgate trial), one
FirstRate source-local-mechanics entry, one Tiingo D1 retrospective-control
entry, and one Tiingo IEX runtime-only entry. It qualifies no predictive,
Paper, or GPU consumer. The next objective is later task-owned intraday-terminal
reattachment, not a Norgate retry or a duplicate collector run.

The completed Tiingo IEX r1 source-isolated integration reattested the pinned
M5 snapshot in both host and Docker runtime. A gzip encoder difference was
resolved by preserving the pinned compressed hash and comparing exact canonical
payloads rebuilt from attested raw sources. Its CPU and single CUDA matrices
completed with categorical finite-run and memory-cleanup evidence; no weights,
loss values, predictions, returns, holdout, selection, KIS input, or Paper
input were created. Receipts remain external under
`D:\thericher-v2\model-artifacts\research\tiingo-iex-r1-representation-integration-v1`.

The task-owned 2026-08-17 06:20 KST terminal reattached offline as `complete`,
with verified coverage and availability bindings. Like the 2026-08-15 baseline,
its cumulative current-session coverage is `incomplete/current_session_short`,
the optional pair binding is `legacy_unbound`, and the exact causal input remains
`input_unavailable/session_coverage_incomplete`.
The causal attestation is `not_recorded`; decision-time availability and
provider finality remain `not_observed`. This is a scoped Data limitation,
never a hold on the Paper canary or another ready lane.

The offline diagnosis found a narrow aggregation defect: an identical row first
retained while still forming could remain incomplete even when a later retained
copy was after the bar close. Coverage now promotes only an identical later row
to complete; conflicting fingerprints and candidate-batch exclusions remain
unchanged. A metadata-only re-evaluation of the current cache still reports the
current session as short, so the immutable terminal receipt remains
`input_unavailable`; no prior receipt, provider-finality fact, model input, or
Paper behavior changed.

The private NAS D1 history-panel builder and historical-forward projection now
check their nonempty derived common-session spans against pinned local
`pandas-market-calendars==5.4.0` `NASDAQ` alias (`NYSE` calendar) sessions and
reject an interior scheduled-session omission before indexed features or labels
can bridge it. The check preserves weekends, holidays, and early-close sessions
and uses no provider or credential. A forward cache can still retain later raw
rows across a gap, but its prospective input stays `input_unavailable` until
the complete boundary-to-forward session chain is present. This package did not
read or reattest the current raw D1 cache, so it does not claim that cache has
passed the new condition or that finality, adjustments, PIT scope, or
predictive/Paper eligibility improved.

The topology audit found retained 120-minute-style chunks at all four expected
ET slots, but the retained set is sparse and no observed session is complete.
For the latest audited session, only the first slot was retained with 119
complete minutes. Static Scheduler facts are `Ready`, enabled, one action, and
four triggers; Operational logging is disabled, so missing retained chunks do
not prove missed triggers. Claude's falsification-first verdict was
`unsupported` for changing timing, paging, or downstream consumers from this
evidence alone.

The existing host dispatcher writes an immutable, source-safe `started` marker
before collection and a hash-bound `terminal` marker after its existing schedule
receipt. The first fresh marker reattached the exact 2026-08-19 KST run
`intraday-head-20260818T1728005721271Z`: its start, schedule-observed, and
dispatcher-completion timestamps bind to a `recovery` terminal with exit code
`1` and `collection_exit_nonzero`. This is one exact task-path nonzero, not
proof that a collector process started or that Docker, provider, persistence,
or timing caused it. It changes neither the Task definition nor any collector,
KIS, Paper, or downstream-consumer behavior. The provenance remains
assumed-honest-host, not cryptographic proof of Scheduler origin.

The terminal writer now accepts only `reason_unavailable`,
`dispatcher_config`, or `collector_provider`, derived in memory from one exact
existing collector error-payload shape. It preserves the original collection
exit code, never retains output or exception text, and rejects a category for a
zero collection exit. The current bound marker predates this schema and the
offline reader reattached it as `reason_unavailable` without modifying its
bytes. Claude's latest scope-matched challenge returned `review_unavailable`
because the service was overloaded; it is not a verdict or authority to change
collection behavior.

The first post-writer marker reattached the exact 2026-08-19 KST run
`intraday-head-20260818T1924006306454Z`. Its source-safe start,
schedule-observed, and completion timestamps bind an existing `recovery`
terminal with exit code `1`, `collection_exit_nonzero`, and the closed category
`reason_unavailable`. Its hash-bound terminal and schedule pointers remain
external-root-relative. This is one diagnostic binding only: it does not prove
a collector, provider, Docker, persistence, Scheduler, or pacing cause and
does not authorize a behavior change.

The offline reattachment reader now accepts an optional paired opaque baseline
run ID and completion timestamp. With the first post-writer marker as that
baseline, the unchanged current pointer classifies as `marker_not_later`; a
later category comparison therefore cannot accidentally count a reread marker
as independent evidence. This is source-safe reader behavior only and changes
no Task, collector, KIS, Docker, consumer, or Paper path.

The first strictly later marker is
`intraday-head-20260818T2120005941479Z`. Its hash-bound terminal and exact
schedule receipt reattach as `retained_partial/current_session_not_complete`
with `collection_outcome: succeeded`,
`collection_failure_category: reason_unavailable`, and
`failure_category_is_comparable: false`; topology remains
`current_metadata_consistent` for session date `2026-08-18`. The source-safe
terminal and schedule hashes are
`sha256:cf3b6983308630167f97962317aa3f89e7d96eb0f66beb2d6a9dd186c4a558ad`
and `sha256:c18b5024a7a058541e6d81757bb30405381451bfdee7b5aad576be5380d349a2`,
with pointers
`execution/kis-paper-intraday-head-invocation-v1/intraday-head-20260818T2120005941479Z/terminal.json`
and `execution/kis-paper-intraday-head-schedule/intraday-head-20260818T2120005941479Z.json`.
The category is a writer compatibility default for a successful collection
stage, not failure evidence. Marker provenance remains assumed-honest-host,
not cryptographic proof of Scheduler origin; Task Scheduler Operational logging
is disabled.

The completed FirstRate normalizer verified the staged archive hashes, expected
entry names, strict source timestamps, an explicit DST-aware New York-to-UTC
conversion assumption, and exact decoded/emitted timestamp-set equality. It wrote canonical CSVs beneath
`D:\market_data\us_equities\firstrate_free_intraday\canonical` and the
source-safe receipt
`D:\thericher-v2\model-artifacts\data-receipts\firstrate-free-intraday\firstrate-free-intraday-source-local-normalization-v1.json`
(`sha256:374fc885b831b6a2aea59526e25f918ebe568414b018b621452c02d608f988be`).
The standard local provider re-read 207,824 SPY and 210,482 QQQ complete M1
Bars with receipt-matching timestamp sets. This records source-local mechanics
only: no reindex/fill, session-coverage, KIS parity, decision-time availability,
provider finality, model, Paper, PnL, or live claim follows.

The completed FirstRate timeframe-mechanics run reattached both canonical input
hashes, loaded them through `LocalCsvBarProvider`, and retained only
source-safe 1m/5m/10m/1h/3h aggregate hashes/counts. It verified every emitted
bar's UTC ordering, complete flag, source-start timestamp, and OHLCV aggregation
from a complete unique contiguous observed-minute bucket. Its immutable manifest
is
`D:\thericher-v2\model-artifacts\data-receipts\firstrate-free-intraday\firstrate-free-intraday-source-local-timeframe-mechanics-v1.json`
(`sha256:aa83961f57f7fe373f9383874c3d294384dca895115ad7f447fb2371ec2528c3`).
The bucket anchor is UTC epoch, not a U.S. regular-session boundary; absent
source buckets are only `not_emitted_from_observed_source_set`, never market
gaps, zero-volume bars, session completeness, availability, finality, model, or
Paper evidence.

The completed FirstRate target-free window preflight reattached both immutable
parent receipts and canonical input hashes, recomputed the exact five
timeframes, and retained only the predeclared 32-cell window matrix, each
eligible count, and end-timestamp-set hash. Its immutable manifest is
`D:\thericher-v2\model-artifacts\data-receipts\firstrate-free-intraday\firstrate-free-intraday-source-local-window-preflight-v1.json`
(`sha256:eb88b4a441541cc1adbd55be781267d4990fce743b89109d610ff82be3904987`).
Eligibility means only complete in-memory Bars with adjacent starts exactly one
declared timeframe apart; it does not bridge, fill, establish a market/session
gap, or choose a model. Claude's scope-matched review rejected a follow-on GPU
representation study as `unsupported`: without verified source time semantics
or a decision-carrying artifact it would be a runtime benchmark, not research.
GPU custody remains free.

The completed FirstRate source-semantics package re-retrieved the official free
data and license pages twice each with matching content hashes, without market
data, credentials, KIS, broker, model, or GPU access. Its immutable source
receipt is
`D:\thericher-v2\model-artifacts\data-receipts\firstrate-free-intraday\firstrate-source-semantics-retrieval-v1.json`
(`sha256:81954bfd6fde980dd63af92fafb6471830742cbb6871b9bdaf21c9ea6c81063f`).
The attached review-limited interpretation is
`D:\thericher-v2\model-artifacts\data-receipts\firstrate-free-intraday\firstrate-source-semantics-interpretation-v1.json`
(`sha256:055b4faa5b83dc85255eeacd84eb59db762992250fcb18eb5285bcf0de4d37e2`).
It confirms only vendor-declared timezone label/zero-volume omission and a
conservative private-internal/no-redistribution project policy. It explicitly
preserves fixed-offset versus DST conversion and source bar boundary as
`not_disclosed`; no cross-feed alignment, completeness, KIS, model, Paper, or
live claim follows.

## Current Cross-Lane Facts

| Lane | Current fact | Next valid action |
| --- | --- | --- |
| Data / Engine Research | The fixed six-class inventory is reattached at `data-receipts/market-data-contract-inventory/market-data-contract-inventory-20260819-r1.json` (`sha256:17f2b0f7cf7e16a61b2c2006e806d6e9c8e6135d41e63bf073fe4cdd2fb55632`). Its counts are unavailable 3, mechanics-only 1, retrospective-control-only 1, and runtime-only 1; no predictive/Paper/GPU consumer is eligible. | Reattach only the first strictly later task-owned intraday terminal. Do not use a repeated pointer, task exit, or inventory status as a causal or broker result. |
| Data | The completed isolated Norgate bridge is `input_unavailable/local_api_not_ready`; host runtime is `available`, while catalog/update/root remain `not_checked`. Its receipt is `data-receipts/norgate-host-readiness-bridge/bridge-norgate-host-readiness-20260818T230439Z.json` (`sha256:20cf9e2954bb567fa31a54d58cde6d61b50be0d86b4b345261e14136c1aa521c`). | Do not repeat the daily probe or infer an updater/subscription/rights cause. No `ready/one` result exists, so no later Norgate capability goal is ready. |
| Engine Research | The Tiingo IEX r1 source-isolated CPU/CUDA runtime matrix is closed with no retained weights or predictive interpretation. A synthetic caller-owned local-paper two-step replay proves future policy-environment stepping against owned cost/fill semantics only. The pure source-attested selection-policy cycle now preserves candidate selection, per-symbol policy, and same-snapshot allocated targets as separate layers; Claude returned `supported-with-limits` for its frozen-context, fail-closed contract. A selected result must now replay the whole supplied selection, policy, and allocation cycle from original inputs and frozen configs before it receives a receipt-compatible opaque lineage reference. Persistent campaign replays reject exact partial JSONL/SQLite/emergency paths, including SQLite sidecars. Candidate replay and comparison now also reject existing exact output artifacts before any runner or baseline write, preserving same-run evidence; Claude's `supported-with-limits` review exposed a stale-baseline-delete interaction and narrowed the fix. | It has no data, score generation, training, reservation, execution, or Paper authority. Cohort lineage proves neither a complete universe nor predictive score or Execution correctness; it binds only the supplied aligned field and exact deterministic downstream replay. When no completed validation artifact exists, the explicit `discard_partial_campaign_replay` recovery removes only those exact regular partial files and preserves unrelated work-directory content; it never removes an artifact or directory. Candidate replay/comparison output concurrency remains owned by their job runner. No candidate, training, GPU appointment, or Paper input follows; any predictive campaign must separately freeze its ranking key, K, turnover, capacity, correlation, costs, and qualified input. |
| Research Steward | RTX 4090 is free after the completed Tiingo IEX r1 source-isolated appointment; no sealed evaluation was spent. | Allocate only a fresh frozen eligible campaign; never manufacture training to fill GPU time. |
| Execution | The 2026-08-17 23:35 KST owned quote-session receipt reattached offline as `canary_completed -> cancelled / clean`, `paper_only`, with attribution `not_eligible`; the bound direct lifecycle receipt records only an acknowledged order-reference category. The broker-free event replay additionally has a strict FIFO decision-PnL projection that binds valid local fills to accepted local orders and retains entry/exit decision roles plus pair totals. Its pure receipt resolver attaches only exact opaque receipt lineage and fails closed on missing, duplicate, role, or instrument mismatch. The earlier 2026-08-11 `outcome_unknown / unresolved` remains its own exact-run reconciliation fact. | The exact KIS run proves neither a fill, PnL, alpha, nor model result. The local projection is only arithmetic provenance, not broker PnL or causal credit. Do not resubmit either durable intent; their existing reconciliation paths remain the only owners. |
| Shared worktree | Alternate IWM collector WIP is untracked/modified and rejected from this objective. | Do not touch, stage, invoke, or reconcile it without a separate assignment. |

## Ready / Owned / Due

| Work | Owner | Status |
| --- | --- | --- |
| Invocation receipt reattachment | Data / Codex | Complete: the exact fresh marker, terminal, and schedule receipt bind a `collection_exit_nonzero` task stage. Its external evidence pointers are `execution/kis-paper-intraday-head-invocation-v1/intraday-head-20260818T1728005721271Z/terminal.json` and `execution/kis-paper-intraday-head-schedule/intraday-head-20260818T1728005721271Z.json`. |
| Task-path failure localization | Data / Codex | Complete: one closed, free-text-free category writer and legacy-compatible offline reader preserve the stage exit code. No timing/page/task/consumer change followed. |
| Failure-category reattachment | Data / Codex | Complete: post-writer `intraday-head-20260818T1924006306454Z` binds `collection_exit_nonzero / reason_unavailable` through `execution/kis-paper-intraday-head-invocation-v1/intraday-head-20260818T1924006306454Z/terminal.json` and `execution/kis-paper-intraday-head-schedule/intraday-head-20260818T1924006306454Z.json`. |
| Failure-category confirmation | Data / existing `thericher-kis-paper-intraday-head` task | Complete: later `intraday-head-20260818T2120005941479Z` is hash-bound but `retained_partial` with a successful collection outcome, so its compatibility-default `reason_unavailable` is noncomparable. No recovery proposal or behavior change followed. |
| FirstRate source-local M1 normalization | Data / Codex | Complete: archive hashes/expected entries, strict decode, canonical output hashes, and timestamp-set equality are retained in the external normalization receipt. SPY/QQQ provider round-trip counts are 207,824/210,482; no promotion followed. |
| FirstRate source-local timeframe mechanics | Data / Codex | Complete: canonical hashes reattached; actual UTC-anchored 1m/5m/10m/1h/3h outputs are aggregated only and each emitted bar passed source-bucket OHLCV/ordering/completion checks. No resampled rows, coverage, model, or Paper consumer followed. |
| FirstRate source-local window preflight | Data / Engine Research | Complete: 32 frozen cells reattached canonical/mechanics hashes and retained only eligible-window count/end-timestamp-set hashes. No labels, features, predictions, GPU allocation, model selection, KIS, or Paper consumer followed. |
| FirstRate source semantics retrieval | Data / Claude review | Complete: official free-data/license pages re-retrieved with matching hashes; only vendor-declared timezone/omission facts are retained, and offset convention/bar boundary remain `not_disclosed`. No promotion followed. |
| Norgate D1 capability reprobe | Data / isolated host runtime | Complete as scoped: the one invocation produced no parseable source-safe output or task-owned receipt. It proves no Norgate availability, subscription, source, or data fact and is not retried. |
| Norgate host readiness bridge | Data | Complete: a source-safe immutable receipt reattests `input_unavailable/local_api_not_ready`; host runtime is available and later categories are not checked. No raw data, credential, KIS, broker, scheduler, or Docker path was used. |
| Market-data contract inventory | Data / Engine Research | Complete: immutable six-class receipt `market-data-contract-inventory-20260819-r1.json` reattaches as 3 unavailable and no predictive/Paper/GPU-eligible input. |
| Later intraday terminal reattachment | Data / existing task | Owned monitoring: current pointer remains the 2026-08-18 baseline; accept only a strictly later terminal/completion binding. Do not poll or manually invoke the task. |
| SPY D1 stability | Data | Existing observer owns its next eligible weekday observation. Its status is observational only, never provider finality. |
| Virtual-Paper lifecycle canary | Execution | The 2026-08-17 23:35 KST task receipt is bound offline to its direct lifecycle receipt as `canary_completed -> cancelled / clean`, `paper_only`, attribution `not_eligible`, and acknowledged order-reference category only. It is not a fill, PnL, alpha, or model result. The earlier 2026-08-11 unknown remains separately owned by its reconciliation path; do not resubmit either intent. Next task-owned opportunity: 2026-08-19 23:35 KST. |
| QQQ provisional runtime observation | Execution | Embedded in the existing intraday-head task. Its v5 validator recomputes the cache/window and exact non-promoting grade; do not manually invoke or duplicate it. |
| Read-only Paper account observer | Execution | Existing four-minute task is the sole owner. Its validated provenance is marker-present under an assumed-honest host, not cryptographic Scheduler-origin proof. |
| Public-source research | Engine Research | Qlib, PatchTST, and FinRL are source-only references, with no code, package, data, weight, campaign, GPU, or Paper consequence. FinRL conventions cannot replace owned data, timing, or cost semantics. |

External quota and session waits belong to their named task. Codex does not
foreground-sleep or add a duplicate scheduler while an independent package is
ready.

## Current Guardrails

- Never read or route `KIS_LIVE_*`.
- Keep raw market data under `D:\market_data` and generated artifacts under
  `D:\thericher-v2\model-artifacts`; neither belongs in Git.
- A qualified research input must retain exact provenance, completed-bar
  geometry, chronological split, decision-time availability, and finality
  facts. A missing condition narrows that input only; it is never a global
  approval hold.
- These are necessary/default-deny local reconstruction conditions, not
  cryptographic provider-origin proof. A future `qualified` designation must
  name its clock authority, timezone/DST session rule, and non-overlapping
  chronological boundary; otherwise it remains a scoped unavailable input.
- Invocation markers are diagnostic-only, immutable external artifacts. They
  preserve source-safe run/timestamp/outcome categories, never raw market data,
  credentials, account values, or broker data. Their presence proves only a
  host-side marker under an assumed-honest host, not a Scheduler-origin claim.
- Model output remains untrusted until deterministic Execution validation.
  Local replay fills retain `source: local_paper`.

## Evidence Index

- Current intraday terminal reader:
  `scripts\project_kis_paper_intraday_head_schedule_receipt.py`.
- Intraday capture-topology audit:
  `scripts\inspect_kis_paper_intraday_capture_topology.ps1`.
- Current invocation-marker reader:
  `scripts\project_kis_paper_intraday_head_invocation_receipt.py`.
- Invocation-to-terminal reattachment reader:
  `scripts\project_kis_paper_intraday_invocation_reattachment.ps1`.
- FirstRate normalized M1 receipt:
  `D:\thericher-v2\model-artifacts\data-receipts\firstrate-free-intraday\firstrate-free-intraday-source-local-normalization-v1.json`.
- FirstRate source-local timeframe mechanics manifest:
  `D:\thericher-v2\model-artifacts\data-receipts\firstrate-free-intraday\firstrate-free-intraday-source-local-timeframe-mechanics-v1.json`.
- FirstRate source-local window preflight manifest:
  `D:\thericher-v2\model-artifacts\data-receipts\firstrate-free-intraday\firstrate-free-intraday-source-local-window-preflight-v1.json`.
- FirstRate official source retrieval receipt:
  `D:\thericher-v2\model-artifacts\data-receipts\firstrate-free-intraday\firstrate-source-semantics-retrieval-v1.json`.
- FirstRate review-limited interpretation receipt:
  `D:\thericher-v2\model-artifacts\data-receipts\firstrate-free-intraday\firstrate-source-semantics-interpretation-v1.json`.
- FinRL source-only receipt:
  `D:\thericher-v2\model-artifacts\research\engine-source-retrieval\finrl-environment-interface-source-20260819-r1\source-retrieval.json`.
- QQQ M1/M5/M10/H1/H3 mechanics:
  `D:\thericher-v2\model-artifacts\data\source-local-qqq-mtf-resampling-mechanics-v1\20260807-qqq-mtf-r1\summary.json`.
- Fixed local-paper EMA attribution:
  `D:\thericher-v2\model-artifacts\research\source-local-ema-local-paper-pnl-attribution-v1\20260807-ema-pnl-attribution-r1\summary.json`.
- Fixed local-paper Donchian attribution:
  `D:\thericher-v2\model-artifacts\research\source-local-qqq-donchian-local-paper-pnl-attribution-v1\20260807-donchian-pnl-r1\summary.json`.
- Qlib source-only receipt:
  `D:\thericher-v2\model-artifacts\research\engine-source-retrieval\qlib-architecture-source-20260809-r1\source-retrieval.json`.
- PatchTST source-only receipt:
  `D:\thericher-v2\model-artifacts\research\engine-source-retrieval\patchtst-source-20260809-r1\source-retrieval.json`.
- Tiingo raw-D1 source-safe receipt:
  `D:\thericher-v2\model-artifacts\data-receipts\tiingo-etf-d1\4a2344b7ab8ec2eaf0b1a5e4afcd41e07cf0b4c14e13db64d07b41fd054883d2.json`.
- Tiingo IEX r1 source-isolated CUDA receipt:
  `D:\thericher-v2\model-artifacts\research\tiingo-iex-r1-representation-integration-v1\r1-cuda-20260810-r1\summary.json`.

## Verification And Git

The completed intraday failure-category confirmation package passed 25 focused
offline reader/reattachment tests, the 2,996-pass authority parallel suite with
17 skips, Ruff, both credential-free Compose configuration parses, and
`git diff --check`. Verification made no KIS, credential, broker, collector,
Docker service, or Task Scheduler call. It reattached one later terminal as
successful but `retained_partial`, which makes the compatibility-default
category noncomparable; no recovery behavior changed.

The FirstRate source-local normalization package passed 15 focused normalizer,
provider, and batch-receipt tests. Its actual offline run validated both archive
hashes and emitted timestamp-set equality; the local provider re-read all
canonical Bars without a network, credential, KIS, broker, Task Scheduler, or
Docker-service call. It then passed the 3,011-pass authority parallel suite with
17 skips, Ruff, both credential-free Compose configuration parses, and
`git diff --check`.

The FirstRate timeframe-mechanics package passed 19 focused normalizer/provider/
batch/mechanics tests. Its actual offline run reattached the canonical SPY/QQQ
hashes and wrote only the external aggregate manifest; no network, credential,
KIS, broker, Task Scheduler, or Docker-service call occurred. It then passed
the 3,015-pass authority parallel suite with 17 skips, Ruff, both credential-
free Compose configuration parses, and `git diff --check`.

The FirstRate source-local window-preflight package passed 23 focused
normalizer/provider/mechanics/preflight tests. Its actual offline run reattached
the parent receipt hashes and wrote only the 32-cell aggregate manifest; no
network, credential, KIS, broker, Task Scheduler, Docker-service, training, or
GPU call occurred. Claude rejected a proposed source-isolated GPU follow-up as
`unsupported`, so no appointment followed. It then passed the 3,019-pass
authority parallel suite with 17 skips, Ruff, both credential-free Compose
configuration parses, and `git diff --check`.

The FirstRate source-semantics package passed seven focused source-retrieval and
review-interpretation tests. It re-retrieved two official FirstRate pages twice
each with matching hashes, then attached a source-safe Claude
`supported-with-limits` interpretation without rewriting source evidence. No
market data, credential, KIS, broker, scheduler, Docker service, model, or GPU
path was used. It then passed the 3,026-pass authority parallel suite with 17
skips, Ruff, both credential-free Compose configuration parses, and
`git diff --check`.

The Tiingo IEX source-isolated package passed 19 focused data/research tests,
the 2,919-pass authority parallel suite with 17 skips, Ruff, both Compose
configuration parses, and `git diff --check`. The CPU and CUDA Docker commands
were networkless and wrote only external source-safe summaries. The suite also
repaired three pre-existing test-contract mismatches exposed by the local Torch
runtime; no KIS, credential, broker, or scheduler call occurred in verification.
The 2026-08-10 quote-session route reattestation added one no-public-port
contract and passed 123 focused execution tests, Ruff, and both Compose parses;
it did not call KIS, start a task/container, or read a private receipt body.
The 2026-08-11 intraday terminal closure used only the existing offline reader
and source-safe task facts. It passed 85 focused receipt/capture/schedule tests,
the 2,931-pass authority parallel suite with 17 skips, Ruff, both Compose
configuration parses, and `git diff --check`.
The cumulative-coverage repair used only fixture metadata and one filtered
metadata-only cache inspection. It passed 90 focused coverage/capture/schedule
tests, the 2,933-pass authority parallel suite with 17 skips, Ruff, both
Compose configuration parses, and `git diff --check`.
Use Git history for immutable commit checkpoints rather than copying a
self-staling latest hash here.

## Resume Procedure

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `NEXT_CODEX_GOAL.md`, this handoff, `AGENTS.md`, `RUNBOOK.md`, and the
   active stateboards.
3. Run a compact Throughput Review, then dispatch only a ready,
   non-conflicting package.
4. The first post-writer marker is one comparable task-stage
   `collection_exit_nonzero / reason_unavailable` binding. The later marker is
   successful and `retained_partial`, so its default category is noncomparable.
   Never infer a Scheduler, collector, provider, or Paper outcome from either
   marker.
5. FirstRate canonical M1 outputs and window geometry remain source-isolated.
   The vendor timezone label/omission declaration does not settle offset or bar
   boundary semantics; never cross-feed align them until a distinct consumer
   obtains its own qualified-input contract.
