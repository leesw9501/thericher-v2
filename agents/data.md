# Data Agent Stateboard (Data Operations)

`AGENTS.md` owns policy and `NEXT_CODEX_GOAL.md` owns the company objective.
This is a current Data projection, not a run ledger. Git and immutable
external artifacts retain historical evidence.

## Ownership And Boundaries

Data owns providers, acquisition, provenance, calendars, canonical storage,
resampling, manifests, temporal splits, and quality facts. It does not select
strategies, fit models, or make execution decisions. KIS Paper market-data
collection uses only its named owner path; never read or route `KIS_LIVE_*`.

## Current Sources

| Source | Status | Permitted interpretation |
| --- | --- | --- |
| KIS Paper QQQ/NAS + SPY/AMS intraday head | The legacy and first post-writer 2026-08-19 KST markers each bind a `recovery` terminal with `collection_exit_nonzero / reason_unavailable`. The later `intraday-head-20260818T2120005941479Z` instead binds `retained_partial/current_session_not_complete` with `collection_outcome: succeeded`; its compatibility-default category is noncomparable. The source-safe static audit independently reports `matches` for the installed Task enabled/action/triggers/settings and the checked-in first `session-capture` runner/Compose route (`task_state: ready`), with no Task, Docker, or KIS invocation. Metadata topology remains `current_metadata_consistent`, while cumulative session coverage remains `incomplete/current_session_short`. The enabled one-action Task has its Operational log disabled. | The static match rules out only checked-in/installed contract drift. It does not prove a task ran, Scheduler origin, Docker dispatch or container entry, collector/provider cause, session completeness, finality, or model eligibility. The one comparable category remains task-path diagnostic evidence only; no timing/page remedy or reusable Paper-candidate promotion follows. |
| KIS Paper QQQ/SPY M1 cursor cache | 21 shared complete regular sessions; exact cursor scope is exhausted. | Source-local mechanics, fixed local-paper baselines, and target-free window preflight only. |
| KIS Paper private D1 | Unadjusted/partial with finality and as-of facts unavailable. The NAS daily-history panel and historical-forward projection now reject a nonempty common-session sequence with an interior normal session missing under pinned local `pandas-market-calendars==5.4.0` `NASDAQ` alias (`NYSE` calendar); this package did not reread the current cache. | `input_unavailable` for daily predictive work. A forward cache retains later rows across a gap, but its prospective input stays unavailable until the full boundary-to-forward session chain is present. The continuity rule proves neither source finality nor current-cache qualification. |
| KIS Paper broad D1 panel | The latest source-safe postrun snapshot (2026-08-01) recorded 2,119/2,119 current-listing targets covered, zero quarantined targets, and zero mismatches over its 604-target baseline overlap. A later successful Task exit does not itself refresh this frozen snapshot. | Coverage/provenance inventory only: current-listing, non-PIT, unadjusted, corporate-action-unqualified, and session-finality-unattested. It cannot supply a target, ranking, training, or Paper input. |
| KIS Paper IWM/AMS M1 | Isolated current-head v2 observations replay locally; no H1/H3 history. Its separate one-page cache reattached offline as exactly one `head` chunk with verified index/manifest/raw integrity, `51` complete bars, `17` adjacent 1m pairs, `33` non-adjacent pairs, and a `660`-second maximum interval. Its source-safe mechanics receipt is `sha256:7dbdae99adaf1e19fe1c3d6bd2760edb71cae2cb7c737c519a5b5f3259e50818`; no raw rows were emitted. The bounded caller-derived probe accepted its head but observed no recognized continuation header, writing only `sha256:99068ebe69ee7d5300eeb2671eed433df87830db980947ac26d4b97a3b267cea`. | The exact IWM current-head request contract has no observed continuation under this one-run probe. Default IWM remains one page; no retry, collector, schedule, raw probe cache, history/finality/availability claim, model input, or Paper input follows. |
| Tiingo raw D1 ETF trio | The 2026-08-09 immutable SPY/QQQ/IWM snapshot reattested offline through 2026-08-07 with 8,438/6,896/6,588 sessions. | A continuation of already-seen, source-separated non-PIT history: retrospective controls and diagnostics only, never a fresh selection look, threshold calibration, ranking, sealed evaluation, GPU, or Paper input. |
| Tiingo IEX M5 r1 ETF trio | Pinned 2026-07-19 IEX-only snapshot reattested offline by raw hashes, stored gzip hash, and exact canonical payload. | One completed source-isolated reconstruction runtime integration only; no source scope, training eligibility, KIS equivalence, model-selection, or Paper-input change. |
| Norgate trial tail | The one host-only readiness bridge completed through the isolated runtime and wrote a hash-bound categorical receipt. It records `input_unavailable/local_api_not_ready`; host runtime is `available`, while catalog, update metadata, and active-root resolution are `not_checked`. No raw Norgate data was read. | This is a local API state only, not an updater, subscription, vendor-access, rights, or data-capability conclusion. Do not repeat the daily probe or start a pilot. Because the result is not `ready/one`, no distinct Norgate capability goal is ready. |
| FirstRate free M1 SPY/QQQ | The two hash-bound original ZIPs normalized to canonical local CSVs with expected entry names and exact decoded/emitted timestamp-set equality. SPY has 207,824 and QQQ 210,482 provider-readable complete M1 Bars; UTC-anchored 1m/5m/10m/1h/3h geometry and the frozen 32-cell target-free window matrix reattached offline. Official FirstRate evidence labels data US Eastern/New York and declares zero-volume bars omitted. | The existing DST-aware New York-to-UTC conversion is a source-local assumption: offset convention and bar start/end stamping remain `not_disclosed`. Omission is vendor-declared only, never session coverage or cross-feed alignment. Project policy remains private/internal with no redistribution. The source proves neither KIS parity, decision-time availability, finality, a predictive model input, or a Paper input. |
| Fixed market-data contract inventory | The external immutable inventory records all six predeclared footprints with only shallow presence and receipt hashes: KIS M1/D1 and Norgate trial are `input_unavailable`; FirstRate M1 is `source_local_mechanics_only`; Tiingo ETF D1 is `retrospective_control_only`; Tiingo IEX M5 is `non_promoting_runtime_only`. | The receipt confers no predictive, Paper, or GPU consumer. It is an evidence map only; each status is scoped and a later qualified input needs its own contract. |
| NYSE Daily TAQ source discovery | The official catalog distinguishes a public sample from a full paid product. No data was acquired and no provider was adopted. | Sample schema/aggregation reference only; it is not a no-cost ongoing or KIS-aligned prospective input. |

