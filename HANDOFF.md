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

The completed `firstrate-m5-mean-reversion-after-cost-control-v1` evaluated one
predeclared, source-local 5m RSI mean-reversion rule against an always-flat
after-cost local-paper comparator. Its external `20260820-r1` run reattached
the fixed FirstRate source geometry, wrote only a precommit, aggregate summary,
and independent validation receipt, and was `rejected`: the rule beat flat in
zero of six SPY/QQQ nonzero-cost cells. All 12 rule/baseline cells were
`source: local_paper`, replayable, and terminal-flat; no raw events persisted.
The summary and validation SHA-256 values are respectively
`sha256:b437e8e39e9cb3963e13bf4778daee7e92d0de6c32cec6e9dac24e462f16266f`
and
`sha256:02f8f89200696d5f8bc0aac15d1d92141d0e076beb656e6ac06696a04418857a`.
No network, credential, KIS, broker, order, GPU, selection, ensemble, or
Paper-consumer path ran. This closes the fixed 14-period Wilder-RSI
30/50 long-only rule; do not tune its parameters or infer a KIS/Paper or GPU
consequence.

The completed `tiingo-d1-trend-mean-reversion-rotation-falsification-v1`
reattached its exact pinned Tiingo SPY/QQQ/IWM D1 snapshot and independently
validated its one external `20260820-r1` receipt. It stopped at its frozen
preflight as `input_unavailable/insufficient_validation_active_decisions`:
only 3 of the required 100 validation decisions were active, while 1,892 of
1,896 scheduled validation decisions were excluded by the frozen event or
discontinuity conditions. It made no performance, selection, point-in-time,
GPU, KIS, Paper, or live claim. The aggregate summary and independent
validation SHA-256 values are respectively
`sha256:f68bbd3cac1ccfbf1f4e4d6876ba3c28c5e9a8fa37324a20d19c252df26261cf`
and
`sha256:17b1ce1f5e18e8f525fb42bcfd2537d18c8d885b40ae3dc68816d3b8653a74d3`.
The completed `tiingo-d1-event-mask-coverage-audit-v1` independently bound
the rotation receipt and found no semantic contradiction: all 1,892 excluded
validation decisions were event-mask exclusions, with zero discontinuity-only
exclusions. Four validation contexts were unmasked, but only three carried a
signal; the event exclusions form five runs longer than 60 decisions. This
proves that this fixed all-ETF event window is structurally sparse on this
repeat source, not that the rule has a PnL result or that a mask change is
warranted. Its summary and validation SHA-256 values are respectively
`sha256:84ba51e3e7857f6e72dbf4552ecbe8496a6804e7b4f7d7b7970f4352081e1897`
and
`sha256:e7fbfdeedd7e55c91ac7a7048ec193dc24dd3352d660e57ef0a1b669b89a0bf9`.
The Tiingo rotation lineage is closed without retuning, GPU, KIS, Paper, or
live consequence. The completed
`norgate-trial-host-readiness-reconciliation-v1` reattached that exact prior
bridge, imported only the isolated local client, and observed
`input_unavailable/local_api_not_ready_updater_not_observed`. Its source-safe
summary and offline validation are respectively
`sha256:5c79a0430b789709df50136f6a1ea999836072c7483f6f1598fc80d43bb924ac`
and the same bound summary with prior receipt
`sha256:20cf9e2954bb567fa31a54d58cde6d61b50be0d86b4b345261e14136c1aa521c`.
No Norgate source rows, settings, credentials, network path, updater action,
KIS, broker, model, or GPU path ran. The narrow local prerequisite is to
install and run Norgate Data Updater; this is not a data-rights or
data-capability conclusion and must not be polled.

Claude's falsification-first direction check returned
`supported-with-limits` for a KIS Paper D1 prospective observation-pairing
measurement, and rejected both another same-source FirstRate rule draw and
waiting as a company objective. The next objective is
`kis-paper-d1-prospective-observation-pairing-v1`: add only the two-stage
decision-time/post-finality identity measurement for the existing QQQ/SPY v2
cache. It can disqualify revision-leaking input but cannot make a predictive,
GPU, Paper, or live claim.

The pairing implementation is now installed as
`thericher-kis-paper-d1-prospective-observation-pairing`. It has two KST
triggers, 08:15 and 23:20 Tuesday through Saturday, and a small external state
pointer under `D:\thericher-v2\model-artifacts\data\kis-paper-d1-prospective-observation-pairing\v1`.
It uses only the existing QQQ/NAS + SPY/AMS virtual-Paper daily route and v2
cache read-only; immutable receipts retain only the fixed source-contract hash,
session key, timestamps, and per-target canonical row hashes. Its container
wiring smoke was `not_due` at 2026-08-20T08:27Z, so it made no KIS request.
The approved offline reader now validates the current pointer for the
2026-08-24 completed-session first stage as
`input_unavailable/first_observation_unavailable` (receipt
`sha256:d814aadc4ccfb68eb727c47369bf47e5b5e39f51e2fd60433a77cddfef623c98`;
source contract `sha256:b7752aa22cc3b358b52c6fe2e6da72e1dc811b5a7078563de0c4201a68f9033d`).
It has no first-receipt binding or later observation, so it is not a pair
outcome. The source-safe Task Scheduler status is `Ready`; task exit is not
outcome evidence. The reader-owned `next_due` is `2026-08-25T23:15:00Z`.
A terse implementation drift check from Claude returned
`uncertain`;
therefore no observation is treated as a qualification result, and a later
Claude falsification check is still required before relying on an actual pair
outcome. A matching pair remains measurement-only; missing/mismatched data
disqualifies only that session.

The observer now writes a hash-bound source-safe `current.json` pointer only to
an immutable outcome receipt. Its offline reader independently revalidates the
pointer, referenced receipt, and, for a later result, the exact first-receipt
ID/hash, session, and first-observation hashes. The initial read-only host
check returned `current_pointer_unavailable`, meaning no actual result existed;
it made no KIS, credential, Docker, or cache call. The later approved
reattachment found the scoped first-stage `input_unavailable` receipt above;
it is neither `first_recorded` nor a validated later receipt. A missing pointer
is unknown, never an inferred match or failure.

