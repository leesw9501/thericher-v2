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
| KIS Paper QQQ/SPY M1 cursor cache | Terminal exact cursor scope with 21 shared complete 09:30--15:29 ET sessions | Source-local, non-promoting 5--90 minute geometry preflight only |
| KIS Paper IWM/AMS M1 candidate | One accepted current-day page through a probe-only route | Provisional route fact only; no history, qualification, or consumer promotion |
| Yahoo intraday starter M1 manifest | Bounded metadata-only 8-day probe with one successful symbol | `input_unavailable` for source-native multi-symbol ORB; no raw scan or promotion |
| KIS Paper SPY D1 stability observer | Installed, no runtime receipt yet | Bounded source-safe observation only; never a qualification or consumer bridge |
| KIS SPY paginated-prefix capability cache | Installed, no runtime receipt yet | Post-collection timing capability only |
| KIS broad NAS D1 panel | Terminal current-listing control | Offline, non-promoting source-local research only |
| Tiingo/Norgate D1 snapshots | Fixed offline controls; Norgate NDU is healthy and its latest capability receipt is offline-only | Source-separated, non-Paper research only |

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

- **Current-head recovery:** `thericher-kis-paper-intraday-head` owns the next
  attempt at 2026-08-05 00:31 KST. The prior 06:20 KST result was the scoped
  `minute_duplicate_conflict` for retained QQQ/SPY head candidates. Offline
  diagnosis classifies the origin as `retained_cache`; the conflicting head is
  already quarantined, so the next worker alone can confirm recovery. A repeat
  is the kill test for a narrow collector repair; no pre-run code change is due.
- **Historical M1 cursor scope:** the existing QQQ/NAS and SPY/AMS backfill
  indices were reattached offline as `source_exhausted`, with no new market-data
  page or snapshot. Do not reopen either terminal cursor with an invented seed;
  a changed endpoint, symbol, or provider behavior needs its own bounded probe.
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
  Evidence: `D:\thericher-v2\model-artifacts\data\daily-spy-input-readiness\static-trace-20260804-r1\assessment.json`.
- **SPY prefix capability:** the negative control and feasibility tasks own
  2026-08-05 04:29:30 and 04:30 KST. One dedicated client/cache namespace may
  inspect at most four pages of 120 rows and must validate seams plus the exact
  completed 09:30--15:29 ET prefix.
- **Pair/QQQ observers:** the daily pair-forward cache is `cache_current` for
  its own contract; the metadata-only QQQ readiness observer has no qualified
  future-window record. Neither condition becomes a general Data or Research
  hold.
- **Broad D1:** the terminal cache has no cursor work. Its low-frequency task
  remains the owner of any future exact-scope collection fact at 00:15 KST; do
  not create a duplicate worker.
- **Forward data:** existing daily pair/forward workers remain independent.
  Their source-safe result can qualify only the named later observation, never
  rewrite a historical campaign.
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
- **Free public augmentation:** no official, no-auth source found that jointly
  establishes PIT/delisting membership, corporate-action meaning, and daily
  OHLCV. SEC Market Structure and EDGAR remain optional source-limited sidecars
  only; no download or promotion is active.
- **SEC schema probe:** the public 2025 Q4 individual-security ZIP is a bounded
  22.4 MB sidecar candidate, but SEC scripted access requires a declared contact
  User-Agent. No designated contact is configured, so no data, provider, or
  promotion was created; a later probe must retain only source-safe coverage.

## Current Quality Contracts

- All derived `5m`, `10m`, `1h`, and `3h` views must come from a caller-owned,
  exchange-calendar-resampled completed M1 sequence. Partial and gapped bars
  remain unavailable.
- A post-collection observation may say
  `availability_within_validity_after_collection`; it must retain
  `decision_time_availability: not_observed` unless a separately designed
  measurement proves that earlier boundary.
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

The next identical `minute_duplicate_conflict` is the strongest kill test for a
narrow origin/receipt repair. A single historical conflict, absent cache,
source-limited cursor, or worker cooldown remains scoped to that cache and must
not hold Execution, Engine, or another Data worker.

## Evidence And Handoff

Source-safe worker receipts belong under `D:\thericher-v2\model-artifacts`;
raw snapshots remain on `D:`. Historic coverage, paging, and source-contract
details remain in Git and external artifacts.

After each owned worker runs, reattach only its categorical outcome, durable
cursor or exact cache state, recovery class, and next due fact. Notify Engine
only when a fresh named consumer contract is actually qualified.
