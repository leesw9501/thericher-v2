# Engine Research Agent Stateboard (매매 엔진 연구 담당)

`AGENTS.md` owns policy and `NEXT_CODEX_GOAL.md` owns the company objective.
This is current hypothesis and campaign custody, not an experiment diary.

## Ownership And Output Boundary

Engine Research owns hypotheses, features, rule/ML/DL campaigns, backtests,
walk-forward evidence, ensemble/portfolio research, and model-side attribution.
Its output is timestamped evidence or a proposed target state, never an order.
Every campaign freezes source, target, temporal split, feature availability,
timeframe/window matrix, cost model, naive baseline, compute limit, and
strongest kill test before target evaluation or GPU consideration.

## Current Research State

- No frozen, input-qualified predictive campaign is active. Do not train or
  allocate GPU merely to raise utilization.
- A bounded metadata-only Data probe classifies the existing KIS Paper private
  D1 cache as `input_unavailable` for a 15/30 daily EMA candidate: its rows
  expose `close`, not an adjusted-close or corporate-action contract; coverage
  is partial; and no completed-bar/finality/as-of timestamp is present. It
  cannot open a daily-rule implementation, campaign, GPU appointment, PnL
  claim, or Paper path. Revisit only when one immutable manifest establishes
  explicit adjustment treatment, 30 contiguous completed sessions with known
  finality, and non-partial selected-instrument coverage.
- `same-cycle-target-allocation-v1` completed the pure model-side bridge from
  caller-provided ordered `TargetExposureProposal` values to one simulated
  shared-capacity cycle. It preserves caller order, rejects duplicate
  market/symbol identities and inconsistent portfolio snapshots, applies the
  existing scale-then-cap rule serially, and consumes capacity only for accepted
  `enter` outputs. An unexecuted `reduce` or `exit` never releases capacity.
  It creates no opportunity rank, alpha/model output, data/KIS call, state
  reservation, local-Paper intent, or broker order. Its 14 focused tests and
  the 2,707-pass, 25-skip authority suite passed; the required Claude
  architecture check timed out as `review_unavailable`, not assent.
- Hierarchical Risk Parity is an independently retrieved source-only portfolio
  allocation reference, not an alpha model. The documented MIT implementation
  clusters an arbitrary historical-return matrix and recursively combines
  branch-level minimum-variance portfolios, but the original study's instrument,
  date, and evaluation scope are `not_disclosed` to this retrieval. It needs
  causally aligned upstream candidate returns, a point-in-time universe, and
  completed rolling windows before any separate allocation contract. It has no
  campaign, code import, GPU, Paper, PnL, or promotion consequence. Evidence:
  `D:\thericher-v2\model-artifacts\research\engine-source-retrieval\pyportfolioopt-hrp-allocation-20260807-r1\source-retrieval.json`.
- QuantConnect LEAN's `DonchianChannel` source and Apache-2.0 license were
  independently re-retrieved on 2026-08-05. The new pure
  `SessionResetDonchianRule` is a fixed `20`-bar entry / `10`-bar exit,
  long/flat engineering baseline over caller-declared, contiguous completed
  session bars. Its separate pure target-state adapter requires explicit
  exposure, positive caller-declared confidence, and TTL, then emits only a
  `TargetExposureProposal` whose ready validity cannot outlast the declared
  session close; insufficient history stays a `missing` abstain.
  Neither module has I/O or a KIS/broker/data/Paper path and neither carries a
  source-performance, campaign, GPU, PnL, ensemble, or promotion claim. Its
  next valid trigger is a separately frozen causal data/split/cost/replay
  contract; the source itself discloses no evaluation sample to adopt.