Raw market bytes remain under `D:\market_data`. Source-safe receipts and
research artifacts remain under `D:\thericher-v2\model-artifacts`.

## Active Objective

The fresh 2026-08-17 06:20 KST terminal is closed as an exact, source-safe
`input_unavailable/session_coverage_incomplete/current_session_short`
classification, matching the 2026-08-15 baseline. Its offline projection
verified the bound cumulative-coverage and availability evidence;
the causal attestation remains `not_recorded` and the pair binding
`legacy_unbound`. The result does not establish provider finality, availability
at a decision time, a model input, or a Paper action.

The completed diagnosis found one cumulative-coverage defect: later identical
fingerprints could not promote a forming row to complete. The repair preserves
conflicting-fingerprint and candidate-batch handling, uses no raw M1 rows, and
does not rewrite any immutable receipt. It is now built in the existing service
from a clean `HEAD` context: 56 focused tests, the 2,933-pass authority suite
with 17 skips, Ruff, and both Compose parses passed. A metadata-only
re-evaluation remains short for the current session, so the next task-owned
terminal alone can test the repaired writer at runtime.

The short-session topology category is complete for both immutable terminals.
Any later task-owned terminal may supply only a new, separately scoped category;
its due time remains task-owned and is never a foreground wait.

The offline reader now accepts a separately hash-bound causal-condition
attestation at a fixed external artifact location, but no current task writes
or binds one. An absent binding stays `input_unavailable`; malformed or
mismatched bound evidence fails closed through the existing unavailable reader.
This contract has no collector, credential, network, or schedule behavior.