The latest task-owned QQQ/SPY intraday-head terminal is dispatcher-complete but
its source-safe current-session coverage is still
`incomplete/current_session_short`; metadata-only inspection reports 37
retained chunks and zero complete 390-minute sessions. To measure whether this
is only the fixed four-page cap, the existing runner now keeps its normal cap
at four pages per target and uses eight only during a regular-weekday
16:20--20:00 Eastern post-close invocation. It adds no Task, route, rate
change, retry loop, or manual run. Claude CLI supplied no verdict
(`review_unavailable`); the next immutable scheduled receipt is the sole kill
test, and a short outcome does not auto-escalate.

The completed `kis-daily-pair-forward-v2-fresh-cache-bootstrap-v1` created the
isolated QQQ/NAS + SPY/AMS KIS Paper D1 cache at
`D:\market_data\us_equities\kis_paper_private\daily-qqq-spy-forward\v2`
without mounting, copying, clearing, or relabeling v1. A network-disabled
preflight was `collection_required`
(`sha256:9aaee83455c9a93906ff534a46d28457bd6aeb125b3f0bf251dc6a6bf4a1d976`),
one serial daily-market-data collector was `ready`
(`sha256:0db2b9fa0dd1b475f971fee33009ed576e03c877fb0e63d19a004db4a3a95d49`),
and a fresh credential-free preflight reattached `cache_current`
(`sha256:d91a68988a3ef248c4ea2c752b27e4ec3c7f53746dd47a06592dcb4e15e6835a`).
The v2 cache has 18 common sessions and is still collection/provenance only:
point-in-time availability, provider finality, and corporate-action
qualification are unobserved, so it cannot clear v1 quarantine or create a
model, GPU, Execution, Paper-consumer, or live claim.

The completed `firstrate-5m-after-cost-control-v1` independently reattached
the existing canonical SPY/QQQ FirstRate source, UTC-anchored complete 5m
windows, and frozen chronological 60-bar/61-bar-embargo contract. Its external
run `firstrate-5m-after-cost-control-v1/20260820-r2` wrote a precommit,
CPU-only per-symbol L2 model, source-safe aggregate summary, and independent
validation receipt. The L2 control did not beat `always_flat` in any of its six
SPY/QQQ nonzero-cost cells (1/3/5 bps per side), so Validation classified it
`rejected`. All 18 model/baseline replay cells were `source: local_paper`,
replayable, and terminal-flat. No network, credential, KIS, broker, order,
GPU, selection, ensemble, or Paper consumer path ran. The summary and
validation SHA-256 values are respectively
`sha256:249a55dc53605e5381cfbaaef370ce9d36302c93594abc421a65b6685857fb2c`
and `sha256:9d6950afdf9051aafa94e82a43eadc4ab6bf2438c10c1b0a63fb41dfe19e2de6`.
This closes that L2 lineage; it is not evidence that a different source-local
technical rule, a GPU architecture, or a KIS consumer is ready.

The completed `firstrate-m5-trend-rule-after-cost-control-v1` reused that exact
source-local 5m geometry but evaluated only the frozen calibration-free
`SMA(20) > SMA(60)` long rule. Its external `20260820-r1` run wrote only
precommit, aggregate summary, and independent validation evidence. The rule
did not beat `always_flat` in any of six SPY/QQQ nonzero-cost cells. All 18
rule/baseline replays were `source: local_paper`, replayable, and terminal-flat;
the summary and validation SHA-256 values are respectively
`sha256:539463a0d6cb84ba16fd75e750493277adc5e9f00f94a5e51f00d1cb44a78d00`
and `sha256:dfc5fab61fb5c440127d9e71eb49d64006c7bbdc77b09e213f94354fa29e8124`.
No training, GPU, network, credential, KIS, broker, order, selection,
ensemble, or Paper-consumer path ran. This closes only the frozen trend rule;
do not tune its windows, direction, threshold, costs, or exit after this
outcome.

The separate completed `firstrate-m5-mean-reversion-after-cost-control-v1`
reused the same source-local 60-bar/61-bar-embargo geometry but evaluated only
the frozen long-only Wilder-RSI(14) <=30 entry and >=50 completed-bar exit
rule, with a predeclared final next-bar flatten. Its `20260820-r1` run was
`rejected`: it beat `always_flat` in zero of six SPY/QQQ 1/3/5-bps-per-side
cells. All 12 aggregate-only local-paper cells reattached as replayable and
terminal-flat. This closes only this fixed RSI lineage; no tuning, GPU,
selection, ensemble, KIS, Paper-consumer, or live consequence follows.

The 2026-08-19 UTC fixed ETF snapshot is now external at
`D:\market_data\us_equities\fixed_etf_prospective_lineage\canonical\tiingo_standard_eod\snapshot=2026-08-19-tiingo-standard-eod-prospective-r1`.
Its offline loader reattached dataset identity
`sha256:537211067196a91d24dfaab229666decc96108e17c4de89e8059d02ed27c787c`
and manifest identity
`sha256:d02c5c1f7bcd47148b491273fad613637ddee8972ad8bb1bdf79dd3ab7d5426d`.
It retained exactly three fixed-symbol responses, 72 normalized rows, and a
2026-08-12 source-as-of boundary. The existing closed contract leaves every
model, training, campaign, ranking, order, GPU, KIS-recovery, Execution, and
Paper eligibility false. Claude's compact code-level challenge was
`supported-with-limits`: provider freshness still does not establish
point-in-time decision availability.

The completed `tiingo-prospective-eod-refresh-v1` passed 6 focused prospective
EOD tests and the goal-boundary authority suite as `3218 passed, 19 skipped` in
42m31s, plus Ruff, both credential-free Compose parses, and `git diff --check`.
The only external action was the fixed three-request Tiingo acquisition; no
KIS, broker, order, live, or model action occurred.

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
Paper, or GPU consumer. The later-terminal task remains an owned non-foreground
monitor. The isolated IWM/AMS current-head cache now reattests offline as one
head chunk with verified index/manifest/raw integrity and aggregate 1m geometry
only. The bounded caller-derived, header-gated continuation probe completed
with one accepted head and no recognized continuation header, so it made no
second request. Its source-safe aggregate receipt is
`sha256:99068ebe69ee7d5300eeb2671eed433df87830db980947ac26d4b97a3b267cea`.
This closes only that endpoint expansion path: do not retry it, start a
collector, infer history/finality/availability, or create a predictive/Paper
consumer.

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

