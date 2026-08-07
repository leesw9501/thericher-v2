# Data Agent Stateboard (시장데이터 담당)

`AGENTS.md` owns policy and `NEXT_CODEX_GOAL.md` owns the company objective.
This is the current Data projection, not a run ledger.

## Ownership And Boundaries

Data owns provider behavior, acquisition, provenance, calendars, canonical
storage, resampling, manifests, temporal splits, and quality facts. It does not
select strategies, fit models, or make execution decisions. KIS Paper
market-data collection is standing-authorized through its named owner paths;
never read `KIS_LIVE_*` or route account/order calls.

## Current Sources

| Source | Status | Permitted interpretation |
| --- | --- | --- |
| KIS Paper current M1 head cache | Observed, partial current-session input | Named current-window consumers only |
| KIS Paper QQQ/SPY M1 cursor cache | Terminal exact cursor scope with 21 shared complete 09:30--15:29 ET sessions | Source-local non-promoting geometry only; QQQ supplied local EMA and MTF mechanics, not a qualification or consumer promotion |
| KIS Paper private D1 cache | `input_unavailable` for daily-EMA preparation | Explicitly unadjusted, partial, and missing daily finality/as-of metadata |
| KIS Paper IWM/AMS M1 candidate | One accepted current-day page through a probe-only route | Provisional route fact only; no history, qualification, or consumer promotion |
| Yahoo intraday starter M1 manifest | Bounded metadata-only 8-day probe with one successful symbol | `input_unavailable` for source-native multi-symbol ORB; no raw scan or promotion |
| KIS Paper SPY D1 stability observer | First task-owned receipt `stable` at 2026-08-04 23:15 KST | Bounded source-safe observation only; never a qualification or consumer bridge |
| KIS SPY paginated-prefix capability cache | First task-owned receipt is incomplete after one accepted page | Exact endpoint pagination fact only; no decision-time availability or consumer promotion |
| KIS broad NAS D1 panel | Terminal current-listing control | Offline, non-promoting source-local research only |
| PIT source candidates | `D:\market_data\pit_sources` contains empty Sharadar and Norgate membership templates only | No manifest, raw export, provenance, or consumer input; do not rescan until an actual export appears |
| Tiingo prospective EOD snapshot | Immutable 2026-08-04 retrieval through source date 2026-07-28 for SPY/QQQ/IWM | Future-lineage only; model and Paper eligibility remain false |
| Tiingo/Norgate D1 snapshots | Fixed offline controls; Tiingo has a hash-bound event-marker sidecar and Norgate NDU is healthy | Source-separated, non-Paper research only |

The broad D1 panel remains current-listing-only, non-PIT, unadjusted or
adjustment-unqualified, corporate-action-unqualified, and session-finality
unattested. Do not promote it to ranking, Paper input, or a qualified model
dataset. The KIS minute endpoint's observed head continuation does not prove
arbitrary historical intraday reach. The exact QQQ/NAS and SPY/AMS blank-start
cursor chains are now `source_exhausted`: their retained M1 coverage runs from
2026-06-22 through 2026-07-21, with about 20,000 rows per target, and their
terminal pages supplied no continuation. That bounds only those exact routes
and cursors; it neither proves a provider-wide retention limit nor permits an
undocumented timestamp seed.

## Ready / Owned / Due

