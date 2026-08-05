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

The existing `thericher-kis-paper-quote-session` Windows task completed its
2026-08-04 23:35 KST invocation with Task Scheduler result `0`. Its exact
scheduled-session receipt is `paper-session-20260804T143501870818Z`, which
reattaches only `recovery_required/prior_submission_unresolved` to the
preserved run `canary-20260722T184759527919Z`; the independent lifecycle
validator also reports `outcome_unknown/unresolved`. This is not a new
lifecycle, broker, fill, no-intent, or PnL result. Do not manually invoke,
infer an outcome, or duplicate the task; the next task-owned opportunity is
2026-08-05 23:35 KST.

The matching 2026-08-04 23:50 KST daily SPY session receipt is exactly
`daily-spy-20260804T145002356832Z`: `no_intent/quote_unavailable`, with no
run identity and both receipt observer and terminal-field probe
`not_attempted`. It is a categorical daily-session no-intent only, not a
broker, fill, or PnL fact. The 22:15 KST daily-head task exited `0` but still
has only the static `producer_path_missing` consumer trace. The 06:20 KST
intraday-head task exited `20`; its exact safe runtime is
`intraday-head-20260804T2120059626443Z`,
`recovery/prospective_session_id_unavailable`. That anomaly is local to the
downstream session binding; its task owns the 2026-08-06 00:29 KST retry.

The current daily-SPY session image preserves `quote_unavailable` only for a
fresh quote-fetch failure and emits `receipt_preparation_unavailable` for a
local receipt/limit-preparation failure. This changes neither the preserved
08-04 receipt nor any Paper call, intent, or schedule. Its 141 focused
execution tests and the 2,573-pass, 23-skip parallel authority suite passed;
the existing single `IgnoreNew` task was rebuilt for 2026-08-05 23:50 KST.

Engine Research independently re-retrieved QuantConnect LEAN's Apache-2.0
Donchian channel source and prepared a pure session-reset `20/10` long/flat
rule with causal, contiguous completed-bar tests. It performs no I/O and has
no KIS, broker, data-collection, backtest, GPU, or Paper connection. This is
only a source-verified engineering baseline: the source has no adopted market
evaluation claim and the current data remains insufficient for a campaign,
profitability, or promotion conclusion.

At 03:16 KST on 2026-08-05, one exact read-only historical terminal-field
probe ran for the preserved legacy state. It used only a virtual token and the
history GET route, returning `history_observed_derived_date` with an absent
identity row. Because its ET day is derived from a tightly checked legacy
creation timestamp, that result is not a no-order, cancellation, terminal,
fill, or PnL conclusion; the legacy state remains `outcome_unknown`.

The quote-session runner now recovers only an exact replayed run from its own
durable state. A distinct new run retains the shared lock and its fresh
account/open-order reconciliation, which blocks a current matching open order
before submit. It no longer scans or mutates unrelated historical state files.
The old state is preserved, not relabeled clean. At 03:50 KST, a new
source-free Claude drift review returned `supported-with-limits`: it supports
the virtual-host, durable-intent, lock, fresh-account/quote, and current
open-order kill tests, but it leaves unqualified a distinct historical unknown
that is not yet visible in KIS's current open-order view and a runner failure
between submit and reconciliation. Those are scope limits, not an inference of
an order or a global Paper hold. Temporary Validation independently classified
that concern as a documented scope limit, not a pre-23:35 task contract
violation; its strongest missing evidence is delayed broker visibility after a
prior distinct unknown. Focused fake-route tests cover same-run recovery,
old-state preservation, and current-open-order no-submit behavior.

Verification for this recovery package passed 129 focused execution tests and
the authority parallel suite with 2,543 passed and 23 skipped. Full Ruff and
all required Compose configurations passed, and the current `kis-paper-session`
image was rebuilt for the existing task. A separate serial `pytest -q`
diagnostic exceeded the desktop ten-minute command limit and is not a passing
result; the already-passing authority suite remains the required verification
for this private Paper change.