The static audit and writer integration are complete. The writer reads only the
current source-safe terminal projection and a separate assumed-honest external
observer input. It rejects missing, task-derived, stale, time-invalid, or
mismatched input, writes only outside Git, and does not alter a task or an
immutable terminal. The real current-terminal smoke returned
`not_written/session_coverage_incomplete`; no attestation was attached.

Claude's scope-matched review was `uncertain`: hashes and categories cannot
cryptographically prove that an external-observer input was independent. The
writer therefore states the assumed-honest limitation, requires exact
run/timestamp binding, and rejects an explicit task-derived input or a replayed
run. This limitation does not block the separate collection-recovery package.

The full-session topology audit is now complete. Its `run_or_persistence_unresolved`
result remains intentionally narrower than a Scheduler-failure claim. The first
fresh marker reattached the exact task-path run
`intraday-head-20260818T1728005721271Z`: the marker began at
`2026-08-18T17:28:00.572127Z`, the schedule receipt was observed at
`2026-08-18T17:28:04.254121Z`, and the dispatcher completed at
`2026-08-18T17:28:05.278714Z`. Its hash-bound schedule terminal is `recovery`
with scheduler exit code `1` and the closed stage category
`collection_exit_nonzero`. This establishes a task-path nonzero only; it cannot
identify a Docker wrapper, collector-process, provider, or persistence cause.
The existing task definition, timing, pages, consumers, KIS route, and Paper
behavior remain unchanged.

The new terminal field accepts only `reason_unavailable`, `dispatcher_config`,
or `collector_provider` from exactly one existing structured collector error
payload. It stores neither the payload nor free text and preserves the existing
stage exit code. The offline reader accepts old immutable markers as
`reason_unavailable`; the legacy marker was reattached that way without byte
changes. The first post-writer marker,
`intraday-head-20260818T1924006306454Z`, binds the same closed category through
the current pointer, immutable terminal, and exact schedule receipt. It is one
diagnostic binding, not a cause or recovery premise. A 2026-08-19 Claude scope
review ended `review_unavailable` because of an API overload, so no
category-based recovery claim exists.

The same offline reader now accepts paired opaque baseline run and completion
facts. Against the first post-writer marker, the unchanged current pointer is
`marker_not_later`, not a second category binding. This reader guard leaves the
existing Task, timing, pages, KIS route, Docker path, consumers, and Paper
behavior unchanged.

The first strictly later pointer is
`intraday-head-20260818T2120005941479Z`, completed at
`2026-08-18T21:20:32.579443Z`. Its terminal and exact schedule receipt hashes
are `sha256:cf3b6983308630167f97962317aa3f89e7d96eb0f66beb2d6a9dd186c4a558ad`
and `sha256:c18b5024a7a058541e6d81757bb30405381451bfdee7b5aad576be5380d349a2`.
The offline projection classifies it as
`retained_partial/current_session_not_complete` with a successful collection
outcome. `failure_category_is_comparable` is therefore false despite the
compatibility-default `reason_unavailable`; no second failure-category binding,
recovery proposal, or behavior change exists. Its source-safe pointers remain
external-root-relative, marker provenance is assumed-honest-host rather than
cryptographic Scheduler origin, and Task Scheduler Operational logging is
disabled.

