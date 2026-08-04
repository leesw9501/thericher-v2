# TheRicher v2 Handoff

## Product Direction

TheRicher v2 is a private, reproducible US-equity research and KIS Paper
trading engine. The product loop is: causal market data -> frozen research
contract -> backtest/walk-forward evidence -> local-paper replay -> KIS Paper
execution evidence -> PnL attribution. KIS Paper is early execution evidence,
not a reward for a profitable model. `KIS_LIVE_*` is unavailable.

`AGENTS.md` owns policy. `NEXT_CODEX_GOAL.md` owns the one current bounded
company objective. The role stateboards are current projections only; Git and
external artifacts retain history.

## Current Objective

`kis-paper-virtual-lifecycle-canary-v2` must reattach one current,
task-owned, virtual-Paper lifecycle result through the existing deterministic
canary. It may end as a categorical no-intent, rejected,
cancelled-and-clean, or unknown-and-reconciled result. It is never a model,
fill, PnL, or profitability result.

As of 2026-08-04 12:20 KST, no new Aug. 4 canary artifact exists. The existing
`thericher-kis-paper-quote-session` Windows task is `Ready` for 23:35 KST with
one Monday--Friday trigger. Do not manually invoke or duplicate it.

## Current Lane Facts

### Data

- Market data remains under `D:\market_data`; generated artifacts remain under
  `D:\thericher-v2\model-artifacts`.
- The KIS current-head collector last closed as the scoped
  `minute_duplicate_conflict` from a stale `retained_cache` candidate; that
  head is already quarantined. Its isolated next attempt is task-owned at
  00:31 KST. A repeated same-scope result is the only trigger for a narrow
  conflict-origin recovery package.
- The existing KIS M1 cursor chains for QQQ/NAS and SPY/AMS are terminally
  `source_exhausted` after their retained 2026-06-22 through 2026-07-21 spans
  (about 20,000 rows per target). The offline reattachment issued no market
  request and created no snapshot. This is an exact route/cursor fact, not a
  general KIS historical-retention claim; do not invent a timestamp seed.
  A source-safe geometry assessment finds 21 shared complete 09:30--15:29 ET
  sessions, enough only for a source-local non-promoting 5--90 minute preflight;
  decision-time availability and model/Paper eligibility remain false. Evidence:
  `D:\thericher-v2\model-artifacts\data\kis-m1-cursor-session-geometry-v1\assessment.json`.
- SPY paginated-prefix negative-control and feasibility workers are installed
  for 04:29:30 and 04:30 KST. They have a dedicated cache and can establish
  only post-collection availability, never retrospective decision-time
  availability.
- The daily pair-forward cache is `cache_current` only for its named source
  contract. The metadata-only QQQ readiness observer is independent and has no
  qualified future-window record.
- The installed 22:15 KST SPY D1 head task currently produces a verified
  prior-session cache snapshot, not a capability/qualification or a
  provider-finality/decision-time availability fact. Its static trace is
  `producer_path_missing`. The reviewed
  `thericher-kis-paper-daily-spy-stability-observer` is installed for 23:15
  KST on weekdays and owns the first distinct, exact-scope D1 comparison. It
  uses the shared KIS request/token gates, a nonblocking external receipt lock,
  and at most one virtual-Paper `dailyprice` attempt after a verified
  15--90-minute-old snapshot and successful authentication. It has no runtime
  receipt yet. `stable` can mean only matching prior-session row hashes; it
  always retains `provider_finality: not_observed` and remains Engine-unreadable.
  Do not build a consumer bridge from it alone. Evidence:
  `D:\thericher-v2\model-artifacts\data\daily-spy-input-readiness\static-trace-20260804-r1\assessment.json`.
- The broad KIS D1 current-listing panel is a source-local research control,
  not a point-in-time, adjusted, corporate-action-qualified, or Paper-ready
  dataset. Historical minute reach remains endpoint-limited.
- Norgate NDU is running and its new aggregate capability receipt is
  `qualified_for_offline_research` only. The latest verified fixed-ETF D1
  snapshot came from a 1990--2026 request but contains only 512 common sessions
  from 2024-07-18 through 2026-08-03 and 1,536 rows. This measures the trial's
  current useful daily reach; do not repeat the same full-history request
  without a changed provider fact. Its source-safe structural receipt attests
  only the raw-file geometry and manifest/hash contract, not eligibility. The
  trial does not establish PIT, ranking, model, GPU, PnL, or Paper eligibility.
  Its raw snapshot remains under `D:\market_data`; use it only through its
  source-local contract. Evidence:
  `D:\thericher-v2\model-artifacts\data\norgate-fixed-etf-d1-structural-integrity-v1\assessment=bf7d5fceae6b2d345dc75132a6e361f79799e6fb419498d8091f180306aaf1aa\assessment.json`.
