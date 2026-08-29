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
| KIS Paper QQQ/NAS + SPY/AMS intraday head | The latest task-owned terminal (`intraday-head-20260819T2120006022679Z`) is source-safely `complete` at the dispatcher level, with verified current-session coverage still `incomplete/current_session_short`; it retains no model qualification. Metadata-only inspection has 37 retained chunks and zero complete regular sessions. The existing four-trigger Task remains unchanged. Its runner now keeps the first three triggers at four pages per target and gives only a regular-weekday 16:20--20:00 Eastern post-close invocation an eight-page cap. Claude CLI produced no verdict (`review_unavailable`). | This is one bounded existing-task capability probe, not a new schedule, rate change, or retry loop. The next post-close receipt must still prove the exact coverage result; a short result closes this cap test without automatic escalation. It does not prove Scheduler origin, provider finality, decision-time availability, a model input, or Paper eligibility. |
| KIS Paper QQQ/SPY M1 cursor cache | 21 shared complete regular sessions; exact cursor scope is exhausted. | Source-local mechanics, fixed local-paper baselines, and target-free window preflight only. |
| KIS Paper private D1 | Unadjusted/partial with finality and as-of facts unavailable. The NAS daily-history panel and historical-forward projection now reject a nonempty common-session sequence with an interior normal session missing under pinned local `pandas-market-calendars==5.4.0` `NASDAQ` alias (`NYSE` calendar); this package did not reread the current cache. | `input_unavailable` for daily predictive work. A forward cache retains later rows across a gap, but its prospective input stays unavailable until the full boundary-to-forward session chain is present. The continuity rule proves neither source finality nor current-cache qualification. |
| KIS Paper QQQ/SPY D1 forward caches | The v1 lineage remains quarantined after retained revision conflicts. The separate v2 lineage at `daily-qqq-spy-forward/v2` reattached offline at 18 common sessions with cache identity `sha256:3ef5f433d1f1a0f36d1326ccff584a4172949e9b0530266b1478acbcc5caa5ea`. A two-stage QQQ/SPY observer is now installed: it retains only per-target row hashes in external immutable receipts and owns its `next_due` state. Its Docker wiring smoke was `not_due`, so it made no KIS request and has produced no pair result yet. | v2 is forward collection/provenance only. The observer can disqualify one session on a missing or changed identity, but even a match lacks point-in-time availability, provider finality, and corporate-action qualification. Neither cache nor observer can become a ranking, model, GPU, Research, Execution, or Paper input. |
| KIS Paper broad D1 panel | The latest source-safe postrun snapshot (2026-08-01) recorded 2,119/2,119 current-listing targets covered, zero quarantined targets, and zero mismatches over its 604-target baseline overlap. The 2026-08-19 short continuation reattached the same all-terminal registry at unchanged generation 26,368 (1,089 `complete`, 1,030 `source_limited`) and made zero KIS requests. | Coverage/provenance inventory only: current-listing, non-PIT, unadjusted, corporate-action-unqualified, and session-finality-unattested. Its exhausted historical cursor cannot supply a target, ranking, training, or Paper input; later daily sessions need a separate forward cache. |
| KIS Paper IWM/AMS M1 | Isolated current-head v2 observations replay locally; no H1/H3 history. Its separate one-page cache reattached offline as exactly one `head` chunk with verified index/manifest/raw integrity, `51` complete bars, `17` adjacent 1m pairs, `33` non-adjacent pairs, and a `660`-second maximum interval. Its source-safe mechanics receipt is `sha256:7dbdae99adaf1e19fe1c3d6bd2760edb71cae2cb7c737c519a5b5f3259e50818`; no raw rows were emitted. The bounded caller-derived probe accepted its head but observed no recognized continuation header, writing only `sha256:99068ebe69ee7d5300eeb2671eed433df87830db980947ac26d4b97a3b267cea`. | The exact IWM current-head request contract has no observed continuation under this one-run probe. Default IWM remains one page; no retry, collector, schedule, raw probe cache, history/finality/availability claim, model input, or Paper input follows. |
| Tiingo raw D1 ETF trio | The 2026-08-09 immutable SPY/QQQ/IWM snapshot reattested offline through 2026-08-07 with 8,438/6,896/6,588 sessions. The completed frozen D1 rotation and its independent aggregate audit found 1,892 event-mask exclusions, zero discontinuity-only exclusions, four unmasked validation contexts, and three active decisions against the fixed 100 minimum. | A continuation of already-seen, source-separated non-PIT history: retrospective controls and diagnostics only, never a fresh selection look, threshold calibration, ranking, sealed evaluation, GPU, or Paper input. The completed audit found no semantic contradiction, so this Tiingo rotation lineage is closed without altering its source or masking policy. |
| Tiingo prospective EOD ETF trio | The 2026-08-19 UTC external SPY/QQQ/IWM snapshot reattests dataset `sha256:537211067196a91d24dfaab229666decc96108e17c4de89e8059d02ed27c787c`, manifest `sha256:d02c5c1f7bcd47148b491273fad613637ddee8972ad8bb1bdf79dd3ab7d5426d`, exactly three fixed-symbol responses, 72 normalized rows, and source-as-of 2026-08-12. | Prospective lineage only. Its closed contract leaves point-in-time, model, training, campaign, ranking, order, Paper, and GPU eligibility false; it cannot clear KIS quarantine or prove decision-time availability/finality. |
| Tiingo IEX M5 r1 ETF trio | Pinned 2026-07-19 IEX-only snapshot reattested offline by raw hashes, stored gzip hash, and exact canonical payload. | One completed source-isolated reconstruction runtime integration only; no source scope, training eligibility, KIS equivalence, model-selection, or Paper-input change. |
| FINRA daily short-sale volume | Existing 2018-08-01--2026-06-17 local snapshot spans four facilities and 58,620,306 canonical rows. The 2026-08-20 official-source receipt is `source_retrieved_with_limits`: FINRA states daily files arrive no later than 18:00 ET and may be revised. | A future source-local, next-session availability/revision contract may evaluate it as an offline-only auxiliary context. It is neither short interest nor exchange-consolidated total volume, has no observed finality/decision-time availability, is not KIS-reconstructible, and cannot yet create a feature, campaign, GPU, Execution, Paper, or live input. |
| Norgate trial tail | The completed reconciliation reattached the bridge and observed `input_unavailable/local_api_not_ready_updater_not_observed`; its summary is `sha256:5c79a0430b789709df50136f6a1ea999836072c7483f6f1598fc80d43bb924ac`. The isolated client imported, but no fixed updater installation or process marker was observed. No raw Norgate data was read. | The local prerequisite is to install and run Norgate Data Updater, then start one new bounded readiness package. This is not a trial-rights, source-capability, or data-quality conclusion; do not poll or start the date-indexed probe. |
| FirstRate free M1 SPY/QQQ | The two hash-bound original ZIPs normalized to canonical local CSVs with expected entry names and exact decoded/emitted timestamp-set equality. SPY has 207,824 and QQQ 210,482 provider-readable complete M1 Bars; UTC-anchored 1m/5m/10m/1h/3h geometry and the frozen 32-cell target-free window matrix reattached offline. The fixed 5m L2, 20/60 trend, and Wilder-RSI mean-reversion after-cost controls each reattached only complete contiguous windows and were rejected with zero wins over flat across six SPY/QQQ nonzero-cost cells. Official FirstRate evidence labels data US Eastern/New York and declares zero-volume bars omitted. | The existing DST-aware New York-to-UTC conversion is a source-local assumption: offset convention and bar start/end stamping remain `not_disclosed`. Omission is vendor-declared only, never session coverage or cross-feed alignment. Project policy remains private/internal with no redistribution. The source proves neither KIS parity, decision-time availability, finality, a predictive model input, or a Paper input. |
| Fixed market-data contract inventory | The external immutable inventory records all six predeclared footprints with only shallow presence and receipt hashes: KIS M1/D1 and Norgate trial are `input_unavailable`; FirstRate M1 is `source_local_mechanics_only`; Tiingo ETF D1 is `retrospective_control_only`; Tiingo IEX M5 is `non_promoting_runtime_only`. | The receipt confers no predictive, Paper, or GPU consumer. It is an evidence map only; each status is scoped and a later qualified input needs its own contract. |
| NYSE Daily TAQ source discovery | The official catalog distinguishes a public sample from a full paid product. No data was acquired and no provider was adopted. | Sample schema/aggregation reference only; it is not a no-cost ongoing or KIS-aligned prospective input. |