- **Current-head recovery:** `intraday-qqq-v4-scheduled-validation-observation-v1`
  completed against the exact 2026-08-07 06:20 KST task-owned pointer. Task
  Scheduler result `1` and the immutable terminal agree on
  `recovery/collection_exit_nonzero`; the required same-run capture binding is
  `verified/incomplete`. Its hash-bound source-safe capture receipt classifies
  QQQ/NAS and SPY/AMS as `rejected/minute_duplicate_conflict`. This is the
  active collector recovery fact only: no raw rows, data qualification, model,
  Paper, fill, PnL, or alpha claim follows. The success-only QQQ session and
  v4 validation services were not invoked and remain `not_applicable`, so v4
  is neither a success nor a failure for this run. The 04:24 v3 historical
  terminal remains preserved. The completed exact, binding-verified recovery
  projection emits `rejected_duplicate_conflict` only for this terminal class
  and capture chain; missing, malformed, unsafe, or mismatched evidence emits
  `evidence_unavailable`, without a latest-artifact or mutable-index fallback.
  Future receipts now seal collector-time `candidate_batch`/`retained_cache`
  provenance plus `not_applicable`/`preserved`/`quarantined` disposition;
  absent historical fields remain `not_recorded_legacy`, and partial or mixed
  receipt shapes fail closed. The existing task next owns 2026-08-08 00:29 KST;
  do not manually rerun or duplicate it. Its collector image has been rebuilt
  without an invocation.
- **Current-head timing repair:** a metadata-only reattachment of the
  2026-08-04 QQQ cache found retained regular-session page ranges
  09:32--11:31, 11:32--13:31, and 15:20--15:59 ET. The missing 04:31 KST
  run was the token-guard collision, not a source-exhaustion result. After a
  source-safe Claude review returned `supported-with-limits`, the same existing
  Tuesday--Saturday task was re-registered, with no new action, service, cache,
  or run count, at 00:29, 02:28, 04:24, and 06:20 KST. The 04:24 trigger
  has a static 5m30s margin before the 04:29:30 prefix control and six minutes
  before the 04:30 prefix collection. The terminal 06:20 KST session capture
  must independently show all 390 completed regular-session offsets before
  this becomes a coverage result;
  otherwise this timing hypothesis is rejected and
 reassessed. DST/pre-market page behavior remains unproven and must be
 rechecked before the next U.S. DST transition. The next owned run is
2026-08-07 06:20 KST; do not manually invoke it.
 The focused schedule checks (18) and the full parallel authority suite
 (2,571 passed, 23 skipped) passed after registration.
- **Cumulative capture receipt:** the rebuilt existing
  `kis-paper-intraday-head` image now writes both its exact-run
  `coverage` and `current_session_cumulative_coverage` for the observed
  America/New_York date. The latter reads only the local index/manifests and
  explicitly excludes earlier and later session dates. Current terminal
  receipts do not include its exact receipt hash, observation time, or
  categorical digest, so no terminal result may attach a same-run coverage
  claim by selecting a newest artifact. It makes no additional KIS call,
  raw-minute read, scheduler, model, or Paper decision. DST/holiday semantics
  and the immutable post-collector snapshot remain scoped limitations.
- **Daily D1 catch-up:** the 2026-08-05 07:00 KST task-owned worker completed
  `drained` with zero attempted/retained chunks and zero completed targets. Its
  source-safe receipt records `client_constructed: false`, so this exact
  cursor state did not read credentials or call KIS. It does not establish
  provider-wide historical coverage; the next scheduled worker remains owner
  of any changed cursor state.
- **Tiingo prospective EOD refresh:** one authorized standard-EOD retrieval at
  2026-08-04 23:13 UTC stored an immutable `SPY`/`QQQ`/`IWM` snapshot under
  the fixed external root. It made exactly three provider requests, normalized
  39 rows through source date 2026-07-28, and then passed an offline loader
  reattachment with no token or network path. The snapshot remains
  `prospective_lineage_only`; training, campaign, ranking, Paper, and order
  eligibility remain false. It neither alters the historical D1 controls nor
  creates a new provider route, scheduler, model, or Paper action.