The source-safe static audit separately reattached the installed
`thericher-kis-paper-intraday-head` Task as `matches`: enabled, exactly one
expected action, four non-repeating Tuesday-through-Saturday KST triggers,
expected recovery/settings shape, and the checked-in first `session-capture`
runner/Compose route all match. Its receipt is
`execution/kis-paper-intraday-head-static-contract-v1/static-contract-20260819T1234034490997Z-931b776ddcdc.json`
with `sha256:12d79514199a50ae7ec6bbd27abfbe90e3fb3826fe505ba762f6122fadc88e95`.
It read no current marker pointer and invoked no Task, Docker, KIS, broker, or
collector. It supplies static-contract evidence only, so the known terminal
remains `reason_unavailable` without a runtime or provider diagnosis.

## Ready / Owned / Due

| Work | Owner | Completion evidence |
| --- | --- | --- |
| Intraday coverage-repair rollout | Data / existing task image | Complete: clean-context image build and source-safe static reattestation passed without a task, KIS, Docker service, or collector invocation. |
| Invocation-marker reattachment | Data / Codex | Complete: the first fresh marker and exact schedule terminal reattached as `collection_exit_nonzero`; its source-safe pointers remain external-root-relative. |
| Task-path failure localization | Data / Codex | Complete: an allowlisted free-text-free category writer and legacy-compatible reader preserve the exact stage exit. No task, pages, timing, or consumer change followed. |
| Failure-category reattachment | Data / Codex | Complete: post-writer `intraday-head-20260818T1924006306454Z` reattached as `collection_exit_nonzero / reason_unavailable` through exact hash-bound terminal and schedule receipts. No timing, pages, task, or consumer behavior changed. |
| Failure-category confirmation | Data / existing `thericher-kis-paper-intraday-head` task | Complete: later `intraday-head-20260818T2120005941479Z` is hash-bound but successful and `retained_partial`, so the preserved default category is noncomparable. No recovery proposal or behavior change followed. |
| Static intraday Task-contract reattestation | Data / Codex | Complete: installed Task enabled/action/triggers/settings and checked-in first `session-capture` runner/Compose route are all `matches`; the source-safe receipt is hash-bound and the audit invoked no Task, Docker, KIS, collector, or broker. It does not diagnose the existing terminal. |
| IWM isolated current-head capture | Data | Complete: one fixed IWM/AMS page accepted with the replay-isolated source-safe receipt above; no retry, pagination, replay promotion, or consumer change followed. |
| IWM isolated cache mechanics | Data | Complete: strict index identity binds the generic raw verifier, with replay-root, index-replacement, raw-tamper, and artifact-symlink rejection coverage. Only source-safe aggregate mechanics were emitted. |
| IWM temporal-reach continuation probe | Data | Complete: one head was accepted, its continuation header was not recognized, and no second page was requested. The exact endpoint expansion path is closed without retry; the external receipt is the source-safe hash above. |
| Tiingo IEX r1 reattestation | Data | Complete: the fixed snapshot remains hash-bound and source-isolated. No further acquisition, scope change, or consumer promotion follows. |
| SPY D1 stability | Existing task | Its next eligible weekday observation is task-owned; `stable` is not provider finality. |
| Norgate host readiness bridge | Data / isolated host runtime | Complete: the immutable bridge receipt is `input_unavailable/local_api_not_ready`; host runtime is available and all later categories are not checked. It never accessed a price, membership, listing, corporate-action, credential, KIS, broker, scheduler, or Docker path. |
| FirstRate source-local M1 normalization | Data | Complete: reattached ZIP hashes, decoded only expected entries, and retained source-safe canonical/output/timestamp-set evidence. The local provider re-read 207,824 SPY and 210,482 QQQ complete M1 Bars; do not infer continuity or promotion. |
| FirstRate source-local timeframe mechanics | Data / Codex | Complete: canonical hashes reattached, existing resampler emitted only complete unique contiguous observed-minute buckets, and source-safe 1m/5m/10m/1h/3h hashes/counts are retained. UTC-epoch alignment is not a regular-session claim. |
| FirstRate source-local window preflight | Data / Engine Research | Complete: two canonical streams reattached through the mechanics receipt and each frozen matrix cell retained only eligible-window counts/end-timestamp-set hashes. No label, feature, prediction, model, selection, GPU, KIS, or Paper consumer followed. |
| FirstRate source semantics retrieval | Data / Claude review | Complete: official free-data and license pages re-retrieved with matching page hashes, then a review-bound interpretation preserved offset convention and bar timestamp boundary as `not_disclosed`. No source promotion followed. |
| Market-data contract inventory | Data / Engine Research | Complete: six fixed source classes reattached through shallow metadata and source-safe receipt hashes. Counts are `input_unavailable: 3`, `source_local_mechanics_only: 1`, `retrospective_control_only: 1`, and `non_promoting_runtime_only: 1`; no eligible predictive/Paper/GPU consumer exists. |