- An official free-source check found no single public panel that establishes
  point-in-time membership including delistings, corporate-action semantics,
  and daily OHLCV. SEC Market Structure and EDGAR can be bounded sidecars only,
  not a qualified model or Paper input. Its 2025 Q4 sidecar ZIP is 22.4 MB, but
  a scripted probe needs a designated contact User-Agent; no data was retained.

### Engine Research And Stewardship

- No frozen, input-qualified campaign is ready. The RTX 4090 is free by design;
  do not manufacture training to fill it.
- The completed Granite TTM R1 run is a structural CPU/CUDA compatibility
  receipt only. It has no market input, forecast score, model selection,
  checkpoint promotion, ensemble, or Paper consequence.
- Chronos-T5 Small is an independently retrieved Apache-2.0 source-only
  candidate. Its forecast input is documented, but its pretraining
  period/financial-instrument scope and hidden-representation interface are not
  disclosed. It has no downloaded weights, execution, campaign, GPU, ensemble,
  Paper, or profitability consequence. Evidence:
  `D:\thericher-v2\model-artifacts\research\engine-source-retrieval\chronos-t5-small-20260804-r1\source-retrieval.json`.
- Moreira and Muir's volatility-managed exposure is independently retrieved as
  a source-only sizing candidate. Its monthly realized-variance mechanism
  needs a future frozen causal D1 baseline and qualified later evaluation
  input; it has no campaign, GPU, PnL, or Paper consequence. Evidence:
  `D:\thericher-v2\model-artifacts\research\engine-source-retrieval\volatility-managed-exposure-20260804-r1\source-retrieval.json`.
- The independently retrieved extreme intraday shock-reversal mechanism is a
  source-only event-triggered mean-reversion candidate. The project lacks its
  source-style liquidity/spread inputs, 60-session per-symbol seasonal M1
  baseline, completed-bar availability evidence, and candidate-specific replay
  parity, so it has no campaign, GPU, PnL, or Paper consequence. Evidence:
  `D:\thericher-v2\model-artifacts\research\engine-source-retrieval\kis-intraday-extreme-shock-reversal-20260804-r1\source-retrieval.json`.
- The independently retrieved session-reset VWAP directional-state source is
  `source_only_input_unavailable`. Its source-native state holds to a later
  VWAP-side change or session close, not the discovery handoff's fixed
  30-minute horizon. The current M1 cache lacks observed decision-time
  availability and candidate-specific replay parity, so it has no campaign,
  code, GPU, PnL, or Paper consequence. Evidence:
  `D:\thericher-v2\model-artifacts\research\engine-source-retrieval\qqq-session-vwap-state-continuation-20260804-r1\source-retrieval.json`.
- The independently retrieved five-minute opening-range-breakout source is a
  distinct `source_only_input_unavailable` technical-rule candidate. Its
  source-native screened form needs a contemporaneous multi-symbol universe,
  prior 14-session liquidity/ATR facts, and relative opening-range volume; the
  current two-ETF, 21-session M1 cache lacks those inputs and observed
  decision-time availability. It has no campaign, code, GPU, PnL, or Paper
  consequence. Evidence:
  `D:\thericher-v2\model-artifacts\research\engine-source-retrieval\us-equity-five-minute-orb-20260804-r1\source-retrieval.json`.
- Closed or non-reusable historical families include QQQ MTF consensus,
  first-30/final-30 momentum, MTF logistic, lower-tail quantile preflight,
  Tiingo rotation/sequence controls, and static broad-D1 benchmarks. A later
  research package must state a distinct hypothesis, causal source, temporal
  split, cost model, baseline, kill test, and data lineage.
- The fixed prospective SPY MTF baseline remains a data-timing control only.
  It needs a future qualified source receipt before any model, GPU, or Paper
  interpretation.

### Execution

- The canary is virtual-host-only at
  `openapivts.koreainvestment.com:29443`, HTTPS, no redirects, and the existing
  quote/account/order/cancel allowlist.
- It persists one durable intent before a broker effect, uses a shared state
  lock, requires a fresh account/open-order view and fresh quote-derived limit,
  rejects matching open orders, uses `cancel_after_submit`, and reconciles an
  exact unknown before any same-intent recovery. Before a fresh quote, a prior
  matching `SPY`/`AMEX`/buy/one-share pending state is recovered; if it remains
  ambiguous, only that fresh session returns `recovery_required` with no new
  quote or order. It never reads a live route.
- The offline validator accepts completion only for `paper_only`, terminally
  cancelled, cleanly reconciled, freshness-valid evidence. The loopback
  dashboard is read-only, credential-free, and price/order-identifier-free.
