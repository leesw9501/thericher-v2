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
| Tiingo/Norgate D1 snapshots | Fixed offline controls; Norgate local metadata is present but its NDU listener is unavailable | Source-separated, non-Paper research only |

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
- **Norgate local capability:** the 2026-08-04 no-download metadata probe found
  package `1.0.77` and a DB-build fingerprint but no listener at local port
  `38889`. When NDU is healthy, run only the existing aggregate-only fixed-case
  probe; current trial/PIT entitlement remains unverified and cannot qualify a
  historical ranking or Paper input. Evidence:
  `D:\thericher-v2\model-artifacts\data\norgate-local-d1-capability-v1\metadata-probe-20260804-r1.json`.

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