Raw market bytes remain under `D:\market_data`. Source-safe receipts and
research artifacts remain under `D:\thericher-v2\model-artifacts`.

## Active Objective

`kis-paper-d1-prospective-observation-pairing-v1` now owns an installed
two-trigger KST worker: first observation at 08:15 and later re-observation at
23:20, Tuesday through Saturday. It uses the existing QQQ/NAS + SPY/AMS
virtual-Paper daily route only, keeps the v2 cache read-only, and persists
only an external source-contract hash, session key, timestamps, row hashes, and
a hash-bound source-safe current-outcome pointer to immutable receipts. The
offline reader revalidates the pointer plus exact first/later receipt binding;
an absent pointer is only `current_pointer_unavailable`. The approved offline
reader now validates a current first-stage receipt for completed session
2026-08-28: `input_unavailable/first_observation_target_failure`, source contract
`sha256:b7752aa22cc3b358b52c6fe2e6da72e1dc811b5a7078563de0c4201a68f9033d`,
and receipt `sha256:36560fc3aa37db0f2e669d5235adac0ebf9ceea972f4a507f2a58d3009342d6e`.
Its first-receipt binding and later observation are both absent, so it is not a
pair result. The source-safe Task Scheduler status is `Ready`; task exit is not
stage or outcome evidence. The reader-owned `next_due` is
`2026-08-31T23:15:00Z`. The rebuilt observer image now gives future target
failures only sorted allowlisted aggregate codes and direct exceptions fixed
family reasons; it retains no error text. No raw rows, model, GPU, or consumer
path is enabled.
A later match is measurement-only; a missing or changed target hash
disqualifies only the bound session.

