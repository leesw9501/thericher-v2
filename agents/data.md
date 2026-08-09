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
| KIS Paper QQQ/NAS + SPY/AMS intraday head | Latest exact chain is `input_unavailable/session_coverage_incomplete`; its optional causal-attestation binding is `not_recorded`, so decision-time availability and provider finality remain `not_observed`. | Only the installed task may produce a later candidate. No model or reusable Paper-candidate promotion; its separately owned QQQ runtime observation remains explicitly provisional. |
| KIS Paper QQQ/SPY M1 cursor cache | 21 shared complete regular sessions; exact cursor scope is exhausted. | Source-local mechanics, fixed local-paper baselines, and target-free window preflight only. |
| KIS Paper private D1 | Unadjusted/partial with finality and as-of facts unavailable. | `input_unavailable` for daily predictive work. |
| KIS Paper IWM/AMS M1 | Isolated current-head v2 observations replay locally; no H1/H3 history. | Current-head mechanics only. Alternate WIP is not an owner path. |
| Tiingo raw D1 ETF trio | The 2026-08-09 immutable SPY/QQQ/IWM snapshot reattested offline through 2026-08-07 with 8,438/6,896/6,588 sessions. | A continuation of already-seen, source-separated non-PIT history: retrospective controls and diagnostics only, never a fresh selection look, threshold calibration, ranking, sealed evaluation, GPU, or Paper input. |
| Norgate trial tail | The 2026-08-09 host-only `norgatedata` 1.0.77 probe returned `unavailable/local_source_unavailable`; recently written D: database files do not attest current vendor access or rights. | Do not re-probe until Norgate Data Updater shows an active US subscription, then verify its Database Location and run one new bounded tail probe. |

Raw market bytes remain under `D:\market_data`. Source-safe receipts and
research artifacts remain under `D:\thericher-v2\model-artifacts`.

## Active Objective

`task-owned-kis-intraday-causal-evidence-refresh-v1` requires one later exact
QQQ/NAS + SPY/AMS M1 completed-session chain. The old terminal
`intraday-head-20260807T2120007624227Z` is closed only for its own incomplete
coverage condition. It cannot become a provider-wide retention claim or an
Engine/Execution hold.

The task owns the next KST sequence on 2026-08-11 at 00:29, 02:28, 04:24, and
06:20. The 06:20 terminal alone is eligible for a completed-session
classification. Do not manually run the task, its Docker profile, a KIS
client, or a parallel collector.

The offline reader now accepts a separately hash-bound causal-condition
attestation at a fixed external artifact location, but no current task writes
or binds one. An absent binding stays `input_unavailable`; malformed or
mismatched bound evidence fails closed through the existing unavailable reader.
This contract has no collector, credential, network, or schedule behavior.

## Ready / Owned / Due

| Work | Owner | Completion evidence |
| --- | --- | --- |
| Intraday causal evidence refresh | Existing `thericher-kis-paper-intraday-head` task | Exact terminal plus matching capture, availability, and optional pair hashes; reader recomputes the named availability-summary bytes. |
| Offline classification | Data after task terminal | `qualified` only with completed-session geometry, chronological split, decision-time availability, and provider finality. Otherwise record the narrow unavailable reason. |
| SPY D1 stability | Existing task | Next 2026-08-10 23:15 KST observation; `stable` is not provider finality. |
| Norgate tail readiness | Norgate local source | Blocked only for this source: wait for Norgate Data Updater to show an active subscription, then run one new bounded probe; do not foreground-retry. |

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
- Preserve a durable serial cursor only after a useful capability probe
  establishes continuation semantics. Do not replace measurement with a
  parallel request flood.
- One collector keeps its in-memory KIS client/token while valid. The
  five-minute cross-process token-start guard spaces fresh token POSTs only;
  it is never a foreground sleep or token lifetime.
- Data limitations are visible to their exact consumer. They never become a
  global approval gate or suppress an independent lane.
- Tiingo's fixed ETF trio is a repeated historical sample, not independent
  evidence. Its non-PIT scope cannot calibrate a later model-side threshold or
  filter, and it cannot be joined into the KIS causal/Paper path.

## Current Evidence

- Intraday source-safe projection:
  `scripts\project_kis_paper_intraday_head_schedule_receipt.py`.
- Official KIS overseas-minute documentation confirms the reviewed request and
  cursor semantics but supplies no reviewed finality/as-of predicate. It keeps
  `provider_finality` and decision-time availability `not_observed`; it makes
  no KIS call or consumer change. Evidence:
  `D:\thericher-v2\model-artifacts\data\provider-documentation-retrieval\kis-overseas-minute-finality-surface-20260809-r1\source-retrieval.json`.
- QQQ multi-timeframe completed-bar mechanics:
  `D:\thericher-v2\model-artifacts\data\source-local-qqq-mtf-resampling-mechanics-v1\20260807-qqq-mtf-r1\summary.json`.
- QQQ MTF canonical window matrix:
  `D:\thericher-v2\model-artifacts\data\source-local-qqq-mtf-window-matrix-v1\20260807-qqq-mtf-matrix-r2\summary.json`.
- Tiingo raw-D1 collection receipt:
  `D:\thericher-v2\model-artifacts\data-receipts\tiingo-etf-d1\4a2344b7ab8ec2eaf0b1a5e4afcd41e07cf0b4c14e13db64d07b41fd054883d2.json`.

## Handoff

When a later task-owned input qualifies, hand Engine Research only its exact
source-safe receipt pointer, source identity, target eligibility, split-ready
time geometry, availability/finality facts, and limitations. Do not choose a
model or construct a Paper order.