The completed `kis-intraday-head-static-task-contract-reattest-v1` independently
attached the installed `thericher-kis-paper-intraday-head` Task and checked-in
first `session-capture` runner/Compose route to one source-safe `matches` result:
enabled, action, triggers, settings, and source all match at `task_state: ready`.
The external receipt is
`execution/kis-paper-intraday-head-static-contract-v1/static-contract-20260819T1234034490997Z-931b776ddcdc.json`
(`sha256:12d79514199a50ae7ec6bbd27abfbe90e3fb3826fe505ba762f6122fadc88e95`).
It read no current marker pointer and invoked no Task, Docker, KIS, collector,
broker, or scheduler. This rules out only static contract drift; it does not
prove Scheduler origin, Docker/container entry, collector/provider cause,
session completeness, finality, or model eligibility. The existing scoped
`reason_unavailable` classification remains unchanged.

The next bounded objective is `kis-intraday-head-collection-dispatch-boundary-v1`:
after a Claude falsification-first challenge, add only closed source-safe
host-side dispatch boundary evidence for future task-owned runs. It must not
change the existing task timing, collector behavior, Docker profile, KIS route,
or conditional Paper branch.

That follow-on review is complete as no-change. Claude returned
`supported-with-limits`, and the source check agrees: for an already bound
terminal, the runner captures the return from its exact
`Invoke-HeadProfileService`/host Docker command before it writes
`collection_outcome`. A new pre/post marker would neither prove container entry
nor identify a collector/provider cause, while adding another diagnostic step to
the pre-collection path.

The completed direct host collection capability probe then used exactly one
existing `session-capture` collector invocation for `QQQ/NAS` and `SPY/AMS`
with the four-page cap. It completed with `paper_only: true` and
`route_class: kis_paper_market_data`; its exact unbound source-safe receipt is
`us_equities/kis_paper_private/intraday-head/v1/session-capture/20260819T130238145868Z-50e04e46fdb2e4e0.json`
under `D:\market_data` (`sha256:50e04e46fdb2e4e0ceb65673066751fdb37bfaa5b53b8007f4ddb8f20316354a`).
This establishes only that the direct host collector/KIS data path completed
the bounded scope and persisted its safe aggregate; it does not prove a
Windows Task/Scheduler, Docker/container, provider-finality, coverage, or
model-input fact. Claude's next falsification-first review returned
`supported-with-limits` for one exact existing Compose-service probe, so the
next objective isolates that container path without invoking a task or a
downstream consumer.

The first exact direct Compose-service probe completed with a scoped nonzero,
not a Docker or provider failure claim. Its `session-capture` receipt is
`us_equities/kis_paper_private/intraday-head/v1/session-capture/20260819T131812782029Z-0caa1e559078804d.json`
under `D:\market_data` (`sha256:0caa1e559078804dc2d269a9aa2abf708e9f169783f775378fdf0d17250e2bcc`):
both allowlisted targets are `rejected/token_request_not_due`. The collector's
shared source-safe token gate had a separate token-start reservation at
`2026-08-19T13:15:01.522769Z` with a five-minute due time; it identifies no
worker and proves only that this container attempt yielded before a token POST.
No Task, account, order, Paper consumer, or live route ran. The next objective
is one new post-gate Compose attempt with a non-mutating due precheck and its
own atomic in-service claim; it has no foreground wait or retry loop.

That post-gate attempt completed and exercised the existing collector through
its retained-cache conflict protection. Its exact safe receipt is
`us_equities/kis_paper_private/intraday-head/v1/session-capture/20260819T133017088958Z-ed596cfe5f8dc959.json`
under `D:\market_data` (`sha256:ed596cfe5f8dc95977c961d48927e9266ba6353e82578f2a2f76b26acc1b80e4`):
both targets are `rejected/minute_duplicate_conflict` with
`conflict_origin: retained_cache` and `retained_head_conflict_disposition: quarantined`.
The installed path preserved immutable raw bytes and quarantined only the
conflicting active head entries; no manual cache change, Task, account, order,
consumer, or live route occurred. This is not provider-finality or qualified
data evidence. Claude returned `supported-with-limits` for one later,
independently fetched clean-capture attempt using the same recovery path; a
second retained-cache conflict closes that exact recovery path without a loop.

The permitted later clean-capture attempt then completed through the exact
existing Compose service. Its unbound source-safe receipt is
`us_equities/kis_paper_private/intraday-head/v1/session-capture/20260819T134229353199Z-c87d4ebfde0e7545.json`
under `D:\market_data` (`sha256:c87d4ebfde0e7545e7907936c8eb506c1e3aa7514ef6d9ea86e9a36d7b4a522e`):
both fixed targets are `collected`, with no failure or conflict category. The
receipt hash, filename timestamp, unbound direct-Compose identity, external
storage scope, and `paper_only` market-data route were revalidated offline.
This closes the exact cache-recovery path; it does not establish Scheduler
origin, a complete session, provider finality, qualified research input, or a
Paper consumer.

The daily-broad continuation capability check is also closed. Its non-network
preflight reattached the 2,119-target current-listing registry, and its one
allowed continuation completed with zero chunks, accepted pages, failures, or
remaining targets. The exact source-safe receipt is
`data/kis-paper-daily-nas-broad-v1/run=20260819T140140890766Z-90568a0332da/receipt.json`
under `D:\\thericher-v2\\model-artifacts`
(`sha256:065e6b4189e172f78047304b21d81361355eebe9f3c8db7d2b2935f3beb430a3`).
Its reattached index is unchanged at generation 26,368: 1,089 targets are
`complete` and 1,030 `source_limited`. No KIS client or market-data request was
constructed, and no account/order/live route ran. Do not start a long worker
for this exhausted historical cursor; a separate QQQ/SPY forward cache is the
next bounded current-data path.

