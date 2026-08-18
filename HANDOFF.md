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
`firstrate-source-local-timeframe-mechanics-v1`, will prove only their existing
local 1m/5m/10m/1h/3h resampling geometry; it remains source-isolated
retrospective mechanics, never a KIS/Paper/model input.

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
entry names, strict source timestamps, Eastern-to-UTC conversion, and exact
decoded/emitted timestamp-set equality. It wrote canonical CSVs beneath
`D:\market_data\us_equities\firstrate_free_intraday\canonical` and the
source-safe receipt
`D:\thericher-v2\model-artifacts\data-receipts\firstrate-free-intraday\firstrate-free-intraday-source-local-normalization-v1.json`
(`sha256:374fc885b831b6a2aea59526e25f918ebe568414b018b621452c02d608f988be`).
The standard local provider re-read 207,824 SPY and 210,482 QQQ complete M1
Bars with receipt-matching timestamp sets. This records source-local mechanics
only: no reindex/fill, session-coverage, KIS parity, decision-time availability,
provider finality, model, Paper, PnL, or live claim follows.

## Current Cross-Lane Facts

| Lane | Current fact | Next valid action |
| --- | --- | --- |
| Data | The legacy and first post-writer markers retain `collection_exit_nonzero / reason_unavailable`. The later hash-bound marker is instead `retained_partial/current_session_not_complete` with `collection_outcome: succeeded`; its default category is noncomparable. FirstRate SPY/QQQ canonical M1 outputs are hash-bound and provider-readable, but remain source-isolated. | Produce a source-safe actual-data resampling mechanics manifest for 1m, 5m, 10m, 1h, and 3h without densifying, calculating session coverage, or creating a KIS/Paper/model consumer. |
| Data | On 2026-08-14 the provisioned-host, source-safe Norgate reader returned `local_api_not_ready`; it wrote no receipt and did not read catalog, metadata, or prices. This categorical result does not determine NDU process, update, subscription, expiry, vendor-access, or rights state. Tiingo/Norgate and broad-D1 sources remain non-promoting. | Do not launch another trigger or repeat the hidden start. The one operator-visible diagnostic is the already-running NDU `Update > Check for Updates` plus database/subscription-state outcome, then minimize rather than close the app; this does not assert a cause or block the Paper canary. If the reader later becomes ready, verify active US subscription and Database Location; only then, if the catalog exposes `US Equities`, run one bounded Norgate probe. Tiingo can support only retrospective controls without a new selection look or KIS/Paper join. |
| Engine Research | The Tiingo IEX r1 source-isolated CPU/CUDA runtime matrix is closed with no retained weights or predictive interpretation. A synthetic caller-owned local-paper two-step replay proves future policy-environment stepping against owned cost/fill semantics only. | No candidate, training, GPU appointment, or Paper input follows; a later predictive campaign needs a distinct qualified input and frozen contract. |
| Research Steward | RTX 4090 is free after the completed Tiingo IEX r1 source-isolated appointment; no sealed evaluation was spent. | Allocate only a fresh frozen eligible campaign; never manufacture training to fill GPU time. |
| Execution | The 2026-08-17 23:35 KST owned quote-session receipt reattached offline as `canary_completed -> cancelled / clean`, `paper_only`, with attribution `not_eligible`; the bound direct lifecycle receipt records only an acknowledged order-reference category. The earlier 2026-08-11 `outcome_unknown / unresolved` remains its own exact-run reconciliation fact. | This exact run proves neither a fill, PnL, alpha, nor model result. Do not resubmit either durable intent; their existing reconciliation paths remain the only owners. |
| Shared worktree | Alternate IWM collector WIP is untracked/modified and rejected from this objective. | Do not touch, stage, invoke, or reconcile it without a separate assignment. |

## Ready / Owned / Due

| Work | Owner | Status |
| --- | --- | --- |
| Invocation receipt reattachment | Data / Codex | Complete: the exact fresh marker, terminal, and schedule receipt bind a `collection_exit_nonzero` task stage. Its external evidence pointers are `execution/kis-paper-intraday-head-invocation-v1/intraday-head-20260818T1728005721271Z/terminal.json` and `execution/kis-paper-intraday-head-schedule/intraday-head-20260818T1728005721271Z.json`. |
| Task-path failure localization | Data / Codex | Complete: one closed, free-text-free category writer and legacy-compatible offline reader preserve the stage exit code. No timing/page/task/consumer change followed. |
| Failure-category reattachment | Data / Codex | Complete: post-writer `intraday-head-20260818T1924006306454Z` binds `collection_exit_nonzero / reason_unavailable` through `execution/kis-paper-intraday-head-invocation-v1/intraday-head-20260818T1924006306454Z/terminal.json` and `execution/kis-paper-intraday-head-schedule/intraday-head-20260818T1924006306454Z.json`. |
| Failure-category confirmation | Data / existing `thericher-kis-paper-intraday-head` task | Complete: later `intraday-head-20260818T2120005941479Z` is hash-bound but `retained_partial` with a successful collection outcome, so its compatibility-default `reason_unavailable` is noncomparable. No recovery proposal or behavior change followed. |
| FirstRate source-local M1 normalization | Data / Codex | Complete: archive hashes/expected entries, strict decode, canonical output hashes, and timestamp-set equality are retained in the external normalization receipt. SPY/QQQ provider round-trip counts are 207,824/210,482; no promotion followed. |
| FirstRate source-local timeframe mechanics | Data / Codex | Next objective: use the canonical SPY/QQQ M1 files through the existing resampler to report only source-safe 1m/5m/10m/1h/3h geometry. No filling, coverage/finality claim, model, or Paper consumer. |
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
5. FirstRate canonical M1 outputs are source-isolated. Use them only for the
   frozen local-resampling mechanics objective until a distinct consumer obtains
   its own qualified-input contract.
