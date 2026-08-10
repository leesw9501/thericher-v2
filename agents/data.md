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
| KIS Paper QQQ/NAS + SPY/AMS intraday head | The fresh 2026-08-11 06:20 KST terminal reattached as `complete` with verified same-run capture and availability bindings. Current-session coverage is `incomplete`; the optional pair binding is `legacy_unbound`, so causal input is `input_unavailable/session_coverage_incomplete` and decision-time availability/provider finality remain `not_observed`. | Diagnose the existing offline aggregation/retention contract only. No model or reusable Paper-candidate promotion; its separately owned QQQ runtime observation remains explicitly provisional. |
| KIS Paper QQQ/SPY M1 cursor cache | 21 shared complete regular sessions; exact cursor scope is exhausted. | Source-local mechanics, fixed local-paper baselines, and target-free window preflight only. |
| KIS Paper private D1 | Unadjusted/partial with finality and as-of facts unavailable. | `input_unavailable` for daily predictive work. |
| KIS Paper IWM/AMS M1 | Isolated current-head v2 observations replay locally; no H1/H3 history. | Current-head mechanics only. Alternate WIP is not an owner path. |
| Tiingo raw D1 ETF trio | The 2026-08-09 immutable SPY/QQQ/IWM snapshot reattested offline through 2026-08-07 with 8,438/6,896/6,588 sessions. | A continuation of already-seen, source-separated non-PIT history: retrospective controls and diagnostics only, never a fresh selection look, threshold calibration, ranking, sealed evaluation, GPU, or Paper input. |
| Tiingo IEX M5 r1 ETF trio | Pinned 2026-07-19 IEX-only snapshot reattested offline by raw hashes, stored gzip hash, and exact canonical payload. | One completed source-isolated reconstruction runtime integration only; no source scope, training eligibility, KIS equivalence, model-selection, or Paper-input change. |
| Norgate trial tail | The host-only `norgatedata` 1.0.77 loopback endpoint responds, but its own readiness status is false. A source-safe status-only probe returned HTTP `402`, which the installed client maps to `NoValidSubscriptions`; the bounded category is `subscription_or_update_unavailable`, not a claim that the trial expired. The reader stops before catalog, update-metadata, or price reads. The existing NDU process has remained responsive since 2026-08-04; a later hidden start merely joined that instance. | Do not launch a second trigger or repeat the hidden start. The next operator-visible diagnostic is in the already-running NDU: inspect `Update > Check for Updates` and the database/subscription state panes, retain only their categorical outcome, then minimize rather than close it. This is an unconfirmed recovery path, not a readiness claim or a hold on other lanes. If status becomes ready, verify the active US subscription and Database Location, then require a catalog exposing `US Equities` before one bounded tail probe. |

Raw market bytes remain under `D:\market_data`. Source-safe receipts and
research artifacts remain under `D:\thericher-v2\model-artifacts`.

## Active Objective

The fresh 06:20 KST terminal is closed as an exact, source-safe
`input_unavailable/session_coverage_incomplete` classification. It differs
from the prior terminal and its existing offline reader recomputed the terminal,
capture, and availability bindings. The result does not establish provider
finality, availability at a decision time, a model input, or a Paper action.

The ready package is a narrow credential-free diagnosis of the current-head
coverage aggregation and retention contract. It may inspect only source-safe
receipt and cache metadata. It must not open raw M1 rows, invoke KIS, Docker,
the installed task, or a parallel collector. If it finds no deterministic
defect, the scoped limitation remains factual rather than becoming a global
provider claim or an Engine/Execution hold.

The offline reader now accepts a separately hash-bound causal-condition
attestation at a fixed external artifact location, but no current task writes
or binds one. An absent binding stays `input_unavailable`; malformed or
mismatched bound evidence fails closed through the existing unavailable reader.
This contract has no collector, credential, network, or schedule behavior.

## Ready / Owned / Due

| Work | Owner | Completion evidence |
| --- | --- | --- |
| Intraday coverage-contract diagnosis | Data / source-safe offline code and receipts | Either a focused deterministic aggregation/retention repair with tests, or evidence that the current `incomplete` result is not repairable offline. |
| Later intraday observation | Existing `thericher-kis-paper-intraday-head` task | A later task-owned terminal may be reattached independently; it does not block the offline diagnosis. |
| Tiingo IEX r1 reattestation | Data | Complete: the fixed snapshot remains hash-bound and source-isolated. No further acquisition, scope change, or consumer promotion follows. |
| SPY D1 stability | Existing task | Its next eligible weekday observation is task-owned; `stable` is not provider finality. |
| Norgate tail readiness | Existing NDU updater, Data, then one operator-visible diagnostic if needed | The responsive NDU instance predates the 2026-08-09T18:34:14Z `UPDATE DONOTSHOW` request; a status-only probe now narrows readiness to `subscription_or_update_unavailable` from HTTP `402`, without determining expiry versus update state. Do not foreground-wait, duplicate either action, or infer a cause. The daily operating review may run the source-safe reader; if it remains unavailable, the one manual diagnostic is visible NDU update plus database/subscription-state inspection, retaining only categorical outcomes. A ready reader must still see `US Equities` before one bounded tail probe. |

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
- Tiingo IEX r1 runtime evidence:
  `D:\thericher-v2\model-artifacts\research\tiingo-iex-r1-representation-integration-v1\r1-cuda-20260810-r1\summary.json`.

## Handoff

When a later task-owned input qualifies, hand Engine Research only its exact
source-safe receipt pointer, source identity, target eligibility, split-ready
time geometry, availability/finality facts, and limitations. Do not choose a
model or construct a Paper order. The current terminal does not meet that
handoff condition.