The first bounded QQQ/SPY D1 forward-cache refresh is also closed. Its
networkless preflight required the 2026-08-18 completed session and wrote
`data/kis-paper-daily-pair-forward-v1/run=20260819T141629274707Z-85e3ed4ed5bd497e/receipt.json`
under `D:\thericher-v2\model-artifacts`
(`sha256:7987f5a89f3ec8631646ece7718f0433ae7308aad9b27060cf0efffa4ad7028f`).
The one permitted collector then closed `deferred/token_request_not_due`, with
zero new accepted pages and zero changed targets; its exact source-safe receipt
is `data/kis-paper-daily-pair-forward-v1/run=20260819T141651910431Z-7298440b05e84736/receipt.json`
(`sha256:f3305c86da4ce345beed1e734f30e614356827ed54f678e3dcf87596c32f5914`).
The offline cache reader reattached seven common forward sessions and two
unchanged target streams. The deferral contract constructs no KIS client in
this branch, and the added cache-current regression test proves preflight also
cannot read KIS configuration or construct a client. This does not refresh a
daily input, prove finality or point-in-time eligibility, or create a research,
Paper, PnL, or live consumer; the existing ready task owns its next due run.

The frozen historical KIS D1 CPU baseline now has independent QQQ and SPY
reproductions. Both reattached the same verified 4,756-bar common-panel hash,
completed the fixed two-baseline by two-phase matrix, and retained only
`local_paper` fills. The external QQQ contract/summary hashes are
`sha256:2f40d0fdbb34aef36a35f181f1e1e52c80fa623326dc91e5a7cf4257ed48bed6` and
`sha256:d1731138d8f2898b75ecd90ab41c4c5754d22fa380f8580dd79d61cd78273c39`;
the SPY summary hash is
`sha256:852fe248251eea52b25e3bbf7796dc9a0881b2a8e78ee536246b4583e9f15f9f`.
Every fixed after-cost baseline result was negative; the closest was QQQ
`previous_bar_direction` on the chronological descriptive holdout at `-0.3965`.
This is a useful negative control, not a profitability claim, selected model,
KIS request, broker result, Paper action, or GPU allocation.

The one frozen QQQ/SPY D1 L2 logistic control also completed offline on the
same 4,756-bar common-panel identity. Its external precommit, model-parameter,
and sanitized-summary hashes are
`sha256:60ac9f662014bc76067945befed7877a345099088f5e3defd4747eacf9dd3b9a`,
`sha256:7db2456aa6f0368008becd59d7d70b3580b2f0f5aeb0db4aafda5f858f3a8545`,
and `sha256:143f7ce60cc74fcac61cf004245730b78c0a34acf5e8003d326bd267c1492213`.
The precommit preceded fit and validation replay; validation labels were
excluded from fitting, and all two model plus six comparator replay cells used
`local_paper`. Its after-cost QQQ/SPY replays were `-109.2703` and `-139.3587`,
both below their fixed previous-bar-direction comparators. This is a failed
descriptive classical-ML control, not a selected model, GPU allocation,
profitability result, broker PnL, Paper action, or live claim.

The one frozen QQQ/SPY D1 shallow regime-tree reproduction also completed
offline on that same hash-pinned panel. Its external precommit and
sanitized-summary hashes are
`sha256:94432ab794299a3a02504e0061f7b0bc6d7220c7c2295ca7192ff3d9e499b59f`
and
`sha256:8bb7f4c7a487cb399d42442a87f467330e9cebbae36cbddd672ef97d0048cd50`.
The precommit preceded the development-only fit; validation labels were
excluded, no fitted estimator was serialized, and all two model plus six fixed
comparator replay cells used `local_paper`. Its after-cost QQQ/SPY model
replays were `-45.8296` and `-73.7783`, both below their fixed
previous-bar-direction comparators. The nonlinear tree lineage is therefore
closed as failed descriptive control evidence: it creates no selected model,
ensemble, GPU appointment, broker PnL, Paper action, or live claim.

Claude's scoped falsification-first review returned `supported-with-limits`
for the completed Data-only QQQ/SPY D1 forward-cache causal-qualification
predicate. Its synthetic fixture was qualified only with every explicit
condition and every single-condition ablation failed closed. The one current
cache run wrote
`data/kis-daily-forward-causal-qualification-v1/run=20260820-kis-daily-forward-causal-qualification-r1/receipt.json`
under `D:\thericher-v2\model-artifacts`
(`sha256:9b361addc7e76dd5cd8ff6bf9800077c8a8866f3b5a21eeedbeb6d2a2dcdc3cf`).
Source/pair identity, complete-calendar continuity, and chronological boundary
are satisfied; named clock/session, decision-time availability, and provider
finality remain `not_observed`, so the aggregate is `input_unavailable`. It did
not collect, construct a KIS client, read credentials, change a schedule, or
create a Research, GPU, Paper, or live consumer.

Claude's next falsification-first review returned `supported-with-limits` for
one existing KIS Paper QQQ/SPY D1 collector invocation. Its static consumer
check found no Research or Execution use of this pair-forward cache that treats
`latest_session` as decision-time availability or provider finality. The next
bounded step may therefore advance cache coverage and exercise the token gate,
but it must remain one-shot and no result can alter the three `not_observed`
runtime conditions without separate retained evidence. A successful collection
is not a model, GPU, Paper, or promotion event.

That one-shot preflight returned `collection_required` at
`data/kis-paper-daily-pair-forward-v1/run=20260819T155737898831Z-4b91351878114c11/receipt.json`
(`sha256:77de03be7d6f4f1ce0fb567244e239966869c39cc50f75f2be361369d7dc9ef9`).
Its exactly one collector call returned `unavailable/collector_unavailable` at
`data/kis-paper-daily-pair-forward-v1/run=20260819T155753946326Z-d0ec4d21d99446fa/receipt.json`
(`sha256:7bba8e74781c803bcdcaaef44aaabdc6b4021b0f039919296618430c996a59b3`).
The unavailable receipt has no cache payload; the existing cache remains
offline-readable with seven common sessions, so no causal requalification or
consumer change followed. Claude's resulting `supported-with-limits` review
requires fixed source-safe `control_gate`, `environment`, `collection`, or
`commit` classification plus a no-network/no-write readiness result before a
later one-shot collector may be considered. No exception text, secret/config
identity, raw row, account, order, Paper, GPU, model, or live fact is retained.