- The distinct source-local `kis-intraday-session-reset-donchian-mechanics-v1`
  replay completed its immutable `2026-08-06-r1` mechanics preflight from the first 20
  complete QQQ/NAS regular M1 sessions in ascending catalog order. Each receipt
  binds a completed-bar causal input hash; the fixed 20/10 rule excludes its
  trigger bar, and any terminal position exits from the predeclared
  penultimate-bar decision at the final-bar open. The external summary retains
  aggregate local-paper/replay/terminal-flat mechanics only, never PnL or
  ranked comparison output. A no-action rule is explicitly `no_rule_activation`,
  while this run activated; it records unavailable decision-time availability,
  no promotion, Paper input, GPU eligibility, or performance metric. Evidence:
  `D:\thericher-v2\model-artifacts\research\kis-intraday-session-reset-donchian-mechanics-v1\m1-donchian-mechanics-20260806-r1\summary.json`.
- Hermetic injected-bar integration tests compose a valid Donchian breakout and
  later breakdown through the existing receipt and `source: local_paper`
  next-bar fill/replay boundary exactly once; the insufficient-history control
  emits no local intent. This is replay reliability only, not a campaign, KIS
  route, PnL result, or promotion claim.
- The separate `kis-intraday-session-reset-vwap-feature-mechanics-v1` completed
  its immutable `2026-08-07-r1` source-local feature preflight from the first
  20 chronological complete QQQ/NAS regular M1 sessions. It calculated only
  in-memory cumulative typical-price/volume VWAP feature windows at the fixed
  `5/10/30/60/90` completed-bar cuts and retained just source identity, counts,
  and an opaque feature-window hash. It creates no directional state, signal,
  order, local-paper path, performance/PnL result, GPU work, or promotion; it
  does not reopen the separately source-only VWAP directional-state candidate.
  Evidence:
  `D:\thericher-v2\model-artifacts\research\kis-intraday-session-reset-vwap-feature-mechanics-v1\m1-vwap-feature-mechanics-20260807-r1\summary.json`.
- The independent `SessionResetEmaStateRule` is a separate pure 15/30
  completed-M1 long/flat mechanism, checked against the Apache-2.0
  QuantConnect LEAN moving-average example without importing its code. Each
  EMA seeds from its own within-session SMA before Decimal recurrence, and its
  explicit `missing`/`ready` input state prevents warmup from becoming a target.
  Its distinct rule-specific target adapter maps that structural state to a
  `TargetExposureProposal` and commits rule id, period, tolerance, and seed
  policy into lineage without leaking EMA values. Hermetic in-memory tests drive
  ready entry/exit through the existing receipt and `source: local_paper`
  next-bar-open/pending-restart replay seam, while structural warmup, ready
  hold, expiry, and future-prefix controls create no intent. The shared local
  simulator rejects a late-accepted historical fill. This is integration
  conformance, not a source-local data replay, campaign, GPU, PnL, or Paper
  input. Source-safe scope and rights receipt:
  `D:\thericher-v2\model-artifacts\research\engine-source-retrieval\quantconnect-session-reset-ema-state-20260806-r1\source-retrieval.json`.
- The proposed `norgate-d1-trio-range-clustering-falsification-v1` remains
  `input_unavailable` and does not open a campaign. A current hash-bound
  dividend-marker hygiene sidecar supported an exact preflight, but the
  declared 20-observation range window left 277 eligible date-group rows and
  a longest contiguous run of 37, below the predeclared 382-group split
  budget. Claude independently returned `unsupported` on that arithmetic kill
  test. Same-session `log(high/low)` is scale-invariant under uniform split
  scaling, but that fact cannot repair the sample budget, PIT gap, or shared
  ETF exposure. It has no CPU/GPU, PnL, ensemble, or Paper consequence.
- The Docker research profile reverified generic PyTorch CUDA compute and a
  five-step deterministic training smoke on the RTX 4090 on 2026-08-04.
  Artifacts are outside Git at
  `D:\thericher-v2\model-artifacts\gpu-compute\infra-gpu-compute-smoke-20260804-r1.json`
  and
  `D:\thericher-v2\model-artifacts\gpu-training\infra-gpu-training-smoke-20260804-r1.json`.
  This confirms the runtime path only; it creates no campaign, GPU appointment,
  model result, PnL claim, or Paper input.