## Quality Contracts

- A completed bar is not proof of availability at a prior decision time.
- A self-consistent task-owned receipt is marker-present local provenance under
  an assumed-honest host, not independent proof of provider origin. A future
  `qualified` classification needs a named clock authority, timezone/DST
  session rule, and non-overlapping chronological boundary; otherwise that
  exact input remains unavailable.
- A bound causal-condition attestation must independently name the clock,
  `America/New_York` DST/session rule, M1 completed-bar geometry, and a
  non-overlapping chronological boundary before its availability/finality
  categories can qualify a consumer. Its fixture-tested branch is not current
  provider evidence.
- An exact source/cursor limit closes only that route; it does not prove a
  provider-wide history limit.
- A `collection_exit_nonzero` terminal is a closed task-stage category, not a
  collector-process, provider, or Scheduler-origin diagnosis. A later category
  may be only `dispatcher_config`, `collector_provider`, or
  `reason_unavailable`, never free text, and preserves the original exit code.
- A category is comparable only for a later hash-bound `collector_nonzero`
  terminal with `collection_outcome: nonzero`. A successful `retained_partial`
  or `complete_session` may preserve a compatibility-default category, but it
  is noncomparable. One comparable post-writer binding is diagnostic only; a
  category-based recovery proposal needs two independently hash-validated
  matching comparable bindings and a fresh Claude falsification-first verdict.
  Divergence remains diagnostic only.
- A later binding must differ from its paired opaque baseline run and complete
  strictly after its paired completion timestamp. `marker_not_later` is a valid
  stale-pointer diagnosis, never a second binding, a cause, or a behavior
  change.
- Generic resampling skips a target bucket containing a duplicate timestamp or
  incomplete source record. `Bar` has no source-revision or observation-order
  provenance, so upstream Data reconciliation must resolve a later revision
  before a complete duplicate can be used.
- A direct `LocalCsvBarProvider` query rejects duplicate returned timestamps
  rather than silently returning an ambiguous M1 stream. This is source-local
  query integrity only; it does not infer revisions, session continuity, or
  promotion eligibility.
- A direct `LocalCsvBarProvider` query requires the exact canonical
  `CSV_FIELDS` header before parsing. A missing `complete` field cannot be
  defaulted to a completed bar through this path; this remains source-local
  integrity only, not an assertion about source completeness or finality.
- Training catalog inspection treats a `date` column used as the parsed
  timestamp as a UTC-derived session key, rather than treating each ISO
  timestamp as an invalid session label. This restores per-session gap
  accounting for that schema without relaxing a distinct `session_date` field.
- A cumulative intraday session with a non-`none`
  `conflicting_overlap_category` is metadata-conflicted even when its
  expected-minute count is complete. The current capture-category projection
  does not yet encode that conflict; this is a deferred Data writer hardening,
  not a reinterpretation of any immutable receipt or a hold on another lane.
- NAS D1 history reattestation and prospective forward projection compare their
  nonempty common session sequences with the pinned local
  `pandas-market-calendars==5.4.0` `NASDAQ` alias (`NYSE` calendar) schedule.
  An interior scheduled-session omission fails closed; weekends, holidays, and
  early closes remain valid sessions. The forward cache may retain later rows
  while its projection remains unavailable. This detects continuity only and
  neither fills data nor proves KIS finality, as-of availability, adjustments,
  or model/Paper eligibility.