The completed stage-discrimination package now passes synthetic faults for all
four fixed stages and has one networkless readiness receipt at
`data/kis-paper-daily-pair-forward-v1/run=20260819T161924502292Z-333ce65960854fcd/receipt.json`
(`sha256:e64e4888b2f5e4937df1712c2bb72f3bf6f6d1410a55bef1d9ba9d09254ee4e5`).
It is `ready/aggregate_ready`, token-due, rate-open, and records no network or
cache write. Its exactly one allowed collector call wrote
`data/kis-paper-daily-pair-forward-v1/run=20260819T161956811379Z-4948e7f7e87b4fe0/receipt.json`
(`sha256:b00e687001ff988bf1e2b32e53ee9c5eebf7585bdacc33b057259c64f50870e0`)
as generic `unavailable/collector_unavailable` with no cache payload and no
`failure_stage`. That receipt does not attest the stage-aware runtime image, so
it is not a stage/provider/finality/availability conclusion and was not
retried. The collector image was rebuilt from the workspace without another KIS
call. The next bounded Data/Infra package is source/image provenance for this
existing service; it must not call the collector, reinterpret this receipt, or
change causal, Research, Execution, Paper, or live eligibility.

Claude's follow-up drift check returned `supported-with-limits` for the runtime
provenance repair. Its constraints were adopted: the contract fingerprint lives
inside receipt `payload` to preserve the causal reader's exact top-level schema,
and it hashes only an in-source frozen stage contract rather than file bytes,
environment, paths, timestamps, or any private input. The three pair-forward
Compose services now share the local image tag
`localhost/thericher-v2/kis-paper-daily-pair-forward:local`. After a local build,
one credential-free `network_mode: none` preflight wrote
`data/kis-paper-daily-pair-forward-v1/run=20260819T164013025667Z-6219bc10fc8c4dd4/receipt.json`
(`sha256:e5c2cf9be1bace915d8c3deb19a57ab5a5f0cc1d7bff634afbeb8f2a38090a7a`)
as `collection_required`; its payload contract hash matches current host source.
It did not read credentials, call KIS, write the cache, run readiness, or invoke
the collector. This establishes only the fixed diagnostic contract, not full
image freshness, data availability, finality, causal qualification, or a
Research/Execution/Paper consumer. The next bounded Data objective is one fresh
stage-aware collector invocation, with no automatic retry.

The fresh shared-tag one-shot was run exactly once after a new Claude
`supported-with-limits` recheck. Claude narrowed the evidence claim: a shared
local tag establishes only the selected tag name, and the static contract hash
establishes only the stage contract, not immutable image identity, freshness,
configuration, or source-build provenance. The collector was run with no build
or pull request and wrote
`data/kis-paper-daily-pair-forward-v1/run=20260819T165517911332Z-b52ac5d46a704e12/receipt.json`
(`sha256:804786626d4fe10dbac971d21f563a54298e9afae92d7beb69c0c4caef8b74cf`)
as `unavailable/collector_unavailable/failure_stage=commit`. Its payload
contract hash matched the preflight and current host static contract hash. The
receipt has no cache payload, no raw rows, credentials, or account data, and its
non-market-data route flags are all false. A credential-free offline reattest
still validates the seven-common-session cache; no cache file or index write was
observed in the invocation time window. The stage does not expose or establish
the exact commit cause, so this one-shot is closed without retry, causal
qualification, Research, Execution, Paper, or live consequence. The next
bounded package is source/fixture-only fixed commit-failure classification.

Claude's classification-boundary review returned `supported-with-limits`. The
implemented v2 static contract adds an optional payload-only
`commit_failure_kind`: fixed-order `cache_contract`, then `storage`, then
`validation`; an unmatched exception omits the field. It never serializes the
exception, message, class name, path, or dynamic value, and it is rejected on
every non-`commit` stage. The static v2 contract hash is
`sha256:82a72fb357f6d7ad8d3d8bb447cc4310461bdb9226afbca26e0e1ad9b42a8c1c`.
Focused fixture tests cover all three mappings, the `OSError`-before-`ValueError`
ordering, a private-detail canary, top-level schema stability, and no leakage to
a later success receipt. This does not classify the completed v1 receipt or
claim that the three categories exhaust runtime failures. It made no credential,
KIS, Docker, cache-write, scheduler, Research, Execution, Paper, or live call.
The next bounded Data action is a fresh credential-free v2 preflight; only its
matching `collection_required` outcome can permit one new collector invocation.

That v2 preflight completed at
`data/kis-paper-daily-pair-forward-v1/run=20260819T172512279495Z-e9baed100e2548a8/receipt.json`
(`sha256:cf95c93741330d60d95dc040e12446d3a34e899d8a3565b82cb0f8b2743e6ec2`)
as matching `collection_required`. The existing shared tag was built once, and
its locally observed image identity was unchanged immediately before and after
the one collector call; that is not immutable image provenance. The one
collector wrote
`data/kis-paper-daily-pair-forward-v1/run=20260819T172546233523Z-2f2f777f8c454d19/receipt.json`
(`sha256:0c28203f24a098685f8068433e2250f14c1774bde99e5e87e64de1862ae53d42`)
as `unavailable/collector_unavailable/failure_stage=commit` with fixed
`commit_failure_kind=cache_contract`. It has no cache payload and all
non-market-data route flags remain false. The offline reattest still binds the
same cache and index identities with seven common sessions; no cache-file or
index mutation was observed in the invocation window. This narrows only the
failure family, not its exact cause, data availability, finality, causal
qualification, Research, Execution, Paper, or live eligibility. No retry ran.

A short architecture/recovery Claude invocation for the next diagnostic did
not return a verdict before it was stopped, so it is `review_unavailable`, not
agreement. The next bounded package is source/fixture-only fixed commit-phase
diagnostics for future `cache_contract` outcomes; it makes no KIS, Docker,
credential, cache-write, or retry call.