The offline projector now also accepts one explicit session ID. It rejects
links, `.`/`..`, mismatched IDs, and non-writer evidence shapes, emits a
distinct session fact without its evidence path, and never scans for a latest
artifact. A pre-canary runtime whose safe ID is `paper-session-*` can bind that
exact receipt. For `prior_submission_unresolved`, the prior direct-canary
runtime remains `outcome_unknown`/`unresolved`; it is not overwritten by a
generic session runtime and still requires direct lifecycle reattachment.

The 23:15 D1 stability observer and retimed intraday-head worker also remain
task-owned with `IgnoreNew` concurrency. The D1 observer completed its first
23:15 KST receipt as `stable`: one `dailyprice` GET, no retry or foreground
wait, and an independently verified 15--90-minute snapshot comparison. It is
observational only, with `provider_finality: not_observed`, and cannot qualify
an Engine or Paper consumer. The next intraday-head collection is task-owned at
00:29 KST on 2026-08-06.

On its next successful collection, the existing retimed intraday-head worker
also dispatches the already implemented QQQ 90-minute observed/provisional
baseline before slower observers can exhaust its two-minute freshness budget.
It uses the existing local-paper replay, virtual-only receipt canary, and
network-disabled exact-session validator; it has no new schedule or broker
route. It may record a scoped `no_intent` or lifecycle fact, never an alpha,
PnL, or promotion result. The source-free Claude challenge timed out
(`review_unavailable`), while the host dispatcher simulation and focused
execution tests passed.

## Current Lane Facts

### Data

- Market data remains under `D:\market_data`; generated artifacts remain under
  `D:\thericher-v2\model-artifacts`.
- One authorized standard-Tiingo-EOD retrieval completed at 2026-08-04 23:13
  UTC for the fixed `SPY`/`QQQ`/`IWM` scope. Its immutable external snapshot
  has 39 normalized rows through source date 2026-07-28 and reattests offline
  without a token or network path. It is future-lineage only: it cannot
  qualify historical D1 controls, model training, ranking, Paper input, or an
  order action.
- The KIS current-head collector last closed as the scoped
  `minute_duplicate_conflict` from a stale `retained_cache` candidate; the
  historical quarantine remains evidence only. Its 2026-08-05 02:31 KST
  collection exited zero, then its downstream QQQ session could not bind an
  exact ID, producing scoped recovery `20` with no broker action. Do not infer
  its downstream stage or manually rerun it. The former 04:31 KST task's terminal
  receipt is separately `recovery: collection_exit_nonzero`: its fresh token
  start followed the 04:30 SPY-prefix collector inside the existing
  cross-process five-minute token-start guard. Its downstream QQQ/Paper stages
  are all `not_applicable`, and the existing worker owns the 06:20 KST retry.
  Its terminal writer now advances one task-owned current
  pointer only after the immutable source-safe receipt exists. The host
  projector reattaches that pointer only when its exact non-link receipt hash,
  run identity, observed timestamp, and terminal category agree; it makes no
  KIS, Docker, network, or credential call and never selects a latest artifact.
- A metadata-only QQQ row-key inspection then established that the successful
  pages covered 09:32--11:31, 11:32--13:31, and 15:20--15:59 ET, while the
  missing mid-session range was caused by the 04:31 guard collision. After
  Claude returned `supported-with-limits`, Codex re-registered the same
existing single-action, four-run `IgnoreNew` task at 00:29, 02:28, 04:24,
and 06:20 KST. The 04:24 time leaves 5m30s before the prefix control and
six minutes before the prefix collector. The scheduled four-run session is the
sole coverage setup; the terminal 06:20 KST session capture is the kill test: its
observed-ET cumulative coverage must show 390 completed regular-session
minutes without guard/concurrency failure. The rebuilt existing image emits
this metadata-only cumulative projection from the local index/manifests while
preserving separate exact-run coverage; it excludes adjacent dates and is not
a causal, finality, Engine, or Paper input. DST/pre-market behavior remains
unproven; this is a reversible current-season repair, not an input promotion.
  Focused schedule checks (18) and the full parallel authority suite
  (2,571 passed, 23 skipped) passed after task registration.