`kis-daily-pair-forward-v2-fresh-cache-bootstrap-v1` is complete. It created
the isolated fixed-pair v2 lineage without mutating or copying the v1
quarantined cache. The initial network-disabled preflight was
`collection_required`; one eligible serial KIS Paper collection completed as
`ready`, and a second network-disabled preflight reattached it as
`cache_current`. This remains collection/provenance evidence only; it provides
no ranking, model, GPU, Execution, Paper-consumer, or live claim.

The completed FirstRate 20/60 technical-trend and Wilder-RSI mean-reversion
controls each reattached the same source-local 5m geometry and rejected their
fixed rule after zero wins over flat in all six nonzero-cost cells. The trend
matrix has 18 cells and the RSI matrix has 12; every aggregate local-paper cell
was replayable and terminal-flat. These are closed source-local rule results,
not KIS-parity, point-in-time, finality, ranking, GPU, Execution, or Paper
facts.

The completed frozen Tiingo D1 trend-pullback rotation and its independent
aggregate event-mask audit are consistent. The audit found that all 1,892
validation exclusions were event-mask exclusions, no discontinuity-only
exclusions occurred, four contexts were unmasked, and three were active. This
closes the source-separated rotation lineage as structurally sparse; it does
not refresh the snapshot, alter masks, retune the rule, or create a Research,
GPU, Execution, Paper, or live consumer.

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

The bounded collection-dispatch review then verified from the existing runner
and terminal contract that an already bound `collection_exit_nonzero` terminal
is written only after `Invoke-HeadProfileService` has returned the host
`docker.exe compose run` exit code. Claude's falsification-first result was
`supported-with-limits`: a further per-call marker would duplicate that exact
returned-boundary evidence for the known terminal while adding another
diagnostic write to the pre-collection path. This proves neither Docker/container
entry nor collector/KIS/provider behavior. No duplicate marker was added.