- **Token cadence calibration:** the 04:31 head collision is now a bounded
  Data capability question, not a permanent five-minute rule. A ready,
  token-only probe first checks and atomically claims the existing five-minute
  shared token-start gate, then uses fresh in-memory Paper clients for exactly
  two successful token POSTs. Only its own second POST may use the frozen
  30-second hypothesis; the shared request gate still applies and monotonic
  transport-start spacing must meet the hypothesis. A lost atomic claim makes
  no network call. The probe reads no credential when the precheck is not due,
  requests no market/account/order data, retains no token or response, writes
  only a source-safe immutable external receipt, and changes neither schedule
  nor default gate until a real result exists. At 06:25 KST, its first Paper
  token authentication succeeded but the second fresh-client authentication
  was categorically `auth_rejected` after 30.12 monotonic seconds. The result
  is `unavailable`, not a lower-cadence calibration: retain the default
  five-minute guard and do not repeat this exact 30-second hypothesis without
  a changed provider fact. Evidence:
  `D:\thericher-v2\model-artifacts\data\kis-paper-token-cadence-probe-v1\token-cadence-20260804T212620165702Z\summary.json`.
  A later read-only end-to-end static audit found no redundant delay: the shared
  one-second request-start gate, token-only five-minute start gate, categorical
  cooldown, and HTTP timeout protect distinct request classes or failure paths.
  Consider a pacing change only after a fake-clock/shared-root/transport test
  demonstrates overlapping protection for the same request state.
- **Historical M1 cursor scope:** the existing QQQ/NAS and SPY/AMS backfill
  indices were reattached offline as `source_exhausted`, with no new market-data
  page or snapshot. Do not reopen either terminal cursor with an invented seed;
  a changed endpoint, symbol, or provider behavior needs its own bounded probe.
  The official `inquire_time_itemchartprice` example documents no initial date
  or history-start parameter: blank `KEYB` starts the current request and a
  later `KEYB` is only the prior page's continuation cursor. It therefore does
  not authorize an arbitrary historical seed or a new collector.
  A source-safe geometry receipt independently finds 21 shared complete
  09:30--15:29 ET sessions, enough only for a source-local, non-promoting
  5--90 minute preflight. It retains `decision_time_availability: not_observed`
  and model/Paper eligibility false. Evidence:
  `D:\thericher-v2\model-artifacts\data\kis-m1-cursor-session-geometry-v1\assessment.json`.
- **IWM M1 candidate route:** one current-day IWM/AMS page was accepted through
  the isolated capability probe. The target is query/client/transport-enforced
  as one page with no previous-day or continuation request, and returned rows
  were discarded. It is `provisional_current_page_route_supported`, not an M1
  collector, historical-reach result, or Engine/Paper input. Evidence:
  `D:\thericher-v2\model-artifacts\data\kis-paper-minute-capability-probe\iwm-ams-candidate-assessment-20260804-r1.json`.
- **Yahoo M1 ORB input probe:** one exact existing metadata manifest is
  `input_unavailable`: its `1m` request spans only eight days and has one
  successful symbol with no explicit regular-session or decision-time-
  availability field. It cannot reproduce the source-native multi-symbol,
  14-prior-session ORB input, and its raw rows are not opened. Reopen only for
  a distinct later manifest that meets every frozen condition. Evidence:
  `D:\thericher-v2\model-artifacts\data\yahoo-intraday-starter-orb-input-probe-v1\assessment.json`.
- **Daily SPY consumer readiness:** a static trace found `producer_path_missing`.
  The existing 22:15 KST `daily-spy-head` task emits a verified prior-session
  cache snapshot only; it does not emit a capability/qualification, a provider
  finality fact, or decision-time availability evidence that Engine can consume.
  The reviewed `thericher-kis-paper-daily-spy-stability-observer` now owns a
  separate 23:15 KST weekday observation before the 23:35 canary. It compares
  only the prior-session row hash after a verified 15--90-minute-old snapshot,
  then issues at most one gated virtual-Paper `dailyprice` attempt. It has a
  ten-attempt bound, a nonblocking external receipt lock, and categorical
  unavailable exits before a GET for a stale/missing snapshot, client, auth, or
  token-gate failure. Its current `0x41303`/sentinel Task Scheduler state means
  `task_has_not_run`, not a worker failure. Its receipt always says
  `provider_finality: not_observed`
  and is Engine-unreadable. Do not build a consumer bridge from it alone.
  At 23:15 KST, its first task-owned attempt produced a source-safe `stable`
  receipt that the offline validator reattached: one `dailyprice` GET, no
  foreground wait or retry, and a 15--90-minute-old snapshot. This is a
  two-read row-hash match only; `provider_finality` remains `not_observed` and
  the receipt remains Engine-unreadable.
  Evidence: `D:\thericher-v2\model-artifacts\data\daily-spy-input-readiness\static-trace-20260804-r1\assessment.json`.
