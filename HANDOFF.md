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
  `minute_duplicate_conflict`; its isolated next attempt is task-owned at
  00:31 KST. A repeated same-scope result is the only trigger for a narrow
  conflict-origin recovery package.
- SPY paginated-prefix negative-control and feasibility workers are installed
  for 04:29:30 and 04:30 KST. They have a dedicated cache and can establish
  only post-collection availability, never retrospective decision-time
  availability.
- The daily pair-forward cache is `cache_current` only for its named source
  contract. The metadata-only QQQ readiness observer is independent and has no
  qualified future-window record.
- The broad KIS D1 current-listing panel is a source-local research control,
  not a point-in-time, adjusted, corporate-action-qualified, or Paper-ready
  dataset. Historical minute reach remains endpoint-limited.
- Norgate NDU is running and its new aggregate capability receipt is
  `qualified_for_offline_research` only. The latest verified fixed-ETF D1
  snapshot has 502 common sessions through its bounded fresh tail, but the
  trial does not establish PIT, ranking, model,
  GPU, PnL, or Paper eligibility. Its raw snapshot remains under
  `D:\market_data`; use it only through its source-local contract.

### Engine Research And Stewardship

- No frozen, input-qualified campaign is ready. The RTX 4090 is free by design;
  do not manufacture training to fill it.
- The completed Granite TTM R1 run is a structural CPU/CUDA compatibility
  receipt only. It has no market input, forecast score, model selection,
  checkpoint promotion, ensemble, or Paper consequence.
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
  exact unknown before any same-intent recovery. It never reads a live route.
- The offline validator accepts completion only for `paper_only`, terminally
  cancelled, cleanly reconciled, freshness-valid evidence. The loopback
  dashboard is read-only, credential-free, and price/order-identifier-free.
- The latest safe private-state inventory has no `submitted` or
  `cancel_started` canary phase. Historical unknowns remain scoped to their own
  reconciliation paths.
- `quote-session`, `daily-spy-head`, and `daily-spy-session` are explicitly
  Monday--Friday KST. This restores Monday US-session coverage without changing
  services, order logic, sizing, or KIS routes.

## Current Ready / Owned / Due

| Work | Owner | Status |
| --- | --- | --- |
| Virtual-Paper lifecycle canary | Execution | Existing worker due 2026-08-04 23:35 KST |
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
- The newest Claude CLI canary and governance invocations timed out. Record
  `review_unavailable`, never agreement. Prior bounded reviews remain scoped to
  their named decisions.
- The Codex app monitor editor also timed out. Its existing Tuesday watch still
  covers tonight; installed Windows tasks remain the primary evidence. Retry the
  future weekday alignment only through the official app API, never by editing
  its TOML directly.

## Verification And Git

- The latest code-changing package passed
  `2442 passed, 23 skipped` through
  `scripts/run_parallel_tests.ps1 -RequireCleanTempRoot`, plus Ruff and all
  required Compose configurations.
- Recent commits: `da12ccd` aligns same-date KST Paper task weekdays,
  `a6a51a9` records worker throughput, and `7202d4d` records monitor recovery.
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
3. When Data produces a fresh qualified causal input, freeze the next distinct
   Engine contract and let Research Steward allocate GPU only if it is eligible.
4. At a company-goal boundary, run required verification, commit/push, replace
   `NEXT_CODEX_GOAL.md` with one material next objective, and refresh only the
   changed current facts in these projections.