- New `session-capture` executions preserve an existing causal head snapshot
  when a later post-close candidate conflicts, and reject that candidate
  pending bounded reconciliation. They do not auto-prefer revised post-close
  values or create a model input. The rebuilt Docker image carries this change;
  Claude's source-safe check was `supported-with-limits` and 65 focused
  collector/session-capture tests passed.
- The existing KIS M1 cursor chains for QQQ/NAS and SPY/AMS are terminally
  `source_exhausted` after their retained 2026-06-22 through 2026-07-21 spans
  (about 20,000 rows per target). The offline reattachment issued no market
  request and created no snapshot. This is an exact route/cursor fact, not a
  general KIS historical-retention claim; do not invent a timestamp seed.
  A source-safe geometry assessment finds 21 shared complete 09:30--15:29 ET
  sessions, enough only for a source-local non-promoting 5--90 minute preflight;
  decision-time availability and model/Paper eligibility remain false. Evidence:
  `D:\thericher-v2\model-artifacts\data\kis-m1-cursor-session-geometry-v1\assessment.json`.
- The offline QQQ local-retention helper binds a verified catalog to exact index
  metadata. Its runtime-window projection binds one ready 90-bar input manifest
  to a named `decided_at` and reports local availability only when the selected
  bars were retained no later than that time. It rejects source/lineage,
  conflict, candidate-conflict, and incomplete-row mismatches; provider
  decision-time availability and finality remain `not_observed`. The named QQQ
  prospective route now consumes it before any KIS client interaction, ending
  as a scoped no-intent when local retention is missing or late. It remains
  outside model training, GPU allocation, PnL, and general Paper eligibility.
- A one-page, current-day-only KIS Paper IWM/AMS M1 capability probe was
  accepted. Query, client, and transport boundaries all prohibit previous-day
  and continuation use, and the probe discarded returned rows. This establishes
  only a provisional current-page route; it does not establish historical reach,
  venue correctness, session finality, decision-time availability, a qualified
  dataset, or model/GPU/Paper eligibility. Evidence:
  `D:\thericher-v2\model-artifacts\data\kis-paper-minute-capability-probe\iwm-ams-candidate-assessment-20260804-r1.json`.
- A bounded metadata-only probe of the existing Yahoo intraday-starter M1
  manifest is `input_unavailable` for the new five-minute ORB source family:
  it has an eight-day request span, one successful symbol, and no explicit
  regular-session or decision-time-availability field. It is not reopened as a
  raw-data scan, provider qualification, campaign, model, GPU, PnL, or Paper
  input. Evidence:
  `D:\thericher-v2\model-artifacts\data\yahoo-intraday-starter-orb-input-probe-v1\assessment.json`.