- The latest safe private-state inventory has no `submitted` or
  `cancel_started` canary phase. Historical unknowns remain scoped to their own
  reconciliation paths; only an exact matching pending canary defers the next
  matching quote session.
- The host lifecycle projector now proves both a valid sanitized lifecycle
  projection and the missing-evidence `unavailable`/exit-2 contract offline.
- `quote-session`, `daily-spy-head`, and `daily-spy-session` are explicitly
  Monday--Friday KST. This restores Monday US-session coverage without changing
  services, order logic, sizing, or KIS routes.

## Current Ready / Owned / Due

| Work | Owner | Status |
| --- | --- | --- |
| Virtual-Paper lifecycle canary | Execution | Existing worker due 2026-08-04 23:35 KST |
| SPY D1 stability observation | Data | Installed worker due 2026-08-04 23:15 KST |
| Current-head duplicate recovery | Data | Existing worker due 2026-08-05 00:31 KST |
| SPY paginated-prefix capability | Data | Existing workers due 2026-08-05 04:29:30/04:30 KST |
| GPU research | Research Steward | Idle because no eligible frozen campaign exists |

An external wait belongs to its worker. Do not foreground-sleep, add a duplicate
schedule, or turn a source result into an approval hold while another lane is
ready.

## Current Recovery And Review Facts

- A current canary runtime projection is absent from the repo worktree, and no
  Aug. 4 external canary/session/validator result existed at the latest safe
  inspection. This is expected before the scheduled task runs.
- The 2026-08-04 recovery review returned `supported-with-limits`: keep the
  preflight exact-scope, prohibit a fresh submit from recovery, preserve a
  remaining ambiguity as a session-scoped result, and retain the shared lock.
  It is a challenge result, not authority or a broker outcome.
- A later Claude CLI call returned `unsupported` from a mismatched workspace:
  it cited absent `docs/` and `attestations/` paths and a stale Git history,
  while the current tree contains the canary module, projector, and allowlist
  tests. Classify that response as `review_invalid_workspace`, not as a
  substantive adverse verdict or a canary hold. No execution boundary changed.
- A separate 2026-08-04 D1 bridge drift review returned `uncertain`: the bridge
  must not infer provider finality from a cached snapshot or write an
  Engine-readable observed-only result until a distinct availability/stability
  producer and exact verification predicate exist. A revised bounded stability
  producer received `supported-with-limits`; independent review caught and then
  verified repairs for auth-attempt accounting, shared KIS gates, and its
  cross-process receipt lock. No bridge was implemented.
- The Codex app monitor editor also timed out. Its active result monitor runs
  Monday--Friday at 23:45 KST; installed Windows tasks remain the primary
  evidence. Retry future edits only through the official app API, never by
  editing its TOML directly.

## Verification And Git

- The recovery package passed `113` focused execution/schedule/dashboard tests,
  then `2448 passed, 23 skipped` through
  `scripts/run_parallel_tests.ps1 -RequireCleanTempRoot`, plus full Ruff and
  all required Compose configurations. These are local-contract checks, not a
  substitute for the task-owned current broker result.
- The current pre-session reattestation additionally passed 137 focused
  canary/intent/quote/receipt/lifecycle/dashboard/schedule tests with no broker
  or credential access. It confirms the deterministic boundary only, not a
  current lifecycle outcome.
- Recent commits: `d0223ab` hardens exact Paper-canary recovery, `da12ccd`
  aligns same-date KST Paper task weekdays, and `a6a51a9` records worker
  throughput.
- Historic stateboard and handoff entries remain searchable in Git. Immutable
  source-safe receipts, model manifests, and runtime evidence remain external
  under `D:\thericher-v2\model-artifacts`; raw market data remains on `D:`.
- The latest known pre-current canary session evidence is
  `D:\thericher-v2\model-artifacts\execution\kis-paper-canary-session\paper-session-20260801T143501387961Z\evidence.json`.
  Granite structural runtime evidence is under
  `D:\thericher-v2\model-artifacts\research\granite-ttm-r1-isolated-runtime-smoke-v1`.

## Next Handoff

1. Reattach the quote-session worker's source-safe result after 23:35 KST using
   the existing runtime projection and offline validator. Do not infer a broker
   result from missing evidence.
2. Continue independent Data worker reattachment at its own due times.
3. Reattach the installed D1 stability observer after its 23:15 KST run. Treat
   any result as source-safe observational evidence only; do not treat the
   cache snapshot or a `stable` result as provider-finality evidence.
4. When Data produces a fresh qualified causal input, freeze the next distinct
   Engine contract and let Research Steward allocate GPU only if it is eligible.
5. At a company-goal boundary, run required verification, commit/push, replace
   `NEXT_CODEX_GOAL.md` with one material next objective, and refresh only the
   changed current facts in these projections.