That local-only package is complete. The v3 static contract hash is
`sha256:219a3a13d1419f9b65dc34f1d6fa3a3ffcb534b045b1d1729308cb8d944e5893`.
Only a future `commit/cache_contract` outcome may carry optional fixed
`commit_failure_phase`: `cache_prepare`, `snapshot_persist`, `index_persist`,
or `cache_reverify`. The cache writer attaches a phase at the four static
operation boundaries while preserving the original cache exception type and
message for callers. The collector accepts a phase only with `cache_contract`;
success, non-commit stages, storage, validation, and earlier receipts omit it.
Fixture tests cover every boundary, field omission, and a private-detail
canary. No credential, KIS, Docker, cache-write, scheduler, Research,
Execution, Paper, or live action occurred. This establishes a future diagnostic
surface only; it does not infer a phase for the v1 or v2 receipt.

Claude's v3 collection recheck was `supported-with-limits`: the host must
enforce the exact-one and matching-hash conditions, and a gate-deferred execute
path can still alter a cache observation without collecting pages. Codex applied
both limits. The v3 credential-free preflight wrote
`data/kis-paper-daily-pair-forward-v1/run=20260819T175759151923Z-5abf449a6416418f/receipt.json`
(`sha256:6fa27ec40b8009b76c0c31fe6210a4ad8814676566bc5f6cc442fa71a011fd5a`)
as matching `collection_required`; it had no cache payload and all
non-market-data route flags were false. Exactly one existing collector then
wrote
`data/kis-paper-daily-pair-forward-v1/run=20260819T175852692208Z-6dd72fc496fc48d5/receipt.json`
(`sha256:cd1b1222c61da98aa12091b8a61bd153cd91e2943d0c79c98dafe4340eb33dc3`)
as `unavailable/collector_unavailable/failure_stage=commit`, fixed
`commit_failure_kind=cache_contract`, and fixed
`commit_failure_phase=cache_prepare`. The tag was locally unchanged across that
one call, but this is not immutable image provenance. The receipt retains no
cache payload or forbidden market/private fields; its static hash matches host
v3. The cache and index reattach to their prior identities with seven common
sessions and two seven-row target streams; no file mutation was observed in the
bounded invocation window. No retry ran. This does not establish the exact
prepare cause, data availability, finality, causal qualification, Research,
Execution, Paper, or live eligibility.

The next bounded package is source/fixture-only `cache_prepare` subphase
diagnostics. It may add only `cache_access`, `cache_state_load`, or
`incoming_merge` for a future matching failure. It must preserve v3 as
subphase-unknown and make no KIS, Docker, cache-write, or retry call.

That package is complete. The v4 static contract hash is
`sha256:95e0ec0fd7408e237cbb79e4010e152291dd4322f58133bd4c46207c258dc893`.
Only a future `commit/cache_contract/cache_prepare` outcome may carry optional
`commit_failure_prepare_subphase`: `cache_access`, `cache_state_load`, or
`incoming_merge`. Each value names only the fixed source region where the
cache exception surfaced; it is not an exact cause claim. An unclassified
boundary leaves the field absent. The cache error's type, message, and args are
preserved, and the collector exposes no dynamic exception or cache detail.
Claude's falsification-first review was `supported-with-limits`: do not treat a
region as causation and do not add incident-shaped values. The v3 receipt stays
subphase-unknown. This local package made no credential, KIS, Docker,
cache-write, scheduler, Research, Execution, Paper, or live call.

The goal-boundary parallel suite initially exposed an unrelated fixture race:
its fake snapshot observer shared the production global mutex with a task-owned
read-only observer. The observer keeps that production default, while fixtures
now pass a unique mutex name. The repaired authority run completed
`3206 passed, 19 skipped, 51 warnings`; this changes no real observer,
schedule, Docker route, KIS call, account read, or order capability.

Claude's v4 recovery check returned no output, recorded as
`review_unavailable`, not agreement or a hold. The credential-free v4
preflight wrote
`data/kis-paper-daily-pair-forward-v1/run=20260819T183535741410Z-6454fe31110444e3/receipt.json`
(`sha256:e24e124b7e2ab6ec50496b5fc9a70ce21198f1483606527b442e9c749cf9029f`)
as matching `collection_required`; its non-market routes, network requests, and
cache writes were all false. The one permitted collector then wrote
`data/kis-paper-daily-pair-forward-v1/run=20260819T183649887588Z-b72198c4d5344bba/receipt.json`
(`sha256:8100bf8cccc02afa88124c05a731ae53113f99075761c5fbe8bb657a3416e832`)
as `deferred`. Its cache-bound target aggregates record `auth_rejected` for
QQQ/NAS and `token_request_not_due` for SPY/AMS; only the daily market-data
route is present and every non-market route is false. Network use is not
recorded for this collector receipt, so it is not inferred. The cache/index
hashes changed with the deferred state but reattach to the receipt; seven common
sessions and two seven-row streams remain, and the optional v4 subphase is
absent. No retry ran. This is not a causal-input, Research, Execution, Paper,
PnL, or live conclusion. The next package isolates the KIS Paper authentication
path with one bounded, source-safe capability probe rather than another daily
collection retry.

Claude's authentication-probe challenge returned `supported-with-limits`: the
transport-level token claim is atomic, but an advisory due check can lose a
race after the two Paper app values enter process memory. The probe therefore
tests that this race sends no token request and writes neither values nor a raw
body. The one permitted virtual-host token-only probe wrote
`data/kis-paper-daily-pair-forward-v1/kis-paper-auth-capability-probe-v1/auth-capability-20260819T190601865051Z/receipt.json`
(`sha256:d07e12f8ca521ca32cc00a4a0f81625ad5b503fa0505bad026969aca95db8261`).
Its hash reattached as `authenticated` with no reason, a 2026-08-19T19:00Z
time bucket, and token-only/Paper-only scope; market-data, account, order,
live, token-retention, credential-write, and raw-body-retention flags are all
false. This proves one bounded KIS Paper token capability only. It does not
reclassify the v4 collector, establish daily-page availability, finality,
causal input, Research, Execution, Paper, PnL, or live eligibility. The next
package uses the existing networkless Paper configuration/gate readiness route
and, only if it is currently ready, one existing QQQ/SPY D1 collector
invocation without a retry loop.

