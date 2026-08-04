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
| KIS SPY paginated-prefix capability cache | Installed, no runtime receipt yet | Post-collection timing capability only |
| KIS broad NAS D1 panel | Terminal current-listing control | Offline, non-promoting source-local research only |
| Tiingo/Norgate D1 snapshots | Fixed offline controls; Norgate NDU is healthy and its latest capability receipt is offline-only | Source-separated, non-Paper research only |

The broad D1 panel remains current-listing-only, non-PIT, unadjusted or
adjustment-unqualified, corporate-action-unqualified, and session-finality
unattested. Do not promote it to ranking, Paper input, or a qualified model
dataset. The KIS minute endpoint's observed head continuation does not prove
arbitrary historical intraday reach.

## Ready / Owned / Due

- **Current-head recovery:** `thericher-kis-paper-intraday-head` owns the next
  attempt at 2026-08-05 00:31 KST. The prior 06:20 KST result was the scoped
  `minute_duplicate_conflict` for retained QQQ/SPY head candidates.
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
  `qualified_for_offline_research`. A verified fixed-ETF D1 snapshot now has
  502 common sessions and remains source-local. Trial/PIT entitlement, ranking,
  model, GPU, PnL, and Paper eligibility remain false. Evidence:
  `D:\market_data\us_equities\norgate_trial\daily_capability_probe\probe=listener-recovery-20260804-r1-norgate-trial-daily-capability-r1` and
  `D:\market_data\us_equities\norgate_trial\local_d1_etf\snapshot=fresh-tail-20260804-r1-norgate-trial-raw-d1-r2` with receipt
  `D:\thericher-v2\model-artifacts\data\norgate-local-d1-capability-v1\fresh-tail-20260804-r1.json`.
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