The bounded direct host probe is now complete: `QQQ/NAS` and `SPY/AMS`
completed one `session-capture` invocation at the existing four-page cap, with
only `paper_only`/market-data aggregate evidence retained at
`us_equities/kis_paper_private/intraday-head/v1/session-capture/20260819T130238145868Z-50e04e46fdb2e4e0.json`
(`sha256:50e04e46fdb2e4e0ceb65673066751fdb37bfaa5b53b8007f4ddb8f20316354a`).
It proves direct-host collector completion only. The next narrow Data package
is one existing Compose-service invocation without a Windows Task, so the
container path can be classified separately without changing pace, scheduling,
or consumers.

That first direct Compose-service invocation is now complete as a scoped
nonzero. The exact source-safe receipt
`us_equities/kis_paper_private/intraday-head/v1/session-capture/20260819T131812782029Z-0caa1e559078804d.json`
(`sha256:0caa1e559078804dc2d269a9aa2abf708e9f169783f775378fdf0d17250e2bcc`)
records both fixed targets as `rejected/token_request_not_due`. A source-safe
read of the shared gate observed a separate start at `2026-08-19T13:15:01.522769Z`
and the installed 300-second due interval. Thus this attempt yielded before a
token POST; it identifies no worker and does not diagnose Docker, KIS, or the
provider. A new goal-owned post-gate attempt may make one fresh atomic claim;
the completed attempt will not be retried inside this objective.

The due-gate container attempt then reached the existing retained-cache
protection for both targets. Its exact safe receipt
`us_equities/kis_paper_private/intraday-head/v1/session-capture/20260819T133017088958Z-ed596cfe5f8dc959.json`
(`sha256:ed596cfe5f8dc95977c961d48927e9266ba6353e82578f2a2f76b26acc1b80e4`)
is `rejected/minute_duplicate_conflict` with `retained_cache/quarantined` for
both `QQQ/NAS` and `SPY/AMS`. The existing index-only quarantine leaves raw
bytes immutable and excludes only conflicting active head entries. It is an
isolated recovery fact, not a provider-finality, coverage, or consumer claim.
Claude supports one later independently fetched clean-capture attempt; another
retained-cache conflict closes this exact recovery path.

That later clean-capture attempt completed through the exact existing Compose
service. Its unbound source-safe receipt
`us_equities/kis_paper_private/intraday-head/v1/session-capture/20260819T134229353199Z-c87d4ebfde0e7545.json`
(`sha256:c87d4ebfde0e7545e7907936c8eb506c1e3aa7514ef6d9ea86e9a36d7b4a522e`)
is `complete` with both fixed targets `collected` and no failure or conflict
category. The filename timestamp, immutable hash, external storage scope, and
unbound direct-Compose identity were reattached offline. It closes only the
cache-recovery branch, not session coverage, finality, or consumer eligibility.

## Ready / Owned / Due