- **SPY prefix capability:**
  `thericher-kis-paper-spy-prefix-negative-control` and
  `thericher-kis-paper-spy-prefix-feasibility` completed their 2026-08-05
  04:29:30 and 04:30 KST attempt. The namespace control was clean; the
  collection exited `collected` after one accepted 120-row page, with 119
  completed prefix minutes, 241 missing prefix minutes, and an invalid seam.
  Its last page had no next cursor, but the legacy receipt did not retain a
  safe terminal continuation category, so its offline projection records
  `not_recorded_legacy`; it cannot distinguish a blank/absent response signal
  from an unrecognized nonblank one. It used one in-memory client, one token
  attempt, and one minute-page attempt. This is an exact endpoint/run
  pagination fact, not a provider-wide retention or paging conclusion. The
  existing worker owns its next scheduled attempt; do not manually rerun it.
  Its existing collector/observer images were rebuilt and the same tasks were
  re-registered after the safe-category change; their trigger times,
  `IgnoreNew`, and zero restart count are unchanged.
  One dedicated client/cache namespace may inspect at most four
  pages of 120 rows and must validate seams plus the exact completed
  09:30--15:29 ET prefix. The two-stage runner has no foreground sleep or
  retry loop: a network-free namespace control precedes the one-client
  collection, followed by a credential-free observer. Its focused
  Data/pagination/schedule reattestation passed 83 tests on 2026-08-05. Its
  first task-owned source-safe receipt is `measurement_incomplete_or_invalid`.
  The host-only
  `project_kis_paper_spy_paginated_prefix_capability.py` reader now binds one
  derived exact run ID to its immutable control/observation pair without
  reading raw pages, credentials, or a latest artifact. New exact runs retain
  only `recognized_continuation`, `blank_or_absent`, or
  `unrecognized_nonblank`, never a raw response-header value. It can classify
  only post-collection completed-prefix availability, incomplete/invalid
  measurement, or no measurement; it always retains
  `decision_time_availability: not_observed`.
- **Official minute-pagination reattestation:** the official KIS GitHub
  `inquire_time_itemchartprice` example (current `main`, file dated
  2025-06-30) confirms the exact first-page and continuation contract: first
  request uses blank `NEXT`/`KEYB`; a response `tr_cont` of `M` or `F` requires
  `NEXT=1`, `PINC=1`, `tr_cont=N`, and a `KEYB` one `NMIN` before the prior
  page's last bar. The current typed client, four-page SPY prefix collector,
  and transport tests already implement that contract. Therefore the next
  task-owned exact prefix run is the bounded capability probe recommended by
  the source, not a reason to rebuild the collector or manually rerun it.
  The source confirms continuation semantics only; it does not turn a
  one-page legacy receipt into a terminal-provider conclusion.
- **Timing is now a bounded source hypothesis:** the measured 2026-08-04
  row-key geometry, completed-bar rule, and retained five-minute token guard
  support the existing worker's 04:24 KST earlier trigger rather than a
  speculative post-guard delay. It preserves a six-minute static margin before
  the 04:30 prefix collection and overlaps the adjacent QQQ page windows. The
  terminal task-owned session capture is the decisive source-time kill test; its
  observed-ET cumulative coverage must retain 390 completed regular-session
  offsets without a guard/concurrency failure.
  The task remains one `IgnoreNew` owner with four runs and no manual rerun.
  This summer-session evidence does not establish DST or pre-market behavior.
- **Pair/QQQ observers:** the daily pair-forward cache is `cache_current` for
  its own contract; the metadata-only QQQ readiness observer has no qualified
  future-window record. Neither condition becomes a general Data or Research
  hold.