- A fixed source-local CUDA structure screen completed from 20 completed QQQ
  M1 sessions under
  `D:\thericher-v2\model-artifacts\kis-intraday-sequence-architecture-screen\m1-architecture-screen-20260804-r1`.
  It jointly reported precommitted LSTM, causal-TCN, and compact-attention
  architectures with a 90-bar input and local-paper replay evidence outside
  Git. The receipt has no winner, selection, or ensemble permission and does
  not materialize its sealed confirmation. It remains source-local because
  decision-time availability is not observed; it cannot create a predictive
  campaign, claim PnL, become a new Steward GPU appointment, or reach Paper.
- The terminal QQQ/NAS and SPY/AMS M1 caches have a source-safe geometry
  receipt with 21 shared complete 09:30--15:29 ET sessions. That is sufficient
  only for a source-local, non-promoting 5--90 minute structural preflight;
  `decision_time_availability` remains `not_observed`, and model/Paper
  eligibility remains false. It does not open a predictive campaign, GPU
  appointment, PnL claim, or Paper path. Evidence:
  `D:\thericher-v2\model-artifacts\data\kis-m1-cursor-session-geometry-v1\assessment.json`.
- The prospective SPY MTF baseline is a fixed causal `1m/5m/10m/1h/3h`
  decision control. Its timing evidence remains
  `decision_time_availability: not_observed` and it requires a fresh qualified
  Data receipt before any predictive, PnL, Paper, or GPU interpretation.
- The existing QQQ 90-minute `1m/5m/10m` runtime baseline is separately
  reattached to the current-head worker as an explicit observed/provisional
  Paper experiment. Its local replay now preserves the worker observation time:
  when that time follows the retained candidate execution bar, it records the
  causal `decision_after_replay_bar` no-intent instead of backdating a fill.
  It has a two-minute freshness contract and no model selection, alpha, PnL,
  ensemble, or GPU consequence. The 2026-08-07 04:24 KST task collected
  successfully and its exact QQQ session was `no_intent`; the existing v3
  validator artifact was source-safe but omitted the scheduler-consumed
  top-level `status: validated`. The v4 output contract fixes that isolated
  receipt path while preserving v3 evidence. Neither the historical receipt
  nor the next task-owned observation supports coverage, model selection,
  alpha, PnL, ensemble, or GPU inference.
- The separately scheduled SPY D1 stability observer is not an Engine input.
  Its first task-owned 23:15 KST receipt is `stable` and retains only hash and
  categorical evidence with `provider_finality: not_observed`. It cannot open
  a campaign, GPU appointment, ensemble, PnL claim, or Paper interpretation.
- The reusable causal MTF sequence contract and local-paper replay seam are
  complete engineering foundations, not evidence of alpha or selection skill.
- Fresh target-decision receipts now carry opaque commitments to their actual
  instrument/market/decision class and local target exposure. This protects
  research-to-execution attribution only; it changes no model result, campaign,
  GPU eligibility, ensemble, PnL claim, or Paper promotion.
- Granite TTM R1 passed an isolated structural CPU/CUDA runtime smoke only. Its
  source, output shape, and artifact integrity are known; forecasting quality,
  comparative evaluation, and Paper use are unknown.
- Chronos-T5 Tiny R4 completed one frozen, source-local Norgate D1 CPU/CUDA
  zero-shot diagnostic. Its external safe-file manifest now reattests despite
  legacy record ordering; the CUDA diagnostic did not surpass its fixed
  zero-return directional baseline. The static current-listing/non-PIT panel
  and undisclosed pretraining scope keep it non-promoting: no model selection,
  ensemble, Paper input, PnL, or further GPU continuation follows. Evidence:
  `D:\thericher-v2\model-artifacts\research\chronos-t5-tiny-norgate-d1-probe-v1\chronos-t5-norgate-d1-actual-r4`.