The v5 readiness receipt is
`data/kis-paper-daily-pair-forward-v1/run=20260819T191313847774Z-fefb0b409c2c4366/receipt.json`
(`sha256:f1d833bdf8aa775919f1793d2025ab2b530d251c13e3da22eb81a70a2c6ba7ab`).
Its hash and v4 static contract reattached as `ready/aggregate_ready`, with
`token_request_due: true`, `rate_gate_deferred: false`, and no network, cache
write, account, order, or live route. It validates only the named Paper app
configuration in process memory. Claude's collection review returned
`supported-with-limits`: those gate fields and the host's zero active collector
fact must be checked at dispatch time, while the collector's own atomic gate
remains authoritative. The one permitted v5 collector then wrote
`data/kis-paper-daily-pair-forward-v1/run=20260819T191401404530Z-df12344aeec246ec/receipt.json`
(`sha256:a10e42f5a44753c67bf483414005d98b5171341998926b10a2a5f9dc85100910`)
as `unavailable/collector_unavailable/commit/cache_contract/cache_prepare/`
`incoming_merge`. Its hash and route isolation reattached; no cache payload was
present and all non-market routes were false. The verified current cache/index
identities and seven-common-session aggregate exactly match the v4 deferred
receipt, so this failed attempt did not mutate retained data. No retry ran.
Source inspection makes duplicate conflicting overlap the candidate inside that
fixed region, not a proven row-level cause. The next package is source/fixture
only: define a revision-preserving forward-merge policy before another KIS call.

That source/fixture-only overlap package is complete. A canonical exact
duplicate is idempotent even when it is reconstructed as a new object. A
conflicting retained session preserves the existing row, records only a
count/category, and leaves that target `input_unavailable` with
`daily_retained_revision_conflict`; it may retain a strictly later append but
cannot clear itself through a later ordinary collection. An unseen interior or
older session and a conflicting duplicate inside one incoming payload remain
structural cache-contract errors. Causal qualification now rejects any
non-`ready` target at its read boundary. Claude returned
`supported-with-limits`: no raw-value hash was added, quarantine is durable,
and the consumer gate prevents a conflicted target from becoming a model input.
No credential, KIS, Docker, external-cache, scheduler, Research, Execution,
Paper, or live action ran. The next collector-facing package must be an
explicit bounded recovery/re-fetch contract.

That one post-policy fixed-pair observation is complete. Its offline preflight
receipt is
`data/kis-paper-daily-pair-forward-v1/run=20260819T215118439029Z-e468f94edded4f86/receipt.json`
(`sha256:91206b61150364513ecaedaa2591253be4721abbc37a0cac9c6e2eca69e54757`)
with `collection_required`. Exactly one collector then wrote
`data/kis-paper-daily-pair-forward-v1/run=20260819T215122140472Z-304d6943bbf146d1/receipt.json`
(`sha256:85516c0e8ce93a9fb4396afd9f53f33ed37005dade4e998bdc4dd1f307a692c0`)
as `partial/resume`: two accepted pages, two retained-revision conflicts, two
quarantined targets, and eighteen common sessions. Both fixed targets are now
`input_unavailable/daily_retained_revision_conflict`; the receipt records the
daily-market route only and every account, position, quote, order, and live
route false. The offline causal receipt
`data/kis-daily-forward-causal-qualification-v1/run=post-reconciliation-observation-20260819-r1/receipt.json`
(`sha256:40cf5a8487fd7144304f8e056aebf6d93811a3ff7051364c207f4025c4e0105a`)
is `input_unavailable` for source-pair identity plus the existing named-clock,
decision-time availability, and provider-finality gaps. A same-route refetch is
not independent recovery evidence and does not clear either quarantine.

The first direct runner invocation failed before its preflight because a
PowerShell parameter default evaluated before its script root was available; no
Docker or KIS call ran. The runner now resolves an empty `ProjectRoot` after
parameter binding, matching the installed task's already-explicit root, with a
fixture assertion for the resolved default path.

The post-reconciliation observation passed its focused 48-test group and the
goal-boundary authority suite as `3218 passed, 19 skipped` in 42m13s, plus
Ruff, both credential-free Compose parses, and `git diff --check`. Verification
made no additional external, KIS, broker, credential, or scheduler call.

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
| Execution | The 2026-08-20 23:35 KST owned quote-session receipt reattached offline as `canary_completed -> cancelled / clean`, `paper_only`, with attribution `not_eligible`; its source-safe session/lifecycle identities are `sha256:41753195259eac17dbc852775dc8511bb5e5803f475b327a505c19debcedfc4d` and `sha256:a36202c198a07a5f402199fcb93c362579ebd13f9c4ee7209a76ed87c9d29cd3`, and the direct receipt records only an acknowledged order-reference category. The current credential-free runtime projection is `unknown`, so it supplies no additional current state. The broker-free event replay additionally has a strict FIFO decision-PnL projection that binds valid local fills to accepted local orders and retains entry/exit decision roles plus pair totals. Its pure receipt resolver attaches only exact opaque receipt lineage and fails closed on missing, duplicate, role, or instrument mismatch. The 2026-08-11 session/direct readers bind the same opaque lineage as `canary_completed -> outcome_unknown / unresolved`, `paper_only`, with attribution `unavailable` (session `sha256:1679c76e0c99b565fa01c6cb53f14446dfc0ea0b93d348d48f505df486d09ce9`; lifecycle `sha256:5e0e3368ef9e28dc1770cad81fed7470b577a7f8f91941ef58cdc0f042d06b7a`). No predeclared source-safe prior-reconciliation pointer or private durable-state binding was available, so no repeat KIS reconciliation ran. | The exact KIS runs prove neither a fill, PnL, alpha, nor model result. The local projection is only arithmetic provenance, not broker PnL or causal credit. Do not resubmit either durable intent. The 2026-08-11 state remains scoped `outcome_unknown`; a future exact-recovery package needs an explicit durable binding and prior-attempt proof before another broker read. |
| Data | The isolated IWM current-head cache reattached offline as one `head` chunk with `51` complete bars, `17` adjacent 1m pairs, `33` non-adjacent pairs, and a `660`-second maximum interbar interval. Its external source-safe mechanics receipt is `sha256:7dbdae99adaf1e19fe1c3d6bd2760edb71cae2cb7c737c519a5b5f3259e50818`; no raw rows were emitted. The explicit caller-derived probe then accepted one head with no recognized continuation header and wrote aggregate-only receipt `sha256:99068ebe69ee7d5300eeb2671eed433df87830db980947ac26d4b97a3b267cea`. | Default IWM remains one page. This exact continuation path is closed with no retry, schedule, raw cache, cadence/history/finality/availability inference, predictive input, Paper input, or GPU consequence. |