- Preserve a durable serial cursor only after a useful capability probe
  establishes continuation semantics. Do not replace measurement with a
  parallel request flood.
- One collector keeps its in-memory KIS client/token while valid. The
  five-minute cross-process token-start guard spaces fresh token POSTs only;
  it is never a foreground sleep or token lifetime.
- Data limitations are visible to their exact consumer. They never become a
  global approval gate or suppress an independent lane.
- FirstRate source-local normalization must preserve the decoded timestamp set
  exactly. A zero-volume omission is `not_present_in_source`, never a missing
  minute, a session gap, or a candidate for a synthesized row.
- FirstRate canonical output uses the local `CSV_FIELDS` contract and has a
  source-safe M1 provider round-trip check. `complete: true` records the
  normalized historical bar representation only; it is not session coverage,
  provider finality, or decision-time availability evidence.
- FirstRate generic resampling is UTC-epoch anchored. An emitted 5m/10m/1h/3h
  bar requires a complete unique contiguous observed-minute source bucket and
  passes OHLCV aggregation checks; a non-emitted bucket is only
  `not_emitted_from_observed_source_set`, not a market/session gap.
- FirstRate's official source labels data US Eastern/New York and vendor-declares
  zero-volume omissions. It does not establish DST-observing versus fixed-offset
  conversion or bar start/end stamping, so canonical timestamps cannot be
  cross-feed minute aligned or treated as session-completeness evidence.
- Tiingo's fixed ETF trio is a repeated historical sample, not independent
  evidence. Its non-PIT scope cannot calibrate a later model-side threshold or
  filter, and it cannot be joined into the KIS causal/Paper path.
- A Norgate readiness receipt may state only host/runtime/API/catalog/update/root
  categories. `local_api_not_ready` leaves later categories `not_checked`; it
  proves neither source capability nor an updater, subscription, or rights cause.

## Current Evidence

- Intraday source-safe projection:
  `scripts\project_kis_paper_intraday_head_schedule_receipt.py`.
- Capture-topology audit and invocation-marker readers:
  `scripts\inspect_kis_paper_intraday_capture_topology.ps1`,
  `scripts\project_kis_paper_intraday_head_invocation_receipt.py`, and
  `scripts\project_kis_paper_intraday_invocation_reattachment.ps1`.
- Static Task-contract audit and source-safe evidence:
  `scripts\inspect_kis_paper_intraday_head_static_contract.ps1` and
  `execution/kis-paper-intraday-head-static-contract-v1/static-contract-20260819T1234034490997Z-931b776ddcdc.json`
  (`sha256:12d79514199a50ae7ec6bbd27abfbe90e3fb3826fe505ba762f6122fadc88e95`).
- Later category-confirmation terminal and schedule evidence:
  `execution/kis-paper-intraday-head-invocation-v1/intraday-head-20260818T2120005941479Z/terminal.json`,
  `execution/kis-paper-intraday-head-schedule/intraday-head-20260818T2120005941479Z.json`
  under `D:\thericher-v2\model-artifacts`.
- FirstRate canonical M1 normalization receipt:
  `D:\thericher-v2\model-artifacts\data-receipts\firstrate-free-intraday\firstrate-free-intraday-source-local-normalization-v1.json`
  (`sha256:374fc885b831b6a2aea59526e25f918ebe568414b018b621452c02d608f988be`).
- FirstRate source-local timeframe mechanics manifest:
  `D:\thericher-v2\model-artifacts\data-receipts\firstrate-free-intraday\firstrate-free-intraday-source-local-timeframe-mechanics-v1.json`
  (`sha256:aa83961f57f7fe373f9383874c3d294384dca895115ad7f447fb2371ec2528c3`).