- Chronos-T5 Small is an independently retrieved `source_only_candidate` with
  an Apache-2.0 source and a documented forecast interface. Its pretraining
  period/financial-instrument scope and hidden-representation interface are not
  disclosed, so it is not a campaign, execution, GPU appointment, ensemble,
  Paper input, or profitability claim. Evidence:
  `D:\thericher-v2\model-artifacts\research\engine-source-retrieval\chronos-t5-small-20260804-r1\source-retrieval.json`.
- TimesFM 2.5 200M PyTorch is independently source-verified as an Apache-2.0,
  Safetensors-marked `source_only_candidate`. Its documented PyTorch loader
  does not require a trust-remote-code-style interface, while its official
  fine-tuning example names a related Transformers checkpoint rather than this
  PyTorch checkpoint. The source partially discloses non-financial pretraining
  sources and selected cutoffs, but financial-instrument scope and complete
  corpus period remain `not_disclosed`; it therefore has no downloaded weight,
  campaign, evaluation, GPU appointment, ensemble, Paper input, or
  profitability consequence. Evidence:
  `D:\thericher-v2\model-artifacts\research\engine-source-retrieval\timesfm-2.5-200m-official-r1\source-retrieval.json`.
- Chronos-2 is a separate Apache-2.0, Safetensors-marked
  `source_only_candidate` with a documented dataframe forecast interface. Its
  pretraining period and financial-instrument scope are not disclosed, so it
  cannot be comparatively evaluated, executed, trained, allocated GPU,
  ensembled, or routed to Paper. Moirai-2.0-R-small was screened out because
  its official weight card is `CC-BY-NC-4.0` and research-only. Neither model's
  weights or dependencies were downloaded. Evidence:
  `D:\thericher-v2\model-artifacts\research\engine-source-retrieval\chronos-2-20260804-r1\source-retrieval.json`.
- Moreira and Muir's volatility-managed exposure is an independently retrieved
  allocation-layer candidate, not a directional model. Its native monthly
  realized-variance scaling needs a future frozen causal D1 baseline and later
  qualified evaluation input, so it is `source_only_input_unavailable` with no
  campaign, GPU, PnL, ensemble, or Paper consequence. Evidence:
  `D:\thericher-v2\model-artifacts\research\engine-source-retrieval\volatility-managed-exposure-20260804-r1\source-retrieval.json`.
- The independently retrieved extreme intraday shock-reversal mechanism is a
  distinct event-triggered mean-reversion family, not a fixed-clock momentum
  or continuation rule. Its TAQ-native liquidity/spread inputs, 60-session
  per-symbol seasonal M1 baseline, completed-bar availability evidence, and
  candidate-specific replay parity are absent, so it is
  `source_only_input_unavailable` with no campaign, GPU, PnL, ensemble, or
  Paper consequence. Evidence:
  `D:\thericher-v2\model-artifacts\research\engine-source-retrieval\kis-intraday-extreme-shock-reversal-20260804-r1\source-retrieval.json`.
- The independently retrieved 52-week-high mechanism is distinct from the
  closed short-return rank, but its original 252-session/monthly/six-month
  contract needs a qualified point-in-time daily universe and more later data.
  Norgate now confirms offline-only D1 capability, not the required PIT input,
  so the candidate remains source-only; no campaign, adapter, GPU job, or Paper
  path exists. Evidence:
  `D:\thericher-v2\model-artifacts\research\strategy-discovery\fifty-two-week-high-source-pass-20260804-r1\source-handoff.json`.