- `thericher-kis-paper-spy-prefix-negative-control` and
  `thericher-kis-paper-spy-prefix-feasibility` completed their 2026-08-05
  04:29:30 and 04:30 KST attempt. The negative control was clean; the exact
  SPY/AMS M1 run accepted one page with 119 completed prefix minutes, 241
  missing, an invalid seam, and no next cursor. The legacy receipt did not
  retain a safe terminal continuation category, so the offline projection marks
  it `not_recorded_legacy`; it cannot distinguish a blank/absent response
  signal from an unrecognized nonblank one. New exact runs retain only a safe
  category, never a raw response-header value. It used one in-memory client,
  one token attempt, and one minute-page attempt. This is an exact pagination
  observation, not a provider-wide KIS conclusion. Its existing worker owns
  the next attempt. Its existing collector/observer images were rebuilt and
  the same tasks re-registered for the safe-category contract; trigger times,
  `IgnoreNew`, and zero restart count are unchanged. The cache can establish
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
  15--90-minute-old snapshot and successful authentication. Its first
  task-owned 23:15 KST receipt is `stable`: one GET, no retry or foreground
  wait, and an independently validated two-read row-hash match. `stable` can
  mean only matching prior-session row hashes; it always retains
  `provider_finality: not_observed` and remains Engine-unreadable. Do not build
  a consumer bridge from it alone. Evidence:
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
- The same 512-session Norgate snapshot now has one explicit, double-read
  current-build conformance receipt with 1,536 reference and active bars and
  zero divergences. A hash-bound dividend-marker hygiene sidecar independently
  verifies 24 nonzero markers, 72 exclusions, and 55 distinct masked date
  groups. These results prove neither vendor correctness, publication timing,
  PIT eligibility, adjustment/corporate-action semantics, nor consumer
  eligibility. The proposed range diagnostic is now `input_unavailable` on an
  exact sample-budget kill test: its 20-observation window yields 277 eligible
  date-group rows with a longest contiguous run of 37, below its declared
  382-group split budget. Claude independently returned `unsupported` on that
  arithmetic constraint; the matching external sidecar retains its own
  source-safe evidence. Evidence:
  `D:\thericher-v2\model-artifacts\data\norgate-active-build-revision-v1\revision-current-512-20260804-r1\receipt.json`.
- A current local-client tail probe resolves the `US Equities` update timestamp
  to exactly one active data root,
  `D:\market_data\us_equities\norgate_us_platinum_trial`. Its predeclared
  2026-06-23 through 2026-08-04 D1 window has 29 common SPY/QQQ/IWM sessions,
  below its separate 126-session minimum, so its status is
  `input_unavailable`. It validates client/root binding only: it neither
  rebuilds the frozen snapshot nor changes model, GPU, PnL, or Paper
  eligibility. Evidence:
  `D:\thericher-v2\model-artifacts\data\norgate-trial-tail-readiness-v1\tail-active-build-20260804-r2`.
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
- The existing Chronos-T5 Tiny R4 CPU/CUDA zero-shot diagnostic was reattached
  after its verifier was repaired for legacy manifest record ordering.
  Its static Norgate development-panel input, hidden pretraining scope, and
  contract keep it source-local, non-PIT, non-promoting, and ineligible for
  Paper, model selection, or further GPU allocation. Its CUDA diagnostic did
  not surpass the fixed zero-return directional baseline. Evidence:
  `D:\thericher-v2\model-artifacts\research\chronos-t5-tiny-norgate-d1-probe-v1\chronos-t5-norgate-d1-actual-r4`.
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
  Tiingo rotation/sequence controls, and static broad-D1 benchmarks. The Tiingo
  raw-D1 source now also has a 330-marker/990-row external hygiene sidecar;
  this does not change its non-PIT, non-Paper scope. A later research package
  must state a distinct hypothesis, causal source, temporal split, cost model,
  baseline, kill test, and data lineage.
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
  exact unknown only on a same-intent replay. A distinct run does not scan or
  mutate historical state files; it relies on its own current open-order check.
  It never reads a live route.
- The at-most-one-intent claim is scoped to the existing single host-owned
  state root and its one scheduled Docker runner. No copied/restored state root,
  second machine, or out-of-band runner is installed; those would be outside
  this task's contract, not a general Paper hold.
- The offline validator accepts completion only for `paper_only`, terminally
  cancelled, cleanly reconciled, freshness-valid evidence. The credential-free
  loopback dashboard cannot call a broker or submit an order; authenticated
  local emergency and pause controls may change only their local control state.
  Its account projection omits prices and order identifiers.
- The local dashboard now replays FIFO realized-after-fee PnL only from closed
  `source: local_paper` lots. It leaves open lots unvalued and excludes every
  KIS account/broker fact, so it is descriptive simulator accounting rather
  than a fill-quality, profitability, model, or execution-risk input. The
  related Claude request returned unrelated stale task text, so classify that
  review as `review_unavailable`, not as agreement or a decision boundary.