- Norgate host readiness bridge receipt:
  `D:\thericher-v2\model-artifacts\data-receipts\norgate-host-readiness-bridge\bridge-norgate-host-readiness-20260818T230439Z.json`
  (`sha256:20cf9e2954bb567fa31a54d58cde6d61b50be0d86b4b345261e14136c1aa521c`).
- Fixed market-data contract inventory receipt:
  `D:\thericher-v2\model-artifacts\data-receipts\market-data-contract-inventory\market-data-contract-inventory-20260819-r1.json`
  (`sha256:17f2b0f7cf7e16a61b2c2006e806d6e9c8e6135d41e63bf073fe4cdd2fb55632`).
- FirstRate official source retrieval receipt:
  `D:\thericher-v2\model-artifacts\data-receipts\firstrate-free-intraday\firstrate-source-semantics-retrieval-v1.json`
  (`sha256:81954bfd6fde980dd63af92fafb6471830742cbb6871b9bdaf21c9ea6c81063f`).
- FirstRate review-bound interpretation receipt:
  `D:\thericher-v2\model-artifacts\data-receipts\firstrate-free-intraday\firstrate-source-semantics-interpretation-v1.json`
  (`sha256:055b4faa5b83dc85255eeacd84eb59db762992250fcb18eb5285bcf0de4d37e2`).
- Official KIS overseas-minute documentation confirms the reviewed request and
  cursor semantics but supplies no reviewed finality/as-of predicate. It keeps
  `provider_finality` and decision-time availability `not_observed`; it makes
  no KIS call or consumer change. Evidence:
  `D:\thericher-v2\model-artifacts\data\provider-documentation-retrieval\kis-overseas-minute-finality-surface-20260809-r1\source-retrieval.json`.
- A 2026-08-19 official-source recheck independently confirms the existing
  `NEXT`/`KEYB` minute-pagination semantics and separately documents that the
  related U.S. free current-price surface can receive next-day corrections. The
  latter is not a minute-route finality fact, so it reinforces rather than
  relaxes `not_observed`; it does not widen the measured QQQ/SPY cursor scope.
  Evidence:
  `D:\thericher-v2\model-artifacts\data\provider-documentation-retrieval\kis-overseas-price-revision-surface-20260819-r1\source-retrieval.json`.
- Public U.S. minute-source discovery receipt:
  `D:\thericher-v2\model-artifacts\data\provider-discovery\public-us-equity-intraday-20260819-r1\source-retrieval.json`.
- FirstRate free M1 acquisition receipt:
  `D:\thericher-v2\model-artifacts\data-receipts\firstrate-free-intraday\firstrate-free-intraday-20260819-spy-qqq-r1.json`.
- QQQ multi-timeframe completed-bar mechanics:
  `D:\thericher-v2\model-artifacts\data\source-local-qqq-mtf-resampling-mechanics-v1\20260807-qqq-mtf-r1\summary.json`.
- QQQ MTF canonical window matrix:
  `D:\thericher-v2\model-artifacts\data\source-local-qqq-mtf-window-matrix-v1\20260807-qqq-mtf-matrix-r2\summary.json`.
- Tiingo raw-D1 collection receipt:
  `D:\thericher-v2\model-artifacts\data-receipts\tiingo-etf-d1\4a2344b7ab8ec2eaf0b1a5e4afcd41e07cf0b4c14e13db64d07b41fd054883d2.json`.
- Broad D1 source-safe postrun receipt:
  `D:\thericher-v2\model-artifacts\data\kis-paper-daily-nas-broad-panel-postrun-v1\postrun-5b24100dc992a4fed2848593.json`.
- Tiingo IEX r1 runtime evidence:
  `D:\thericher-v2\model-artifacts\research\tiingo-iex-r1-representation-integration-v1\r1-cuda-20260810-r1\summary.json`.

## Handoff

When a later task-owned input qualifies, hand Engine Research only its exact
source-safe receipt pointer, source identity, target eligibility, split-ready
time geometry, availability/finality facts, and limitations. Do not choose a
model or construct a Paper order. The current terminal does not meet that
handoff condition.