- **Broad D1:** the terminal cache has no cursor work. Its low-frequency task
  remains the owner of any future exact-scope collection fact at 00:15 KST; do
  not create a duplicate worker.
- **Forward data:** the 2026-08-05 06:55 KST task-owned QQQ/SPY pair-forward
  run completed `ready`: each named target has seven retained forward rows and
  seven common sessions under its unadjusted, non-PIT source contract. It used
  daily market-data routes only; raw rows remain on `D:`. This narrow later
  observation cannot rewrite a historical campaign or qualify a model, GPU, or
  Paper input. Receipt:
  `D:\thericher-v2\model-artifacts\data\kis-paper-daily-pair-forward-v1\run=20260804T215507025331Z-176c6d006a024f9c\receipt.json`.
- **NAS-forward recovery:** the 06:40 KST `unavailable`/`reconcile` receipt
  predates the current allowlisted failure classifier. Its cache was unchanged,
  the current collector image matches the host source hash, and 32 focused
  offline tests pass; the next existing worker owns recovery.
- **Norgate local capability:** after the no-download metadata probe, NDU was
  started and the fixed-case aggregate receipt is
  `qualified_for_offline_research`. A bounded 1990--2026 request returned only
  the fixed trio's 512 common sessions from 2024-07-18 through 2026-08-03, so
  this trial's useful daily temporal reach is measured rather than inferred.
  Do not repeat the same full-history request without a changed provider fact.
  The snapshot remains source-local; Trial/PIT entitlement, ranking, model,
  GPU, PnL, and Paper eligibility remain false. Evidence:
  `D:\market_data\us_equities\norgate_trial\daily_capability_probe\probe=listener-recovery-20260804-r1-norgate-trial-daily-capability-r1` and
  `D:\market_data\us_equities\norgate_trial\local_d1_etf\snapshot=history-probe-20260804-r1-norgate-trial-raw-d1-r2` with receipt
  `D:\thericher-v2\model-artifacts\data\norgate-local-d1-capability-v1\history-probe-20260804-r1.json`.
  Its target-free structural assessment now reattests the newest snapshot as
  `integrity_attested` with 512 common sessions and 1,536 rows; the receipt
  retains only hashes, counts, and categorical contract facts. It does not
  change any eligibility flag or create a predictive/GPU package. Evidence:
  `D:\thericher-v2\model-artifacts\data\norgate-fixed-etf-d1-structural-integrity-v1\assessment=bf7d5fceae6b2d345dc75132a6e361f79799e6fb419498d8091f180306aaf1aa\assessment.json` and
  `D:\thericher-v2\model-artifacts\research\norgate-scope-readiness\scope-readiness-20260804-r1\assessment.json`.
  A new explicit-snapshot, two-read current-build conformance receipt is
  `matching` with 1,536 reference and active bars and zero divergences. It is
  a repeatability taxonomy only: a future mismatch is `revision_detected`,
  not a data-correctness verdict, and a match proves neither PIT/publication
  timing nor adjustment/capital-event semantics. Model, GPU, PnL, and Paper
  eligibility remain false. Evidence:
  `D:\thericher-v2\model-artifacts\data\norgate-active-build-revision-v1\revision-current-512-20260804-r1\receipt.json`.
  The latest local-client tail probe resolves its `US Equities` update timestamp
  to exactly one active root,
  `D:\market_data\us_equities\norgate_us_platinum_trial`. Its predeclared
  2026-06-23 through 2026-08-04 D1 window has 29 common SPY/QQQ/IWM sessions,
  below the separate 126-session tail contract, so it ends
  `input_unavailable` as `calendar_interval_below_predeclared_minimum`. This
  confirms the current client/root binding only; it does not rebuild the frozen
  snapshot or alter model, GPU, PnL, or Paper eligibility. Evidence:
  `D:\thericher-v2\model-artifacts\data\norgate-trial-tail-readiness-v1\tail-active-build-20260804-r2`.
  A separate hash-bound dividend-marker exclusion sidecar now reattests the
  same 512-session parent: 24 nonzero source markers yielded 72 exclusion rows
  over 55 distinct date groups. It is conservative post-hoc data hygiene only,
  not a statement about event timing, adjustment semantics, PIT availability,
  or any consumer eligibility. Evidence lives in the matching external sidecar.