## Ready / Owned / Due

| Work | Owner | Status |
| --- | --- | --- |
| Invocation receipt reattachment | Data / Codex | Complete: the exact fresh marker, terminal, and schedule receipt bind a `collection_exit_nonzero` task stage. Its external evidence pointers are `execution/kis-paper-intraday-head-invocation-v1/intraday-head-20260818T1728005721271Z/terminal.json` and `execution/kis-paper-intraday-head-schedule/intraday-head-20260818T1728005721271Z.json`. |
| Task-path failure localization | Data / Codex | Complete: one closed, free-text-free category writer and legacy-compatible offline reader preserve the stage exit code. No timing/page/task/consumer change followed. |
| Failure-category reattachment | Data / Codex | Complete: post-writer `intraday-head-20260818T1924006306454Z` binds `collection_exit_nonzero / reason_unavailable` through `execution/kis-paper-intraday-head-invocation-v1/intraday-head-20260818T1924006306454Z/terminal.json` and `execution/kis-paper-intraday-head-schedule/intraday-head-20260818T1924006306454Z.json`. |
| Failure-category confirmation | Data / existing `thericher-kis-paper-intraday-head` task | Complete: later `intraday-head-20260818T2120005941479Z` is hash-bound but `retained_partial` with a successful collection outcome, so its compatibility-default `reason_unavailable` is noncomparable. No recovery proposal or behavior change followed. |
| Static intraday Task-contract reattestation | Data / Codex | Complete: source-safe installed Task metadata and checked-in first `session-capture` route are all `matches`; no Task, Docker, KIS, collector, or broker invocation occurred. It closes static drift only. |
| FirstRate source-local M1 normalization | Data / Codex | Complete: archive hashes/expected entries, strict decode, canonical output hashes, and timestamp-set equality are retained in the external normalization receipt. SPY/QQQ provider round-trip counts are 207,824/210,482; no promotion followed. |
| FirstRate source-local timeframe mechanics | Data / Codex | Complete: canonical hashes reattached; actual UTC-anchored 1m/5m/10m/1h/3h outputs are aggregated only and each emitted bar passed source-bucket OHLCV/ordering/completion checks. No resampled rows, coverage, model, or Paper consumer followed. |
| FirstRate source-local window preflight | Data / Engine Research | Complete: 32 frozen cells reattached canonical/mechanics hashes and retained only eligible-window count/end-timestamp-set hashes. No labels, features, predictions, GPU allocation, model selection, KIS, or Paper consumer followed. |
| FirstRate source semantics retrieval | Data / Claude review | Complete: official free-data/license pages re-retrieved with matching hashes; only vendor-declared timezone/omission facts are retained, and offset convention/bar boundary remain `not_disclosed`. No promotion followed. |
| Norgate D1 capability reprobe | Data / isolated host runtime | Complete as scoped: the one invocation produced no parseable source-safe output or task-owned receipt. It proves no Norgate availability, subscription, source, or data fact and is not retried. |
| Norgate host readiness bridge | Data | Complete: a source-safe immutable receipt reattests `input_unavailable/local_api_not_ready`; host runtime is available and later categories are not checked. No raw data, credential, KIS, broker, scheduler, or Docker path was used. |
| Market-data contract inventory | Data / Engine Research | Complete: immutable six-class receipt `market-data-contract-inventory-20260819-r1.json` reattaches as 3 unavailable and no predictive/Paper/GPU-eligible input. |
| Later intraday terminal reattachment | Data / existing task | Owned monitoring: current pointer remains the 2026-08-18 baseline; accept only a strictly later terminal/completion binding. Do not poll or manually invoke the task. |
| SPY D1 stability | Data | Existing observer owns its next eligible weekday observation. Its status is observational only, never provider finality. |
| Virtual-Paper lifecycle canary | Execution | The 2026-08-25 23:35 KST task session receipt reattached offline to its exact lifecycle receipt as `canary_completed -> cancelled / clean`, `paper_only`, attribution `not_eligible`, and acknowledged-order-reference category only (session `sha256:f9000afdb172455a3214e6c7cb551ce2683632feb9dd65c1232c486f9380960d`; lifecycle `sha256:9aa7d3a28701c91afbc734080107157c5d6d6f98510bcfa9d6104190a499ab8e`). The credential-free runtime projection is absent. The 2026-08-24 session remains `quote_unavailable / quote_timestamp_stale`, `no_new_intent`, and the 2026-08-11 reader pair remains `outcome_unknown / unresolved`. None is a fill, PnL, alpha, or model result. Do not resubmit either intent. Scheduler is `Ready`; next task-owned opportunity: 2026-08-26 23:35 KST. |
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

The D1 overlap-reconciliation package passed 48 focused cache, causal-reader,
collector-script, and scheduler-script tests, then the full authority suite as
`3218 passed, 19 skipped` in 41m26s, plus Ruff, both credential-free Compose
parses, and `git diff --check`. It was source/fixture-only.

The v5 D1 forward-cache outcome and verification-root recovery passed the
focused eight-test serial and four-worker groups, then the full authority
parallel suite as `3215 passed, 19 skipped` in 39m24s, plus Ruff, both
credential-free Compose parses, and `git diff --check`. The runner now prefers
local non-reparse `D:\trpy` and falls back to `C:\trpy`; it is test-only and
does not alter market-data or model-artifact roots. The first C-root authority
attempt exposed correct 15% storage-floor enforcement in test-created artifact
roots, and the only later failures came from a short system-temp fixture's
normal-capacity assumption. That fixture now supplies a deterministic normal
capacity while retaining its explicit below-floor test. Claude's bounded
recovery review returned no verdict, recorded as `review_unavailable`; no
broker, KIS, credential, Docker service, or scheduler call occurred in this
verification repair.

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