| Work | Owner | Completion evidence |
| --- | --- | --- |
| FirstRate 5m L2 after-cost control | Data / Engine Research / temporary Validation | Complete: source/local-resampling reattestation, 60-bar/61-bar-embargo split, and all 18 local-paper replay cells completed. The L2 candidate had zero wins over flat in six nonzero-cost SPY/QQQ cells, so the lineage is `rejected`; no GPU or consumer follows. |
| Tiingo D1 event-mask coverage audit | Data | Complete: the exact rotation receipt and pinned snapshot reattached independently. Event masks accounted for all 1,892 validation exclusions, discontinuity-only exclusions were zero, and the aggregate binding was consistent. The rotation lineage is closed without a policy change. |
| Norgate trial host readiness reconciliation | Data / Infra Capability | Complete: the immutable diagnosis is `local_api_not_ready_updater_not_observed`, independently validated without a second host invocation. It records a local updater prerequisite only; no source rows, updater action, network, or repeated poll followed. |
| KIS D1 prospective observation pairing | Data / Infra Capability | Owned: the installed two-stage worker has an external durable `next_due` and a hash-bound current-outcome reader. The validated current first-stage receipt is `input_unavailable/first_observation_target_failure` for completed session 2026-08-28; no first-receipt binding or later observation exists, so no pair result, model, or consumer is enabled. The source-safe Task Scheduler status is `Ready`; task exit is not stage or outcome evidence. Reader-owned `next_due`: `2026-08-31T23:15:00Z`. The host-only `read_current_kis_paper_d1_prospective_observation_pairing_outcome.py` CLI calls that same reader and emits only validated categorical fields, immutable receipt binding, and an external evidence pointer. The rebuilt image limits future target failures to sorted allowlisted aggregate codes and direct exceptions to fixed family reasons. |
| Cboe VIX/VXN D1 availability observations | Data / completed one-shot `thericher-cboe-vix-d1-availability-20260820` and `thericher-cboe-vxn-d1-availability-20260820` tasks | Complete: Task Scheduler records the 2026-08-21 05:30/05:31 KST invocations with result `0`, but the prepared offline reader returned `unavailable` for both VIX and VXN under the exact 2026-08-20 session, 20:00Z close, and 2026-08-21 13:30Z next-open bounds. The missing receipts are scoped to these observations; task exit is not outcome evidence. Do not retry or create a recurring task. Neither outcome establishes decision-time availability, provider finality, a feature, campaign, GPU, Execution, Paper, or live input. |
| FirstRate 5m trend-rule input reattestation | Data | Closed as duplicate: the completed fixed 20/60 control already bound this exact source-local 5m geometry and chronology. Do not dispatch another reattestation under a new label. |
| Tiingo prospective EOD refresh | Data | Complete: one current dated external SPY/QQQ/IWM snapshot was acquired through the fixed three-request path and reattached offline by dataset/manifest identity. Its source-as-of boundary and all lineage-only eligibility flags remain fixed; focused and full authority verification passed. |
| Intraday coverage-repair rollout | Data / existing task image | Complete: clean-context image build and source-safe static reattestation passed without a task, KIS, Docker service, or collector invocation. |
| Invocation-marker reattachment | Data / Codex | Complete: the first fresh marker and exact schedule terminal reattached as `collection_exit_nonzero`; its source-safe pointers remain external-root-relative. |
| Task-path failure localization | Data / Codex | Complete: an allowlisted free-text-free category writer and legacy-compatible reader preserve the exact stage exit. No task, pages, timing, or consumer change followed. |
| Failure-category reattachment | Data / Codex | Complete: post-writer `intraday-head-20260818T1924006306454Z` reattached as `collection_exit_nonzero / reason_unavailable` through exact hash-bound terminal and schedule receipts. No timing, pages, task, or consumer behavior changed. |
| Failure-category confirmation | Data / existing `thericher-kis-paper-intraday-head` task | Complete: later `intraday-head-20260818T2120005941479Z` is hash-bound but successful and `retained_partial`, so the preserved default category is noncomparable. No recovery proposal or behavior change followed. |
| Static intraday Task-contract reattestation | Data / Codex | Complete: installed Task enabled/action/triggers/settings and checked-in first `session-capture` runner/Compose route are all `matches`; the source-safe receipt is hash-bound and the audit invoked no Task, Docker, KIS, collector, or broker. It does not diagnose the existing terminal. |
| Collection-dispatch boundary review | Data / Codex / Claude | Complete as no-change: the bound terminal already carries the returned host Docker-command exit for its exact collection call. A new marker would not diagnose Docker/container or provider behavior and would add diagnostic work before collection. |
| Direct host collection capability probe | Data / Codex | Complete: one `QQQ/NAS` + `SPY/AMS` `session-capture` invocation at four pages per target completed with an exact unbound source-safe receipt. It established direct-host collector completion only; no Task, Docker, account, order, Paper consumer, or model behavior changed. |
| First container collection capability probe | Data / Codex | Complete: one exact Compose invocation yielded `rejected/token_request_not_due` for both targets before a token POST. Its safe receipt does not diagnose Docker, KIS, or the provider; no Task, account, order, or consumer ran. |
| Post-gate container collection capability probe | Data / Codex | Complete: the due-gate service reached the built-in retained-cache conflict branch and quarantined both conflicting active head entries while preserving raw bytes. It established no session/finality/model consumer. |
| Quarantined-head recovery capture | Data / Codex | Complete: one later exact Compose capture is hash-bound as unbound `complete` with both fixed targets `collected`; no conflict repeated and no Task, account, order, consumer, or model change followed. |
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
| Daily-broad continuation capability | Data / Codex | Complete: the exact short continuation reattached an unchanged all-terminal 2,119-target index and exited `complete` with zero chunks/pages/failures. It constructed no KIS client; a long worker is not ready for this cursor. |
| QQQ/SPY D1 forward refresh | Data / Codex | Complete: the hash-bound preflight required collection, then the one permitted direct collector deferred at `token_request_not_due` with zero new accepted pages and zero changed targets. The existing scheduled task is ready and owns its next due attempt. |
| KIS D1 forward causal qualification | Data | Complete: one offline fail-closed predicate rejected the current cache as `input_unavailable` only for the three unobserved runtime conditions: named clock/session, decision-time availability, and provider finality. Its synthetic fixture passed only with all six explicit conditions; every single-condition ablation failed closed. No collection, credential, KIS client, Docker, scheduler, GPU, research, or execution consumer ran. |
| KIS QQQ/SPY D1 one-shot current collection | Data | Complete: static Research/Execution search found no `latest_session` consumer; one preflight required collection and one collector then closed `unavailable/collector_unavailable` without a cache payload. No retry or consumer change followed. |
| KIS QQQ/SPY D1 stage-aware one-shot collection | Data | Complete: one matching preflight and exactly one shared-tag collector invocation closed `unavailable/collector_unavailable/failure_stage=commit`; the receipt contract hash matches, cache remains valid, and zero cache writes were observed in the invocation window. No retry or consumer change followed. |
| KIS QQQ/SPY D1 commit failure classification | Data / Infra Capability | Complete: v2 static source-safe optional kinds are fixed-order and fixture-tested with no credential, KIS, Docker, cache-write, or retry. It does not classify the completed v1 failure. |
| KIS QQQ/SPY D1 v2 preflight and one-shot collection | Data | Complete: matching preflight receipt `sha256:cf95c93741330d60d95dc040e12446d3a34e899d8a3565b82cb0f8b2743e6ec2` preceded exactly one collector receipt `sha256:0c28203f24a098685f8068433e2250f14c1774bde99e5e87e64de1862ae53d42`, which narrowed the failure only to `commit/cache_contract`; no retry or consumer change followed. |
| KIS QQQ/SPY D1 commit-phase diagnostic | Data / Infra Capability | Complete: static v3 hash `sha256:219a3a13d1419f9b65dc34f1d6fa3a3ffcb534b045b1d1729308cb8d944e5893` permits only four fixed future `cache_contract` phases; fixture tests preserve exceptions and reject private/dynamic receipt content. |
| KIS QQQ/SPY D1 v3 preflight and one-shot collection | Data | Complete: matching preflight receipt `sha256:6fa27ec40b8009b76c0c31fe6210a4ad8814676566bc5f6cc442fa71a011fd5a` preceded one collector receipt `sha256:cd1b1222c61da98aa12091b8a61bd153cd91e2943d0c79c98dafe4340eb33dc3`, narrowed to `commit/cache_contract/cache_prepare`; no retry or consumer change followed. |
| KIS QQQ/SPY D1 prepare-subphase diagnostic | Data / Infra Capability | Complete: static v4 hash `sha256:95e0ec0fd7408e237cbb79e4010e152291dd4322f58133bd4c46207c258dc893` permits only `cache_access`, `cache_state_load`, or `incoming_merge` on a future exact `commit/cache_contract/cache_prepare` receipt. It names a source region, preserves exception behavior, omits unclassified cases, and made no external call. |
| KIS QQQ/SPY D1 v4 preflight and one-shot collection | Data | Complete: matching preflight `sha256:e24e124b7e2ab6ec50496b5fc9a70ce21198f1483606527b442e9c749cf9029f` permitted one collector `sha256:8100bf8cccc02afa88124c05a731ae53113f99075761c5fbe8bb657a3416e832`, which closed `deferred` with QQQ `auth_rejected` and SPY `token_request_not_due`; receipt/cache binding holds and no retry or consumer change followed. |
| KIS Paper authentication capability probe | Data / Infra Capability | Complete: one source-safe virtual-host token-only receipt `sha256:d07e12f8ca521ca32cc00a4a0f81625ad5b503fa0505bad026969aca95db8261` reattached as `authenticated`; it retains no token, credential, raw body, market-data, account, order, or live fact. |
| KIS QQQ/SPY D1 v5 readiness and one-shot collection | Data | Complete: readiness `sha256:f1d833bdf8aa775919f1793d2025ab2b530d251c13e3da22eb81a70a2c6ba7ab` confirmed open recorded gates without a network/cache write; one collector `sha256:a10e42f5a44753c67bf483414005d98b5171341998926b10a2a5f9dc85100910` closed `commit/cache_contract/cache_prepare/incoming_merge`, with cache/index aggregates unchanged and no retry. |
| KIS QQQ/SPY D1 post-reconciliation observation | Data / Infra Capability | Complete: preflight `sha256:91206b61150364513ecaedaa2591253be4721abbc37a0cac9c6e2eca69e54757` was `collection_required`; one collector `sha256:85516c0e8ce93a9fb4396afd9f53f33ed37005dade4e998bdc4dd1f307a692c0` retained two conflicts and quarantined both targets. Causal receipt `sha256:40cf5a8487fd7144304f8e056aebf6d93811a3ff7051364c207f4025c4e0105a` is `input_unavailable`; the 48-test group and `3218 passed, 19 skipped` authority suite passed. No retry, clearance, promotion, or consumer action followed. |
| Historical KIS D1 CPU baseline | Data / Engine Research | Complete: QQQ and SPY independently reattached the same 4,756 complete D1 Bars and completed their fixed two-baseline by two-phase local-paper matrices under external contracts. This source remains descriptive-only and does not become a current predictive input. |
| KIS D1 L2 logistic control | Engine Research / Data | Complete: the one hash-pinned QQQ/SPY development-only fit wrote external evidence only; validation labels were excluded and all two model plus six comparator replays used `local_paper`. Both model after-cost cells were negative, so the source remains descriptive-only. |
| KIS D1 regime-tree breadth | Engine Research / Data | Complete: the one hash-pinned development-only shallow-tree reproduction retained no serialized estimator and all two model plus six comparator replays used `local_paper`. QQQ/SPY model after-cost results were below their fixed previous-bar-direction comparators, so this descriptive lineage is closed. |

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
- Direct host session-capture evidence:
  `D:\market_data\us_equities\kis_paper_private\intraday-head\v1\session-capture\20260819T130238145868Z-50e04e46fdb2e4e0.json`
  (`sha256:50e04e46fdb2e4e0ceb65673066751fdb37bfaa5b53b8007f4ddb8f20316354a`).
- First container session-capture evidence:
  `D:\market_data\us_equities\kis_paper_private\intraday-head\v1\session-capture\20260819T131812782029Z-0caa1e559078804d.json`
  (`sha256:0caa1e559078804dc2d269a9aa2abf708e9f169783f775378fdf0d17250e2bcc`).
- Post-gate container conflict evidence:
  `D:\market_data\us_equities\kis_paper_private\intraday-head\v1\session-capture\20260819T133017088958Z-ed596cfe5f8dc959.json`
  (`sha256:ed596cfe5f8dc95977c961d48927e9266ba6353e82578f2a2f76b26acc1b80e4`).
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