- **Tiingo D1 marker hygiene:** the immutable three-ETF raw-D1 snapshot now has
  an independently recomputable external sidecar with 330 source-marker
  sessions and 990 marker-or-adjacent observed-session exclusion rows. Its
  parent hashes, scope, and explicit false eligibility flags reattest offline;
  it does not validate event timing or semantics, repair the source's non-PIT
  status, or qualify a model, ranking, sealed holdout, or Paper input. Evidence:
  `D:\market_data\us_equities\tiingo_etf_daily\event_marker_exclusions\snapshot=20260804T104229Z-tiingo-etf-d1-event-exclusions-r1`.
- **Cboe D1 volatility availability/finality:** a metadata-only inventory
  confirms the local 2026-06-18 snapshot has 16 daily volatility-index series,
  including VIX/VXN/RVX, over 1990-01-02 through 2026-06-17; no raw rows were
  inspected. Cboe labels VIX history as updated daily but does not publish a
  daily-endpoint availability timestamp or finality SLA, while its index policy
  allows selected EOD corrections to be recalculated and reissued within two
  business days. These D1 series are therefore `unqualified_for_causal_feature_use`:
  they cannot become same- or next-session features, campaigns, Paper inputs,
  or promotion evidence until a separate source-safe five-session observation
  captures publication and revision behavior. The pure receipt writer accepts
  only the mapped `VIX`/`VXN`/`RVX` Cboe CDN route, hashes one normalized row in
  memory, and revalidates explicit close-relative boundaries. Its new
  credential-free, unscheduled one-series CLI preflights symbol/time/artifact
  scope before its one no-cache request; per-symbol HTTP, schema, or expected
  session-row failure yields only `unavailable`, while `Date`, `Last-Modified`,
  and cache headers are retained only as hashes or `absent`. It has no KIS,
  scheduler, Engine, or Paper import surface. Claude was
  `supported-with-limits`: five real sessions, not the CLI, must measure the
  actual publication bracket and revision behavior. A HEAD mapping probe
  returned `200/text-csv` for all three routes without retaining a body or
  header value; it proves endpoint mapping only, not timing or finality. Evidence:
  `D:\thericher-v2\model-artifacts\data\cboe-volatility-availability-finality-v1\assessment=20260807-r1\assessment.json` and
  `D:\thericher-v2\model-artifacts\data\cboe-volatility-availability-finality-v1\endpoint-mapping-probe=20260807-r1\receipt.json`.
- **Free public augmentation:** no official, no-auth source found that jointly
  establishes PIT/delisting membership, corporate-action meaning, and daily
  OHLCV. SEC Market Structure and EDGAR remain optional source-limited sidecars
  only; no download or promotion is active.
- **SEC schema probe:** the public 2025 Q4 individual-security ZIP is a bounded
  22.4 MB sidecar candidate, but SEC scripted access requires a declared contact
  User-Agent. No designated contact is configured, so no data, provider, or
  promotion was created; a later probe must retain only source-safe coverage.

## Current Quality Contracts

- **Completed QQQ MTF mechanics:** the immutable source-local
  `20260807-qqq-mtf-r1` receipt binds the verified QQQ/NAS M1 catalog
  to the first 20 complete regular 2026 sessions. It reports only aggregate
  M1/M5/M10/H1/H3 completed-bucket geometry and causal commitment; M1=7,800,
  M5=1,560, M10=780, H1=120, and H3=40. The H1/H3 terminal 30-minute buckets
  are explicitly excluded, with no incomplete buckets. It is CPU-only and has
  no provider, credential, broker, target, model, Paper-input, or data
  qualification consequence. Evidence:
  `D:\thericher-v2\model-artifacts\data\source-local-qqq-mtf-resampling-mechanics-v1\20260807-qqq-mtf-r1\summary.json`.