- The independently retrieved same-clock-slot intraday continuation source uses
  NYSE/TAQ 30-minute intervals. It is distinct from closed single-ETF and
  same-day momentum work, but needs a prospective multi-symbol M1/PIT input;
  any 5m/10m/1h adaptation is a separate untested hypothesis. It remains
  source-only with no campaign, GPU job, or Paper path. Evidence:
  `D:\thericher-v2\model-artifacts\research\strategy-discovery\intraday-clock-slot-continuation-source-pass-20260804-r1\source-handoff.json`.
- The session-reset VWAP directional-state source is independently retrieved
  as `source_only_input_unavailable`. Its native rule uses completed regular
  session M1 HLC typical price and volume, changes state only after a completed
  VWAP-side cross, and flattens at the close; it does not define the handoff's
  fixed 30-minute horizon, which is not adopted. The author-hosted paper is
  all-rights-reserved, so this project retains only a concise factual mechanism
  summary and no source implementation. The current 21-session cache lacks
  observed decision-time availability and candidate-specific causal
  latency/fill/cost parity. It therefore cannot become a campaign, code change,
  GPU appointment, PnL claim, or Paper path. Evidence:
  `D:\thericher-v2\model-artifacts\research\engine-source-retrieval\qqq-session-vwap-state-continuation-20260804-r1\source-retrieval.json`.
- The independently retrieved SPY noise-area candidate is a distinct
  same-clock 14-prior-session volatility-band entry with a band-plus-session-
  VWAP trailing exit, rather than the closed fixed-clock momentum or the
  VWAP-side-state rule. The current 21-session cache ends at 15:29 ET, so it
  cannot reproduce the source-native prior 16:00 close gap adjustment or
  regular-close flattening; causal decision-time availability and
  candidate-specific Execution parity are also absent. It remains
  `source_only_input_unavailable`, with no code, campaign, GPU, PnL, ensemble,
  or Paper consequence. Evidence:
  `D:\thericher-v2\model-artifacts\research\engine-source-retrieval\spy-noise-area-vwap-trailing-20260804-r1\source-retrieval.json`.

- The independently retrieved five-minute opening-range-breakout source is a
  distinct `source_only_input_unavailable` technical-rule candidate. Its
  source-native screened form requires a contemporaneous multi-symbol universe,
  prior 14-session volume and ATR facts, and same-day relative opening-range
  volume; the current QQQ/SPY 21-session cache cannot reproduce those screens
  and lacks observed decision-time availability. A bounded Yahoo M1 manifest
  probe is also insufficient at eight requested days, one successful symbol,
  and no explicit calendar or availability field. It is therefore not a
  campaign, code change, GPU appointment, PnL claim, or Paper path. Evidence:
  `D:\thericher-v2\model-artifacts\research\engine-source-retrieval\us-equity-five-minute-orb-20260804-r1\source-retrieval.json`.
- The independently retrieved turn-of-month source is a deterministic calendar
  state overlay, distinct from the current momentum, VWAP, ORB, shock, and
  sequence families. Its single-instrument SPY long-versus-flat mapping is not
  source-native; moreover, the current KIS input lacks causal month-boundary
  close availability, versioned calendar provenance, and next-execution
  semantics. It remains `source_only_input_unavailable`, with no code,
  campaign, GPU appointment, backtest, PnL, ensemble, or Paper path. Evidence:
  `D:\thericher-v2\model-artifacts\research\engine-source-retrieval\turn-of-month-spy-window-20260804-r1\source-retrieval.json`.
- The independently retrieved pre-holiday return source is a sparse
  calendar-event family distinct from the month-boundary overlay and current
  price/volume/sequence families. The publisher's direct abstract endpoint was
  unavailable to this worker, and the retrieved source facts do not define an
  executable single-ETF rule. The current KIS input also lacks prospectively
  bound holiday-calendar, completed-bar, and decision-to-execution evidence.
  It remains `source_only_input_unavailable`, with no code, campaign, GPU
  appointment, backtest, PnL, ensemble, or Paper path. Evidence:
  `D:\thericher-v2\model-artifacts\research\engine-source-retrieval\pre-holiday-session-window-20260804-r1\source-retrieval.json`.