- The latest safe private-state inventory has no `submitted` or
  `cancel_started` canary phase. Historical unknowns remain scoped to their own
  reconciliation paths; only an exact matching pending canary defers the next
  matching quote session.
- The host lifecycle projector and independent offline lifecycle validator now
  require a direct non-link receipt path and matching requested/recorded
  `run_id` before emitting a sanitized fact; missing or unsafe evidence remains
  `unavailable`/exit-2. Their 82 focused tests use no broker or credentials.
  The short Claude design check produced no verdict (`review_unavailable`), so
  this source/test repair does not alter the scheduled task or execution
  authority.
- `quote-session`, `daily-spy-head`, and `daily-spy-session` are explicitly
  Monday--Friday KST. This restores Monday US-session coverage without changing
  services, order logic, sizing, or KIS routes.

## Current Ready / Owned / Due

| Work | Owner | Status |
| --- | --- | --- |
| Virtual-Paper lifecycle canary | Execution | Exact 08-04 scheduled receipt is `recovery_required/prior_submission_unresolved` for preserved legacy run; independent validator remains `outcome_unknown/unresolved`, not a new lifecycle. Daily SPY is separately `no_intent/quote_unavailable`; 170 offline route/receipt/dashboard tests pass. Next canary opportunity is 2026-08-05 23:35 KST |
| SPY D1 stability observation | Data | First 23:15 KST receipt `stable`; next owned observation 2026-08-05 23:15 KST |
| Current-head timing repair | Data | Same `IgnoreNew` task remains at 00:29/02:28/04:24/06:20 KST after source-safe page-range evidence; rebuilt receipt now emits exact-run and observed-ET cumulative coverage, and terminal 06:20 capture owns the 390-completed-offset kill test |
| SPY paginated-prefix capability | Data | First exact receipt is `measurement_incomplete_or_invalid`: clean control, one accepted page, invalid seam, no next cursor; legacy terminal signal is `not_recorded_legacy`, and the rebuilt existing worker owns the next attempt |
| GPU research | Research Steward | Idle because no eligible frozen campaign exists |

An external wait belongs to its worker. Do not foreground-sleep, add a duplicate
schedule, or turn a source result into an approval hold while another lane is
ready.

## Current Recovery And Review Facts

- The repo worktree still has no current runtime projection. The exact external
  2026-08-04 scheduled-session receipt and independent offline validator agree
  only on the preserved legacy `outcome_unknown/unresolved` recovery state;
  this is not evidence of a new canary lifecycle.
- The 2026-08-04 recovery review returned `supported-with-limits`: keep the
  preflight exact-scope, prohibit a fresh submit from recovery, preserve a
  remaining ambiguity as a session-scoped result, and retain the shared lock.
  It is a challenge result, not authority or a broker outcome.
- A later Claude CLI call returned `unsupported` from a mismatched workspace:
  it cited absent `docs/` and `attestations/` paths and a stale Git history,
  while the current tree contains the canary module, projector, and allowlist
  tests. Classify that response as `review_invalid_workspace`, not as a
  substantive adverse verdict or a canary hold. No execution boundary changed.
- A current canary drift review first returned `uncertain`, then
  `supported-with-limits` after source-free code/test reattestation of direct
  virtual-host transport, pre-submit durable state, prior-run recovery, and
  broker-timestamp quote age. Its remaining limit is the one host-owned state
  root and one scheduled runner; this is a scope fact for the existing task,
  not an execution hold.