- **Completed QQQ baseline causal-window feasibility:** the immutable
  `20260807-qqq-mtf-window-r3` receipt binds that exact completed mechanics
  contract and source identity to the canonical 15:30 ET `kis_baseline`
  profile. It confirms only aggregate completed windows: M1=600, M5=120,
  M10=60, H1=40, and H3=40 across 20 sessions; H1/H3 each retain 20 explicit
  terminal-partial exclusions. Receipt loading recomputes its parent contract
  hash and rejects repository-resident parent paths. This is target-free,
  CPU-only mechanics, not availability/finality, provider, model, Paper, or
  data-qualification evidence. Evidence:
  `D:\thericher-v2\model-artifacts\data\source-local-qqq-mtf-window-feasibility-v1\20260807-qqq-mtf-window-r3\summary.json`.
- **Completed QQQ causal-window matrix:** the immutable
  `20260807-qqq-mtf-matrix-r2` receipt reattests both external parent receipts
  before binding the same 20-session QQQ/NAS catalog to the ordered canonical
  `short`, `kis_baseline`, `one_hour`, `medium`, `long`, and `extended`
  profiles at 15:30 ET. It retains only aggregate profile/timeframe counts and
  opaque commitments; every profile drops 20 H1 and 20 H3 terminal partial
  buckets. It has no target, availability/finality, provider, model, Paper,
  performance, or data-qualification consequence. Evidence:
  `D:\thericher-v2\model-artifacts\data\source-local-qqq-mtf-window-matrix-v1\20260807-qqq-mtf-matrix-r2\summary.json`.
- All derived `5m`, `10m`, `1h`, and `3h` views must come from a caller-owned,
  exchange-calendar-resampled completed M1 sequence. Partial and gapped bars
  remain unavailable.
- A post-collection observation may say
  `availability_within_validity_after_collection`; it must retain
  `decision_time_availability: not_observed` unless a separately designed
  measurement proves that earlier boundary.
- The QQQ metadata-only local-retention helper binds the exact verified catalog
  hash to the same index bytes and loader filter. Its runtime-window projection
  additionally binds one ready 90-bar input manifest to a caller-supplied
  `decided_at`, reporting `local_input_available_by_decision` only when the
  latest earliest-complete local retention is no later than that decision.
  It rejects incomplete, conflicted, and lineage-mismatched inputs; provider
  decision-time availability and finality remain `not_observed`. It is the
  pre-client local-input check for the named QQQ prospective route only:
  unavailable/late retention produces its local no-intent. It is not a model,
  general Paper-eligibility, or promotion input.
- IWM/AMS is a probe-only M1 target: its request boundary permits one
  current-day page only and has no active collector or consumer contract.
- The D1 stability observer may label only `stable`, `changed`, `unavailable`,
  or `outside_window`; `stable` means two separately timed virtual-Paper reads
  matched, not provider finality, point-in-time availability, data
  qualification, model readiness, or Paper permission.
- Storage remains private under `D:\market_data`; Git contains neither raw
  data nor provider credentials. Do not begin large work below the documented
  free-space floor.

## Recovery

The next identical `minute_duplicate_conflict` is the strongest kill test for
the non-destructive session-capture repair: an existing causal head must remain
retained while the conflicting post-close candidate stays non-promoting. A
single historical conflict, absent cache, source-limited cursor, or worker
cooldown remains scoped to that cache and must not hold Execution, Engine, or
another Data worker.

## Evidence And Handoff

Source-safe worker receipts belong under `D:\thericher-v2\model-artifacts`;
raw snapshots remain on `D:`. Historic coverage, paging, and source-contract
details remain in Git and external artifacts.

After each owned worker runs, reattach only its categorical outcome, durable
cursor or exact cache state, recovery class, and next due fact. Notify Engine
only when a fresh named consumer contract is actually qualified.