- A temporary Strategy Discovery pass surfaced the monthly U.S. `Mom` factor.
  Engine independently retrieved its official construction page, but the
  primary-paper DOI was unavailable and the construction page does not disclose
  reuse rights. More importantly, it is an aggregate factor return rather than
  an executable constituent universe with local cost, borrow, and causal-input
  assumptions. It is rejected before any code, data download, campaign, GPU,
  ensemble, PnL, or Paper path. Evidence:
  `D:\thericher-v2\model-artifacts\research\strategy-discovery\monthly-us-momentum-factor-source-pass-20260805-r1\source-handoff.json`.

## Closed Or Non-Reusable Families

- QQQ intraday consensus, first-30/final-30 momentum, and fixed MTF logistic
  lines are closed or input-unavailable. Do not retune their windows,
  thresholds, costs, or signs under a new label.
- The lower-tail QQQ quantile proposal is unsupported on its overlapping stale
  historical cache. It needs later, time-disjoint observations and a new
  contract before reopening.
- Tiingo/Norgate static D1 controls and KIS broad-D1 momentum/representation
  studies are source-local, non-promoting evidence. In particular, the Tiingo
  raw-close CPU control and fixed `5/20` sequence breadth already exercised
  CPU plus CUDA GRU, causal TCN, and compact attention; the completed sequence
  cells were negative at the fixed 10-bp view. Do not create a duplicate Tiingo
  CPU/DL baseline. These controls cannot become Paper inputs, a winner, a depth
  job, or an ensemble by relabeling.
- The MIM literature mechanism is historically interesting but its local
  derivative failed its frozen CPU kill test on the available small source.
  Do not re-run it without a distinct later family and data contract.
- The independently retrieved weekly loser-reversal source did not open a
  campaign: its proposed bottom-rank implementation was a sign inversion of
  the closed broad-D1 momentum line. The source-local panel could support a
  separate five-return-interval/five-forward-session adapter, but no adapter
  or diagnostic starts without a source-specific mechanism that is distinct
  from both closed momentum and volume-exhaustion families. Evidence:
  `D:\thericher-v2\model-artifacts\research\kis-broad-d1-weekly-loser-reversal-assessment-v1\assessment.json`.

## Current Inputs And Research Tracks

| Track | Current status | Next valid trigger |
| --- | --- | --- |
| Technical/chart and momentum/regime | No current frozen campaign | New causal, time-disjoint input and contract |
| Classical ML/statistical | No current frozen campaign | Qualified dataset plus CPU-first preflight |
| Sequence/DL/public model | Granite runtime receipt, closed Chronos-T5 Tiny diagnostic, and source-only candidates | Frozen data/target/split and Steward appointment |
| Portfolio/allocation/meta-decision | Deterministic target-scale/cap foundation only | Aligned out-of-fold upstream evidence |

Public source proposals remain `source_unverified` until Engine independently
retrieves the source and records scope, rights, and data compatibility. A source
handoff alone never authorizes code, weights, data download, training, ensemble,
or Paper use.

## Data And Evaluation Limits

- Use only completed bars available at the named decision time. No source blend
  or hidden provider fallback is allowed.
- Model comparisons use chronological purged/embargoed splits. A screened
  survivor needs a later or disjoint replication before sealed evaluation,
  ensemble use, or Paper consideration.
- Static current-listing D1 panels and short head caches may support only their
  explicitly source-local, non-promoting contracts. They do not create a shared
  evaluation pool.

## Handoff

When Data delivers a new qualified consumer input, freeze one distinct campaign
and submit it to Research Steward. Record only the new contract, source-safe
receipt pointer, result category, closed-family implication, and next action.
Historic experiments and artifacts remain in Git and
`D:\thericher-v2\model-artifacts`.