- Today's source-free Claude challenge is `uncertain` because it inspected no
  implementation or state. Independent static Review found the registered
  task/Compose surface shares the guarded root and exact virtual host/route
  client, while the generic direct CLI's configurable state root remains a
  manual-entrypoint limit outside the installed-task scope. It changes no
  route, task, authority, or current worker ownership.
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
- An official KIS GitHub recheck confirms the existing typed minute route's
  continuation shape: `tr_cont` `M`/`F` leads to `NEXT=1`, `PINC=1`, request
  `tr_cont=N`, and an oldest-bar-derived `KEYB`. The current four-page SPY
  prefix worker already performs that bounded capability probe, so no manual
  rerun or collector rewrite is pending. The former 04:31 KST token-start
  collision did not by itself justify a post-guard retime. The subsequent
  metadata-only QQQ page-range measurement supplied the required
near-boundary evidence, so the same task was re-registered at 04:24 KST
alongside the earlier 00:29/02:28 windows. Claude returned
`supported-with-limits`; the terminal task-owned session capture must prove
the 390 completed-offset result through its observed-ET cumulative
metadata-only projection. DST/pre-market behavior remains unproven.

## Verification And Git

- The observed-ET cumulative session-coverage receipt package passed 22
  focused capture/coverage/backfill/schedule tests, then `2,571 passed,
  23 skipped` through `scripts/run_parallel_tests.ps1 -RequireCleanTempRoot`,
  full Ruff, and default, intraday-head, and readonly Compose configurations.
  The rebuilt existing intraday-head image is ready for the next task-owned
  session; this verification is local and does not substitute for its KIS
  coverage outcome.

- The recovery package passed `113` focused execution/schedule/dashboard tests,
  then `2448 passed, 23 skipped` through
  `scripts/run_parallel_tests.ps1 -RequireCleanTempRoot`, plus full Ruff and
  all required Compose configurations. These are local-contract checks, not a
  substitute for the task-owned current broker result.
- The current pre-session reattestation additionally passed 137 focused
  canary/intent/quote/receipt/lifecycle/dashboard/schedule tests with no broker
  or credential access. It confirms the deterministic boundary only, not a
  current lifecycle outcome.
- The independent local-PnL package passed 32 focused local-paper/dashboard/
  attribution tests, then `2499 passed, 23 skipped` through the normal parallel
  test helper, full Ruff, and all three required Compose static configurations.
  Those checks use no KIS call or credential read and do not replace the
  scheduled lifecycle-canary evidence.
- Recent commits: `d0223ab` hardens exact Paper-canary recovery, `da12ccd`
  aligns same-date KST Paper task weekdays, and `a6a51a9` records worker
  throughput.
- `a13c195` preserves retained causal head data when a post-close capture
  conflicts, while leaving the fresh candidate non-promoting pending separate
  reconciliation evidence.
- Historic stateboard and handoff entries remain searchable in Git. Immutable
  source-safe receipts, model manifests, and runtime evidence remain external
  under `D:\thericher-v2\model-artifacts`; raw market data remains on `D:`.
- The latest known pre-current canary session evidence is
  `D:\thericher-v2\model-artifacts\execution\kis-paper-canary-session\paper-session-20260801T143501387961Z\evidence.json`.
  Granite structural runtime evidence is under
  `D:\thericher-v2\model-artifacts\research\granite-ttm-r1-isolated-runtime-smoke-v1`.

## Next Handoff

1. Preserve the exact 2026-08-04 session fact as legacy
   `outcome_unknown/unresolved`, and the separate daily SPY `no_intent` as
   `quote_unavailable`. Do not infer a broker result or submit a replacement;
   the next quote-session opportunity is 2026-08-05 23:35 KST.
2. Continue independent Data worker reattachment at its own due times.
3. Preserve the completed D1 `stable` observation as source-safe observational
   evidence only; do not treat its cache snapshot or result as provider-finality
   evidence.
4. When Data produces a fresh qualified causal input, freeze the next distinct
   Engine contract and let Research Steward allocate GPU only if it is eligible.
5. At a company-goal boundary, run required verification, commit/push, replace
   `NEXT_CODEX_GOAL.md` with one material next objective, and refresh only the
   changed current facts in these projections.
