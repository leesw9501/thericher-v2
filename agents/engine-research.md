# Engine Research Agent Stateboard

AGENTS.md owns policy and NEXT_CODEX_GOAL.md owns the company objective. This
is the current Research projection, not a campaign ledger.

## Ownership

Own hypotheses, features, models, campaigns, analytical backtests,
walk-forward evaluation, research-side portfolio/allocation hypotheses, and
model-side PnL attribution. Research Steward owns exclusive-GPU and
sealed-evaluation allocation. Never modify broker submission or deterministic
execution-risk behavior.

## Current Source Opportunity Contract

The pure current-source opportunity adapter is complete for the existing local
KIS intraday graph. It accepts an already supplied candidate plus a caller-pinned
causal completed-bar-prefix contract, symbol/market, completedness, and validity
facts; it can only preserve or downgrade that candidate. The historical v1
external replay artifact remains immutable; the corrected v2 synthetic replay
is pinned at
`sha256:8855ec22147b9218fc83ac60eaf3cb17dd2a70b38bc46b7568aec5033ad383d1`
when its facts match. An ineligible candidate, stale source, source gap, or
duplicate produces only an abstention and no local-paper intent. Future bars do
not influence the source contract, receipt, or bridge. This is graph plumbing,
not an opportunity selector, model result, ensemble, PnL claim, or Paper
candidate.

The original MIM source was independently re-retrieved through public SSRN,
DOI, RePEc, and Rutgers metadata. The source-safe receipt is
`D:\thericher-v2\model-artifacts\research\mim30-source-receipt-v1\mim30-primary-source-20260802-r1.json`
(`sha256:4d91b03e4a1f688d31a7a67e0595a2493650a2d7abfefb5372774a8c2e186d91`).
Its pure contract is `mim30-spy-long-only-derivative-v1`
(`sha256:2ef4d43bc0905c02d6cc95cae9c40c395b560b4d06ac903a09dc001013d5884f`):
SPY/AMS 1m, prior regular close through 10:00 ET, positive-to-long and
nonpositive-to-flat only, no short or filter, two-sided early-close exclusion,
60/20/20 chronological split, 252-session/30-sealed-entry minimum, and fixed
10/15/20-bp (`1.0x/1.5x/2.0x`) round-trip scenarios. It is explicitly a
long-only derivative, not a source replication. Current local Paper uses
next-completed-bar open entry and terminal 15:59-open exit, not a 16:00 close or
auction fill. Consequently an explicit execution-parity attestation is required
for research interpretation, but this contract remains data/research-only and
Paper-ineligible until a later Execution implementation reattests it. The local
cache supplies only 20 structurally complete candidate sessions, 232 below the
frozen 252-session minimum. The exact KIS `SPY/AMS/1m` capability probe found a
head-only terminal continuation shape with no initial historical-date field, so
the source input is `input_unavailable` for this campaign rather than a reason
to manufacture a collector, model, GPU job, Paper input, or model weight.
Claude's MIM falsification-first verdict was `unsupported`: the exact route
cannot support the frozen historical split, and source-window timing, early
close, and corporate-action interpretation remain non-promoting. That verdict
closes only this historical MIM campaign; it does not block a separately frozen
prospective engine or another Data/Research package.

The pure `prospective-spy-intraday-baseline-v1` consumes the Data Agent's
`SPY/US` prospective session record with exact causal `1m/5m/10m/1h/3h`
lookbacks of `30/6/3/2/2`. It proposes the fixed research-only `0.02` long
target only when every view's final close exceeds its first close, and otherwise
emits abstain/no-trade. Its one-minute TTL, `10`-bp round-trip metadata, and
always-flat comparator are fixed; it has no training, tuning, ensemble,
historical claim, artifact, provider, execution, or Paper authority. Proposal
identity uses only source/contract identities, structural/timestamp facts, and
the derived categorical action, never OHLCV values.

The completed dedicated `prospective-spy-observation-receipt-v1` evaluates this
already-frozen baseline once per immutable session record and binds the result
to a SHA-256 commitment over the selected causal input bars. The receipt keeps
only source/record hashes, structural timestamps, baseline/feature identities,
and `enter` or `abstain` category/reason; it carries no raw values, PnL,
training result, selection, or Paper claim. A future fresh receipt preserves
this rule unchanged and is not a GPU or model-campaign input by itself.

The `3h=2` correction is a pre-outcome contract fix: at the 15:30 decision
boundary two completed three-hour bars exist, so the frozen unanimous trailing
return predicate remains evaluable without a hidden reinterpretation. KIS route
or venue codes are not model-side Bar identity; Execution owns that translation.

## Strategy Discovery Intake

An invoked Strategy Discovery assignment now owns one bounded public-source
landscape pass for target-free sequence representation and public time-series
model candidates. It may provide only retrievable source identifiers, retrieval
time, verbatim license text, a source-derived mechanism proposal, and the
source's stated discovery/evaluation or pretraining-corpus period and
instrument scope (or `not_disclosed`). Engine Research independently
re-retrieves any candidate before it becomes a hypothesis, causal task,
campaign, or GPU job.

This is deliberately not `agents/strategy-research.md` yet: it has no durable
queue, model, benchmark, data, broker, or Paper authority. Promotion requires
two consecutive company-goal boundaries with independently re-retrieved
handoffs that Engine Research actually consumes and one source-hygiene
rejection. A failed re-retrieval or an unconsumed handoff retires the trial.
Unknown or overlapping discovery/pretraining coverage may support only an
isolated non-promoting study. The first external source-safe handoff is
`official-time-series-foundation-source-pass-20260729-r1`, under
`D:\thericher-v2\model-artifacts\research\strategy-discovery`; it pins
Chronos, TimesFM, and Uni2TS/Moirai code sources and their verbatim repository
licenses. It deliberately records pretraining period/instrument scope as
`not_disclosed_in_pinned_readme`, checks neither checkpoint rights nor weights,
and adds no dependency or runtime. This is one unconsumed handoff, not a
campaign input or a reason to create a durable discovery lane.

A separate 2026-07-30 official-source hygiene retrieval rejected runtime
adoption of the currently listed Chronos, TimesFM, and Uni2TS/Moirai public
model projects. Their official repositories state Apache-2.0 code licenses,
but do not establish checkpoint rights plus a financial-instrument and
pretraining-period scope sufficient to rule out evaluation overlap. It
downloaded no weights, data, or dependency and is a rejection, not a second
handoff, model candidate, runtime decision, or GPU job.

The additional source-safe handoff
`ohlcv-mechanism-source-pass-20260730-r1` is external at
`D:\thericher-v2\model-artifacts\research\strategy-discovery` with hash
`sha256:08802d6838cb51c87842975b25edfe296e34d53acd710568f99a1f7d4431f7ef`.
It records one each of chart-structure, time-series-momentum, and
cross-sectional-tree references, all explicitly `source_unverified`. None has
an independently re-retrieved rights, source-semantics, adjustment, or
point-in-time compatibility claim, so this is an unconsumed discovery handoff,
not a hypothesis, campaign, GPU job, ensemble input, or Paper input.

The separate source-only multi-track pass
`multi-track-source-pass-20260731-r1` is external under the same root with
hash `sha256:9fd0f4398d5e56b3eebd740d6eb3a56146c0eca85075aca166c003ec65ca2343`.
It records two technical/chart, two momentum/regime, and one official Qlib
classical-ML reference. All five remain `source_unverified` and unconsumed:
they neither qualify the current source data nor authorize code, data,
dependency, runtime, GPU, ensemble, KIS, or Paper work. A later Engine
Research package must independently re-retrieve one source and freeze its own
causal data, timing, split, costs, and falsifier before it may use it.

## Research Track Portfolio

Engine Research owns five parallel tracks under one campaign and trial-custody
contract; these are work packages, not independent agents or Markdown queues.

- **Technical Rule And Chart Structure:** completed-bar price, candle, volume,
  breakout, reversion, and deterministic exit hypotheses. Rejected rules are
  not retuned under a new name.
- **Momentum, Regime, And Cross-Section:** relative strength, trend, volatility,
  correlation, and opportunity-selection hypotheses. A point-in-time universe
  and corporate-action limitation remain explicit; static Norgate work is
  development-only until KIS reconstruction is qualified.
- **Classical Statistical And ML:** naive, linear, tree, and calibrated
  tabular controls. CPU breadth precedes scarce depth work.
- **Sequence, DL, And Public Models:** LSTM/GRU/TCN/attention-family
  representation or forecast candidates, plus isolated public-model benchmarks
  after source, weight, and training-corpus provenance review. Research Steward
  allocates the exclusive GPU to the first ready frozen job, not an arbitrary
  queue item.
- **Portfolio, Allocation, And Meta-Decision:** cross-candidate combination,
  target-weight, capacity, and sizing hypotheses. Each candidate exposes its
  correlation, turnover, availability, and capacity assumptions for independent
  Execution rejection; it never changes deterministic risk directly.

**Cross-Track Synthesis** remains dormant until at least two independently
frozen candidates expose aligned out-of-fold evidence with comparable costs and
availability. Temporary Validation then tests incremental net value, error
dependence, turnover, drawdown, and stale-data behavior. It can return only
`no_combination` or one new frozen ensemble-campaign proposal; it does not
choose weights, tune members, open a sealed holdout, promote a result, or create
a Paper action. A proposal is recorded as a new candidate family before any
future sealed evaluation allocation.

Campaign custody is now implemented as the append-only
`research_campaign_custody` namespace in the external control ledger. It keys
frozen contracts, trial-family indexes, and non-promoting outcomes by checksum,
rejects Git-local artifact roots, and has focused contract coverage. Historical
breadth remains non-promoting: the registry makes trial custody auditable; it
does not make an old result comparable, selectable, or promotable. Research
Steward owns its cross-track allocation and sealed-evaluation usage; Engine
Research owns the candidate contracts and implementations.

## Window And Timeframe Experiment Protocol

Timeframe and observation window are first-class campaign parameters, not a
late threshold tweak. The first intraday seed matrix is a bounded menu, not a
requirement to train every combination: 1m `{15, 30, 60, 90, 120, 180}` bars,
5m `{3, 6, 12, 18, 36}` bars, and 10m `{3, 6, 12, 18}` bars. A 1h or 3h regime
view must be an explicitly named matrix cell under the same contract or a new
campaign family. Each campaign freezes its exact subset before reading an
outcome.

- Every cell uses the same causal availability rule, split, target, fill/cost
  model, naive comparator, and family-level stop budget. The budget is shared
  across the matrix rather than multiplied by its cells.
- The contract declares a minimum complete-causal-observation and block-aware
  effective-sample rule per cell. Overlapping windows are not counted as
  independent observations. A cell that misses the predeclared rule is
  `input_unavailable`, not silently dropped after results appear.
- Screen evidence reports the number of cells considered, turnover, after-cost
  result, and the fixed `1.0x/1.5x/2.0x` cost band. A development or out-of-fold
  survivor is not a winner: it receives a new family lineage and a later or
  disjoint replication/depth contract before any sealed evaluation, ensemble,
  or Paper consideration.
- Target-free or data-scarce window studies may improve representations and
  runtime plumbing, but are ledgered as non-promoting and cannot become a
  profitability claim by relabeling the same artifacts.

## Current Target-Free Representation Evidence

The first separate Norgate target-free representation campaign completed under
external r6 contract `sha256:ef3745da...a4aacc2`. Its CPU GRU smoke and one
Docker CUDA batch completed fixed GRU, LSTM, temporal-convolution, and compact
attention reconstruction jobs. The aggregate batch evidence is
`sha256:1f91c4d3...2a4481`; all weights are external numeric non-pickle `.npz`
files, and the registry outcome is `sha256:e011f1d6...0b65bd`. The r5 attention
failure remains immutable preflight evidence; r6 corrected only bounded
diagnostic batching and did not select a model, retain a numeric score, create a
forecast, ranking, PnL claim, ensemble, KIS input, or Paper action.

Claude's later review was `supported-with-limits`: a static Norgate-only result
cannot prove KIS reconstruction, the full-panel target-free weights cannot be
reused by a downstream held-out label task, adjustment semantics are not yet
qualified, and survivorship is a declared limitation rather than a killable
test. The completed offline dual-source conformance receipt is
`sha256:17a5c604...bf26afa`: it found only a shared five-field D1 shape and
completed-bar declaration; adjustment and symbol identity conflict, while
corporate action, timezone, and gap semantics remain unknown. The interface is
source-parameterized only and remains ineligible for transfer, model work,
ranking, PnL, or Paper use. The next Research-adjacent input check is an
offline KIS `MODP=0` split-signature falsification, not a causal
label/model/GPU campaign. That audit now has narrow `consistent` evidence for
five fixed split pairs, but Claude rejected turning it into a label adapter:
the result neither qualifies remaining corporate actions nor changes the
non-model status. The next source-local check is an all-six-symbol unexplained
large-discontinuity census, still with no label/model/GPU/Paper consequence.

That v2 census is now complete with one aggregate AAPL category and zero for
the other five streams. The symbol-aware fixed-pair exclusion is correct, but
the category has no asserted cause and does not justify another historical
adapter or any Research action. Historical D1 remains quarantined while
Execution independently proves its existing KIS Paper lifecycle.

## Current Objective

Keep the completed KIS-native QQQ/SPY controls and six-symbol daily control as
development-only falsification evidence. All three independent E1/E2/E3
candidate-only screens and their fixed cross-fold falsification consumer are
complete. Its result rejects the fixed pair but does not select a replacement.
The fixed NAS daily-history recovery is complete and its reattested
source-local panel now supplies six immutable D1 streams with a 2,179-session
common subset. The new campaign contract is also frozen at
`sha256:5a9ceb...9aaea5`: it has exact `1,510 / 22 / 647` phase geometry,
20-return per-symbol windows, development-only labels, and target-free
validation inputs. This remains current-listing coverage evidence rather than a
PIT universe or ranking input. Its six per-symbol CPU L2-logistic smokes and
18 Docker CUDA LSTM/causal-TCN/compact-attention cells are now complete under
  fixed source-safe Docker r2 receipts `sha256:e60cf92...ffc4fa` and
  `sha256:2c213d0...b99dae`. The latter retains 18 external `state_dict`
  checkpoints only. This is target-free model-plumbing evidence, not validation
  evaluation, selection, ensemble, replay, PnL, or Paper input.
The executable breadth runner now rechecks the exact frozen campaign identity,
and CUDA accepts only a complete sibling-attested CPU receipt before writing
any output. The host reattestation `cpu-smoke-20260728-r2` remains immutable;
the r1 Docker mismatch was resolved by unchanged same-runtime Docker r2 breadth
artifacts rather than hash relaxation or cross-runtime bridging. The Docker r4
sealed evaluator completed all six CPU and 18 CUDA candidates plus the 18 fixed
comparators. Its source-safe precommit and summary are
`sha256:999750...f71746` and `sha256:032342...35fedf`; all fills are in-memory
and replayable `local_paper`, all accounts are terminal flat, and no target,
prediction, event row, source value, ranking, selection, ensemble, promotion,
KIS, or Paper order was retained or enabled. The summary names only a
marker-detected `execution_environment: docker` class; versioned Compose
configuration and focused tests separately attest the network/mount contract.
The prospective QQQ first-five pair is required only for its isolated
prospective observation, pair-dependent campaign, and later pair-dependent
promotion decisions; it does not make historical research input-pending.
The new prospective QQQ runtime baseline is deliberately separate from that
first-five pair: it freezes one 90/18/9 completed-bar, five-action target-state
decision and records provisional cache-bound evidence. It is an execution
learning control, not a trained model, GPU campaign, ranking, or profitability
claim.
The fixed nonlinear daily tree breadth package is complete and falsified. A
future breadth package must introduce a new hypothesis and falsification rule,
not retune the rejected linear, sequence, or tree candidates. GPU work starts
only after an eligible campaign's dataset, target, split, costs, and naive
baseline are frozen. The 21-session intraday cache remains a pipeline control,
not a depth-training corpus or a reason to manufacture GPU work.

The completed data-backed 1m sequence screen used one fixed 90-bar horizon; it
was an architecture comparison, not a `{15, 30, 60, 90, 120, 180}` window
sweep. Its after-cost outcomes did not produce a selectable candidate. The
separate non-promoting 1m window-sensitivity preflight is now complete on the
retained 20-session KIS cache: its aggregate real spread was below the
predeclared session-block null P95, so it closed `no_structure`. It does not
alter the installed QQQ decision table, create a Paper action, or qualify CUDA.
The fixed comparison sessions are spent for this family; a later intraday
candidate needs later or otherwise disjoint evidence.

The fixed CACC-D1 closing-auction co-confirmation screen is also complete and
falsified across all three sparse validation folds. It used no training, GPU,
network, credentials, KIS, or broker route. Do not retune its threshold, add it
to an ensemble, or turn its result into a Paper input.

The distinct NAS D1 volatility-conditioned trend package fixes causal
completed-bar `20 x 5` windows and development-only per-symbol normalization.
Its six CPU L2-logistic smokes and 18 network-disabled Docker CUDA
LSTM/causal-TCN/compact-attention candidates have CPU/CUDA r2 summaries
`sha256:65ba9f682bb6477bd7fdfa5d61761fb7ab67f3db23601187a92f88415bad69a8`
and `sha256:3158ac0e69c002394d97dc5f52946d70637e082f292a7c549498f4c045e5bc2c`.
All target-free forwards and all 18 `state_dict` checkpoints remain external.
Its completed r5 sealed local-paper precommit and summary are
`sha256:e7bd2cd8...d7b4618` and `sha256:803ead44...634d010`. The fixed package
classified 24 candidates and 36 comparator cells, with six paired kill-rule
passes. That mixed result remains evidence only: it creates no winner, ranking,
selection, ensemble, promotion, KIS, or Paper input. Every fill was in-memory
`local_paper`, replayed terminal-flat, and source values, predictions, fills,
and checkpoints stayed unretained. Claude's required post-evaluation challenge
was `review_unavailable` because local OAuth could not refresh.

The bounded prospective observer is also complete. It reattested the frozen
r2/r5 identities, derived its boundary from the 2026-07-24 frozen source
session, and found zero later common all-six-symbol D1 sessions; its immutable
result is only `input_unavailable`. Data now owns a separate forward cache.
There is no eligible new GPU campaign or prospective replay until that exact
consumer input contains a complete decision, `t+1`, and `t+2` common window.
The installed Data task now invokes this network-disabled observer after each
verified forward-cache outcome. The current cache has one common session and
the Docker observer correctly remains `input_unavailable`; PyTorch CUDA sees
one device, but no eligible model run or generated model artifact follows.

The independent candle-state r3 package is now complete as candidate-only model
plumbing. Its new per-symbol causal OHLCV contract uses 40 completed D1 bars,
five Decimal-quantized candle-state features, the same frozen split/costs, six
CPU L2-logistic smokes, and 18 network-disabled CUDA LSTM/causal-TCN/compact-
attention candidates. The prior r1 host/Docker mismatch and r2 review findings
remain immutable scoped evidence; r3 fixes fixed-context Decimal division,
canonical normalizers, and the CPU summary attestation rather than relaxing a
check. The r3 CPU and CUDA summaries plus the CPU sidecar attestation are
external under
`D:\thericher-v2\model-artifacts\research\kis-nas-d1-candle-state-breadth-v3`.
All validation forwards remained target-free and every checkpoint is external.
The attempted Claude drift check returned `review_unavailable` because OAuth
could not refresh, so this remains non-promoting: no selection, ensemble, PnL
claim, KIS call, or Paper action follows.

The first static Norgate broad D1 opportunity-development campaign is also
complete. It reattached the frozen 523-symbol / 483-session source through the
existing hash-attested feature artifact, but moved the validation boundary to a
22-date purge so development labels and feature windows are disjoint from
validation features. Its immutable external campaign contract, CPU baseline,
and one Docker PyTorch CUDA causal-TCN breadth job are under
`D:\thericher-v2\model-artifacts\norgate-broad-opportunity-development\norgate-broad-opportunity-development-r1`.
The contract/CPU/CUDA identities are `sha256:27e0...d8d348`,
`sha256:913e...3dbf42f5`, and `sha256:f091...541fa13`. Neither completion
requested review, selected a model, produced PnL, ranked a symbol, or opened a
KIS/Paper route. It remains field-compatible development plumbing only: static
survivorship, adjustment/corporate-action, and cross-provider reconstruction
limits remain explicit.

## Current Readiness

- The first source-local Tiingo D1 CPU control is complete at
  `D:\thericher-v2\model-artifacts\tiingo-etf-d1-cpu-baseline-v1\20260801T173121Z-cpu-baseline-r2`.
  It precommitted raw completed-D1 `5/20/60` trailing momentum, a 70/30 split,
  61-session purge, target-day open-to-close direction, a fixed `5/10/20`-bp
  round-trip cost band, and flat/momentum baselines. Every evaluated validation
  momentum cell was below flat across the band; SPY and QQQ 60-session validation cells are
  `input_unavailable` because their fixed retrospective event mask leaves fewer
  than 50 samples. This is an honest descriptive control, not a winner,
   ensemble member, PnL claim, Paper input, or GPU appointment. Recovery: a new
   daily family must freeze a distinct causal hypothesis and cannot retune this
   matrix after reading these results.
- The distinct Tiingo D1 sequence breadth family is complete at
  `D:\thericher-v2\model-artifacts\research\tiingo-d1-sequence-breadth-v1`.
  Its host CPU comparator and Docker CUDA breadth use the immutable SPY/QQQ/IWM
  snapshot, completed raw-OHLCV sequence lengths `5/20`, a 70/30 chronological
  split, 22-session dependency purge, feature-side discontinuity rule, known
  event mask through `t+1` for retrospective description, and fixed `5/10/20`
  bp costs. The CPU summary is
  `cpu\sequence-cpu-20260802T032249\summary.json`; the completed PyTorch CUDA
  12.8 GRU/causal-TCN/compact-attention batch is
  `cuda\sequence-cuda-20260802T032438-r2\summary.json`, bound to source-contract
  input `sha256:340a6acede3e8d9d8058a766c9a7b1bfc6fb98a0bab68656d2bad3ed928d7849`.
  It writes no checkpoint, raw value, prediction, or weight. All six fixed
  architecture-window aggregates are negative at the fixed 10-bp cost view, so
  it is descriptive breadth evidence only: no winner, ensemble, replay, PnL,
  Paper input, or next GPU allocation follows. Recovery: freeze a different
  causal family and source interpretation; do not retune this one after result
  inspection.
- The updated Norgate local trial cannot yet provide an independent broad
  cross-sectional holdout for a distinct campaign. Its actual 2026-06-23
  onward SPY/QQQ/IWM common tail is 28 completed sessions and its entire
  41-calendar-day interval is below the precommitted 126-session requirement.
  This is `input_unavailable` for that prospective family, not a negative model
  result, a broad-panel restatement claim, or a restriction on KIS/Tiingo or
  source-independent Engine packages. Do not manufacture a GPU job from the
  static panel or lower the threshold after observing the tail.
- Eligible source-separated KIS historical input exists: QQQ/SPY daily common
  history and a bounded complete QQQ/SPY intraday scope.
- The frozen daily CPU run completed on 4,756 QQQ KIS-private sessions with
  an 80/20 chronological split and a one-session purge. Both fixed naive
  candidates were after-cost negative in development and descriptive holdout;
  every replay fill was `local_paper`. It is not a selection or profitability
  result.
- The Docker CUDA replication compared LSTM, causal TCN, and compact attention
  on the fixed 20-session intraday scope. Its artifact wrote no checkpoint or
  raw market data and selected no winner, ensemble, or Paper action.
- The new daily screen reattested the QQQ/SPY-only 4,756-session KIS panel,
  froze 3,783 development sessions, 22 purge sessions, and 951 validation
  sessions, and used only 20 completed-bar QQQ/SPY return windows. Validation
  windows began after their own 20-session warmup, the pooled scaler fit only
  development data, and every eligible replay fill was `local_paper`.
- A deterministic one-epoch CPU smoke and one network-disabled Docker CUDA
  screen of LSTM, causal TCN, and compact attention completed on 2026-07-26.
  Each attempt wrote three checkpoints and six replay cells solely beneath the
  external artifact root. No candidate, result, ensemble, promotion, holdout,
  broker route, or Paper action was selected or created.
- The immutable `cpu-control-20260726T154600Z-r2` L2 logistic run completed
  against the exact QQQ/SPY daily hashes. Its precommit binds the fixed
  `10000` starting cash and one-share quantity before fitting and validation;
  it produced two model and six naive `local_paper` replay cells. The model was
  after-cost negative for both symbols and weaker than the previous-bar
  direction comparator, so it is a falsified control, not a candidate,
  selection, ensemble member, or Paper input. The external summary is under
  `D:\thericher-v2\model-artifacts\kis-daily-l2-logistic-control-v1`.
- The first independent daily nonlinear breadth candidate completed on
  2026-07-28 in Docker CPU mode. It used fixed 20-session QQQ/SPY completed
  return windows, 3,783 development sessions, 22 purge sessions, 951 validation
  sessions, the existing after-cost local-paper target, and a fixed shallow
  histogram-gradient tree without early stopping. It wrote no serialized model
  or raw rows. The external summary is under
  `D:\thericher-v2\model-artifacts\kis-daily-regime-tree-breadth-v1\20260728-cpu-smoke`.
  Its QQQ/SPY after-cost PnL was `-45.8296 / -73.7783`, below the corresponding
  previous-bar-direction controls `-1.7914 / -44.1851` and below flat. This
  falsifies the fixed candidate; it is not retuned, selected, ensembled,
  promoted, or routed to Paper work.
- The preceding `cpu-control-20260726T154042Z` artifact remains immutable but
  is not a qualifying campaign result: its precommit omitted replay sizing.
  It must not be compared, selected, or used to support PnL claims. The r2
  run is the sole corrected result for this fixed configuration.
- The fixed CACC-D1 CPU-only screen completed against the existing three
  hash-attested QQQ/SPY D1 folds. Its source-safe external summary is
  `D:\thericher-v2\model-artifacts\kis-daily-cacc-d1-v1\cpu-20260728t0208-cacc-d1-r2\summary.json`
  with precommit `sha256:76eb55...e960a9`. Every fold triggered the immutable
  kill rule: the first was nonpositive after costs and all three failed to beat
  their time-matched always-long comparator. The candidate is closed with no
  tuning, GPU, ensemble, promotion, or Paper consequence.
- No GPU job is active. The just-completed opportunity campaign used one fixed
  causal-TCN breadth job after its CPU integrity result; it was not
  performance-selected. The next constrained Research input is broad KIS D1
  coverage, so Research prepares its field-reconstruction comparison while Data
  generalizes collection rather than manufacturing another static-panel run.
- The 2026-07-28 throughput review found no frozen campaign eligible for GPU
  work: the existing D1 candidates are closed/falsified, and the natural QQQ
  runtime receipt is execution evidence only. The newly completed QQQ/SPY D1
  relative-regime control reattested the 4,756-session common panel, preserved
  the frozen `3,783 / 22 / 951` split, and warmed each phase independently for
  its 63-session causal input. Its CPU smoke and full 443-slot validation used
  only in-memory `local_paper` fills and source-safe external summaries. The
  candidate made 312 validation trades but was after-cost weaker than the
  time-matched always-long baseline, so the strict rule classifies it
  `falsified`. It is closed: no retune, model, ensemble, GPU dispatch,
  promotion, or Paper input follows.
- The separate QQQ/SPY D1 relative-allocation control is also complete. Its
  smoke and full receipts are under
  `D:\thericher-v2\model-artifacts\kis-daily-relative-allocation-control-v1`.
  The full 443-slot rule selected QQQ 312 times and SPY 131 times through one
  in-memory local-paper account, but its `172.3873` after-cost PnL was below
  time-matched always-QQQ `210.2283`; the fixed three-comparator outcome is
  `falsified`. It remains no model, ensemble, GPU, promotion, or Paper input.
- The prospective loop now deterministically derives its 5m/10m views from one
  same-session 90 completed-minute QQQ/NAS window and replays the original
  proposal through `local_paper`. The current prior-session smoke is `stale`
  and therefore an abstaining no-intent receipt; its separate offline validator
  independently matched that cache evidence. No parameter changed and no KIS
  route was opened.
- The pair-bound prospective observer is implemented, local-paper-only, and
  network-disabled. It remains inactive until Data supplies its immutable pair.
- The latest capture-scoped QQQ terminal page contained no qualified regular
  session minute under the exact 390-minute contract. It is Data evidence only
  and cannot become a feature, label, candidate result, or GPU input.
- Data has now exposed a hash-bound six-symbol KIS Paper daily panel with 199
  common sessions through 2026-07-24. It can supply one immutable D1
  `CatalogedBars` stream per fixed symbol to offline `local_paper` validation.
  It has no PIT universe meaning, corporate-action qualification, ranking
  claim, or Research result yet; do not train an ensemble, select a model, or
  allocate GPU work from the small current-basket panel.
- Research now has one pure unranked opportunity-selection input built only
  from the reattested source-scoped D1 manifest. It preserves the ETF daily
  catalog and current NAS panel as separate source IDs, exposes no bars,
  scores, ranks, actions, selected symbols, model, replay, or broker field,
  and explicitly remains ineligible for historical membership, liquidity,
  ranking, Paper, or cross-partition alignment. It is a future input boundary,
  not a campaign or GPU eligibility claim.
- The new source-partitioned D1 eligibility receipt has a pure Research
  consumer that preserves the ETF and NAS groups as distinct partitions and
  exposes only categorical per-instrument eligibility, reason codes, and
  limitations. All current references meet the narrow data proxy, but the
  handoff remains false for historical membership, ranking, model selection,
  Paper, executable liquidity, and cross-partition alignment. It supplies no
  score, action, feature, replay, model, GPU, provider, credential, or broker
  surface.
- The first ETF-source-local D1 trend-regime control is complete. Its fixed
  completed-D1 20/50 SMA rule used a chronological 70/30 decision-slot split,
  next-two-open one-share `local_paper` replay, and a time-matched always-long
  comparator. The external source-safe summary is
  `D:\thericher-v2\model-artifacts\etf-d1-trend-regime-v1\etf-d1-trend-regime-20260728-0400\summary.json`.
  The all-ETF falsification condition is false because SPY alone exceeded its
  comparator; QQQ and IWM did not, and IWM remains source-limited. This result
  is not a selection, model, ensemble, GPU, PnL, or Paper input. Claude's
  required result challenge was `review_unavailable` because local OAuth expired.
- The first frozen six-symbol CPU local-paper control completed with an exact
  159/1/39 chronological split, three-bar fixed momentum, one-share replay,
  fixed after-cost economics, and an `always_long` comparator. Its external
  source-safe summary records positive momentum-minus-comparator deltas for
  AAPL, AMZN, META, and MSFT and negative deltas for GOOGL and NVDA. This
   triggers independent falsification work before any model claim; it does not
   identify winners, support ranking or profitability, select an ensemble, or
   provide a Paper input. Claude's required concise challenge was attempted but
   the local OAuth session was expired.
- The daily catch-up worker is now terminal and added no QQQ/SPY rows. The
  existing QQQ/SPY history is therefore the candidate input, not a reason to
  wait for more collection. Its existing `+-1` event-boundary audit does not by
  itself protect the true `t-20..t+2` sequence dependency: visible feature rows
  are `t-19..t`, their first return reads `t-20`, and replay labels use `t+1`
  and `t+2`. A joint candidate mask must cover both symbols before any new
  sequence campaign is executable.
- The active schema-v2 joint contract is hash-bound at `sha256:d8c1...7c2a6`.
  It has 114 joint event sessions and validation eligible counts `146 / 128 /
  145`; its v2 artifact records `review_unavailable` after the required Claude
  attempt. The candidate remains `model_execution_eligible: false`. A later
  consumer must rebuild and compare the contract identity, then preserve the
  sparse eligibility list for one fold at a time rather than give all expanding
  folds to one generic `CampaignContract`.
- The first source-safe consumer is now frozen: `expanding-1` reattests the
  active parent into external artifact `sha256:a15c...90f0b` with fold-input
  identity `sha256:b019...5a1db`. It carries exact sparse development and
  validation indices `2345 / 146`, the joint-event/audit identities, and no
  prices, returns, model, replay, or broker capability. It may only be exposed
  after a rebuilt parent contract matches the active hash; a normal writer
  result cannot be selected directly.
- The D1 materializer now reattests that fold artifact before binding the same
  catalog. Its validation receipt is `sha256:247142...6b2f748`; it materialized
  one sparse `t=3825` window with predecessor `3805`, 20 feature rows
  `3806..3825`, and future references `3826/3827`. Values stay in memory and
  the receipt has no prices, returns, labels, predictions, checkpoints, or
  broker data. Temporary Validation passed independently. It remains
  `review_unavailable`, non-executable, and not a campaign/model/replay input.
- The D1 target/cost adapter derives only an in-memory QQQ long-versus-flat
  binary target from its `t+1/t+2` references. Its active v2 receipt is
  `sha256:90be...d7486` with target-cost identity `sha256:2c0e...4b842`.
  Its 1-bps fee and 2-bps slippage per fill match the existing fixed sequence
  economics, but it freezes all intermediate Decimal arithmetic at precision 34
  and `ROUND_HALF_EVEN`. Validation rejected its v1 receipt for ambient
  precision sensitivity; v2 is the only eligible source for a candidate-only
  screen. It stores no labels or price-derived value externally.
- The first `expanding-1` candidate-only D1 screen completed one Docker CPU
  smoke and one Docker CUDA run on the fixed linear and compact-GRU candidates.
  Both artifacts contain only source identities, counts, normalization hashes,
  candidate specifications, and aggregate classification metrics. The CUDA
  result's positive-biased aggregate behavior is an observation to falsify,
  not a threshold-tuning, winner, ensemble, promotion, replay, or Paper input.
  Temporary Validation independently passed scope, tail, split, and artifact
  checks. Claude OAuth remained unavailable, so no result is promotable.
- The second independent fold is complete as contract evidence only:
  `expanding-2` fold input `sha256:79723...c9305` / `sha256:650757...99f4e`
  carries exact `2511 / 128` sparse decisions and remains before the final
  151-session tail. Its materializer and target/cost receipts are
  `sha256:e489f...9709f` / `sha256:4de77...941da`; both retain only lineage,
  geometry, formula, and non-executable scope. Temporary Validation passed
  isolated sparse/tail, source-safety, mount, and pure-route checks. Claude
  OAuth retry was unavailable, so it remains candidate-only.
- The same `expanding-2` fold now completed one CPU smoke and one
  network-disabled Docker CUDA screen with unchanged linear and compact-GRU
  specifications. The source-safe aggregate result identities are
  `sha256:96a29b18...a7106e` and `sha256:233629de...2826e`. They keep the exact
  `2511 / 128` split, development-only normalizer, no persisted weights or
  per-decision outputs, and no selection/replay/PnL/Paper consequence.
  Independent Validation passed; Claude OAuth remained unavailable, so neither
  E1 nor E2 result is promotable.
- The third independent fold is now complete as input-contract evidence:
  `expanding-3` fold input `sha256:40d6...7128fc` / `sha256:1cf3...3d11e`
  carries exact `2671 / 145` sparse decisions. Its validation materializer and
  target/cost receipts are `sha256:e0b9...c147c8` / `sha256:4c38...961560`,
  with materializer/target identities `sha256:72c4...6de43d` /
  `sha256:5511...176cc3`. They retain only lineage, geometry, and formula;
  no source value, model, replay, broker, or Paper capability follows.
  Validation passed the tail and route checks, and Docker reattestation
  correctly refused immutable overwrite. Claude OAuth remains unavailable.
- The same E3 input now completed one Docker CPU smoke and one network-disabled
  CUDA screen with unchanged linear and compact-GRU specifications. Its
  source-safe aggregate result identities are `sha256:438b...c20e87` and
  `sha256:f3ad...03922a`; both keep the exact `2671 / 145` split,
  development-only normalization, no persisted weights, and no selection,
  replay, PnL, or Paper consequence. Independent Validation passed. Claude
  OAuth remains unavailable, so no result is promotable.
- The fixed six-input cross-fold verifier completed under
  `D:\thericher-v2\model-artifacts\kis-daily-joint-event-d1-crossfold-falsification-v1\crossfold-falsification-20260727-r1`.
  Its result identity is `sha256:1bbbc7...18bc5d`. It keeps E1/E2/E3 and
  CPU/CUDA separate, reads no raw market values or labels, and classifies every
  fixed candidate/mode/fold observation as `falsified` against that fold's
  class-majority count. It creates no winner, aggregate score, selection,
  replay, PnL, Paper input, checkpoint, or future-model prohibition.

## Ready Queue

1. Keep CACC-D1 closed. Its OHLC co-confirmation rule, threshold, folds, and
   costs are immutable falsification evidence, not a parameter-search seed.
2. Treat the fixed linear/compact-GRU D1 pair as falsified under its stated
   fold-local rule. Do not retune parameters, select a winner, create an
   ensemble, promote a checkpoint, or create a KIS Paper action from it.
3. Keep the completed fixed histogram-gradient tree breadth candidate closed.
   The next daily breadth proposal must change the causal hypothesis or input
   contract, not repeat its 20-bar return window with parameter changes. Freeze
   its costs, split, naive baselines, and strongest kill test before dispatch.
4. Keep the completed daily breadth, L2 control, and six-symbol control
   descriptive only. Do not retune the failed pair under a new label.
5. Keep depth input-pending and ensemble empty until independently replicated,
   error-diverse breadth candidates exist. A verified prospective pair is an
   additional observation only; it never rewrites historical results or becomes
   a global queue gate.
6. Observe the first fresh runtime window as a fixed control only. Do not tune
   the decision table from that session or turn an individual Paper outcome into
   a model, ensemble, GPU, or PnL claim.
7. Keep the completed ETF trend-regime control descriptive. Do not tune its SMA
   windows, select SPY, add an ensemble member, allocate GPU work, or turn its
   one non-falsified validation slice into a Paper input.
8. Keep the QQQ/SPY D1 relative-allocation control closed. Its phase-local
   63-session rule selected QQQ 312 times and SPY 131 times across 443 slots,
   but its after-cost result was below the time-matched always-QQQ comparator.
   Do not retune the lookback, tie rule, cadence, costs, or comparators; do not
   promote it, use it in Paper work, or dispatch GPU depth work.
9. Keep the completed sealed NAS r4 evaluator immutable. It is candidate-only
   attribution evidence, not a winner, ensemble, promotion, or KIS Paper input.
   The next breadth proposal must declare a distinct causal hypothesis, feature
   contract, costs, split, naive baseline, and strongest kill test before any
   CPU or GPU work begins.
10. Keep the completed volatility-conditioned r5 receipt and completed
    prospective observer immutable. The observer found zero all-six-symbol
    common D1 sessions after its 2026-07-24 boundary and recorded only its own
    `input_unavailable` receipt. Data's separate forward cache now has one
    common all-six-symbol D1 session, still below the exact three-session
    consumer requirement. Its automatic offline invocation does not select a
    candidate, authorize a Paper action, or create GPU work. Research remains
    ready to observe a later complete common window without tuning, ensembling,
    promoting, ranking, or creating a KIS Paper action.
11. The QQQ/SPY D1 overnight-versus-intraday directional-count CPU smoke is
    complete, but Claude's falsification-first verdict is `unsupported`. Its
    external precommit is `sha256:dc37ed...62dd5a1` and the independent Docker
    validator reattached summary `sha256:3fde8e...030a8ca`. This is only
    source/local-paper plumbing: no full run, GPU, selection, ensemble,
    promotion, KIS Paper input, or order may follow. Do not retune its
    lookback, count comparison, cadence, costs, or comparator family.
12. The KIS broad D1 cache now has a complete source-local coverage panel at
    generation 26,368: all 2,119 current NAS targets have retained coverage,
    the generation-604 overlap is equal with zero mismatches, and its external
    chronology records only per-target span buckets plus `1,089 complete / 1,030
    source_limited` states. Its current-listing/non-PIT, unadjusted,
    corporate-action-unqualified, and session-finality-unattested scope is not
    an eligible target or split. Do not freeze a CPU baseline, use historical
    membership, rank targets, open labels, start GPU work, or treat aggregate
    coverage as a model result. A later candidate still needs a date-based
    split, independently qualified target/cost definition, and explicit
    leakage kill test; this chronology record cannot provide a shared-span
    threshold, campaign eligibility, or GPU dispatch signal.
13. Keep the completed 1m window-sensitivity preflight immutable. Its
    `30/60/90/120/180` matrix closed `no_structure` after the real aggregate
    spread stayed below the frozen session-block null P95. Do not reuse its
    comparison sessions to retune a window, start CUDA, select a model, create
    an ensemble, or change Paper behavior. A later intraday candidate needs a
    fresh later/disjoint family and its own contract.
14. The pure target-position policy foundation is complete. It combines only
    caller-supplied opportunity eligibility, current exposure, and explicit
    completed-bar multi-timeframe predictions; it has no default alpha, data
    read, network, credential, broker, model-selection, or order authority.
    Invalid or conflicting evidence abstains. Its bounded proof ends at
    `TargetExposureProposal` and the existing local-paper preparation bridge,
    never a KIS route or Paper submit. The Claude drift invocation timed out,
    so the result is `review_unavailable`, not a promotion verdict.
15. The fixed 20-session multi-timeframe consensus replay is complete at
    `kis-intraday-multitimeframe-consensus-replay-v1/qqq-20260623-20260721-consensus-r1`.
    It proved the causal model-to-receipt-to-`local_paper` route and terminal
    replay, but generated only two entries. Its all-session always-long
    comparator is descriptive, not an equal-count selection null. Preserve
    the contract and artifact immutable: do not tune its experts, thresholds,
    timing, sizing, or horizon; do not promote it, allocate CUDA, create an
    ensemble, or change KIS Paper behavior. The next bounded package freezes
    an equal-count session-subset null diagnostic and then requires later or
    disjoint replication for any candidate claim. The new diagnostic completed
    with exact replay-digest parity, `190` two-session subsets, and a one-sided
    null value near `0.1684`; it is `selection_unqualified` because the fixed
    rule entered only two sessions, below the minimum `30`. Close this family:
    it cannot be retuned, promoted, ensembled, routed, or used for GPU work.
16. The pure `target-exposure-allocation-v1` model-side foundation is complete.
    It takes an already-issued long-only target and caller-owned exposure,
    capacity, confidence, and risk facts; it applies multipliers before caps,
    emits only a target-state proposal, and has no source/model/IO/GPU/broker
    authority. Stale, unqualified, or inconsistent entry capacity abstains;
    exhaustion holds; a fresh reduction or exit remains pass-through. It is not
    an allocation model, portfolio reservation, execution approval, or paper
    input. A later learned allocator needs a new frozen campaign with aligned
    out-of-fold upstream predictions and a deterministic baseline comparison.

## Durable Constraints

- All artifacts and checkpoints belong under
  D:\thericher-v2\model-artifacts or /app/model_artifacts.
- Preserve provider identity, feature timestamps, chronological splits, and
  holdout isolation.
- A result can propose target state/evidence only. Execution owns sizing,
  route selection, persistence, and broker effects.

## Recovery

Current class: complete for the joint contract, all three fold inputs/materializer/
target receipts, all three candidate-only CPU/CUDA screens, the fixed cross-fold
artifact, the fixed daily tree breadth candidate, CACC-D1, the QQQ/SPY
relative-regime and relative-allocation CPU smoke/full receipts, the sealed
Docker r4 NAS 24-candidate/18-comparator evaluation, and the sealed Docker r5
volatility-conditioned 24-candidate/36-comparator local-paper evaluation. The completed
daily-history continuation is transport and coverage evidence only: it creates
no frozen Research input, replay, campaign, or GPU job. A new campaign requires
its own contract; target-local daily-history recovery has no automatic Research
or GPU consequence. A failed consumer attempt creates new immutable evidence
rather than overwriting a parent artifact. A missing prospective pair is
input_unavailable only for its pair-bound observation. A stale prospective
runtime window is likewise only its own no-intent fact and does not create GPU
work or a promotion hold.

## Next Handoff

Preserve the fixed-pair, tree, CACC-D1, ETF trend-regime, both closed QQQ/SPY
controls, the unsupported overnight/intraday smoke, both immutable sealed NAS
result families, and the completed prospective observation receipt. The next
research candidate should not reuse the already-consumed fixed QQQ/SPY
validation slice for another variant. Data now owns a separate QQQ/SPY D1
forward cache and its 06:55 KST collector. The initial credential-free
preflight is `collection_required`; its guarded first invocation deferred while
broad data collection was running, so the pair has no future common session
yet. Research may prepare no more than its consumer contract and cannot score,
select, tune, ensemble, promote, rank, or create a KIS Paper action until that
named out-of-time input has the declared depth. The completed prospective
receipt/replay is engineering evidence only; a future fresh captured receipt
remains neither a training result nor a candidate, PnL, or Paper claim.

The completed QQQ consensus replay and its equal-count null are a closed
local-cache product-path family. They prove causal adapter/receipt/local-paper
plumbing but not selection skill. Later/disjoint data may support a fresh
replication family; meanwhile, a separate pure target-exposure allocator can
advance the engine's sizing stage without consuming this evidence.

The next meaningful Engine Research input is not another variant on the spent
QQQ sessions. Data may turn the existing local Norgate trial into a bounded
date-indexed daily source contract. The 2026-08-01 three-case receipt is now
`qualified_for_offline_research`, and the pure consumer outline freezes only
completed D1 bars, a next-regular-session candidate decision boundary,
chronological split with campaign-local purge, later Execution-attested costs,
an always-flat baseline, and an availability-time shift kill test. It still
cannot score, fit, tune, rank, ensemble, allocate GPU, claim PnL, or form a
Paper input. The fresh date-indexed pilot is complete at
`D:\market_data\us_equities\norgate_trial\daily_pilot\pilot=20260801T161934Z-norgate-trial-daily-pilot-r2`.
Its pure loader now provides 28 completed D1 `Bar`s with an exact source-date
state lookup and rejects static substitution or date misalignment. It is useful
only as offline loader plumbing: the dynamic values may be restated, provider
ticker identity is not historical security identity, and source availability,
adjustment, and corporate-action semantics remain unknown. A labelled campaign
still needs its own frozen source, target, split, costs, baseline, and falsifier;
this pilot cannot score, fit, tune, rank, ensemble, allocate GPU, claim PnL, or
form a Paper input.

The reusable `causal-multitimeframe-sequence-window-v1` input contract is now
complete for injected `1m/5m/10m/1h/3h` `Bar` sequences. It has caller-frozen
lookbacks, one UTC cutoff, exact cross-timeframe symbol/market identity, and
only structural timestamp/count metadata. It does not create a model, target,
GPU appointment, score, rank, artifact, PnL, or Paper path. The next recovery
fact is a new, separately frozen campaign or a calendar-aware upstream segment
adapter; do not fill session gaps or reuse consumed QQQ window evidence.

## Next Frozen Breadth Candidate

The next ready Engine package is
`tiingo-d1-trend-mean-reversion-rotation-v1`, a CPU-only falsification of a
distinct three-ETF portfolio-selection hypothesis. It reuses only the immutable
local Tiingo `SPY/QQQ/IWM` snapshot
`us_equities.tiingo_etf_daily.snapshot=20260801T173121Z-tiingo-etf-d1-r1`
with dataset hash
`sha256:b47539a373bf2d625ad2380376808cf412219f6c5d932b66631bb3aa553683cf`.
At a completed D1 close it may select at most one ETF with positive 60-session
trend and the largest negative five-session return normalized by prior
20-session realized volatility; no qualifying decline means flat. The frozen
next-session open-to-close target, three-way all-in round-trip cost band,
chronological 70% development / 61-session purge / 30% validation geometry,
and event/discontinuity mask are a new family contract, not a retune of the
failed momentum or sequence families. The snapshot was already used by two
Tiingo families, so this is explicitly repeat-source falsification, not a
sealed or independent holdout. The mask stops at decision time `t`; it cannot
read a target-day event marker to skip an outcome.

It is CPU-only and receives no GPU or new sealed-evaluation appointment. Its strongest
kill test is a net result at the fixed 20-bp cost that is flat-or-worse, or
consistently weaker than both fixed exposure-matched active comparators across
the cost band. A minimum 100 active validation decisions is a preflight
requirement; otherwise it closes `input_unavailable` before target evaluation.
A result is only a source-local falsification fact: it cannot claim
profitability, select a model, form an ensemble, become a KIS Paper input, or
justify an order.

## Tiingo D1 Mean-Reversion Rotation Result (2026-08-02)

The frozen `tiingo-d1-trend-mean-reversion-rotation-v1` is complete as
`input_unavailable`, not as a performance or kill conclusion. The verified
immutable Tiingo three-ETF source reattested to dataset hash
`sha256:b47539a373bf2d625ad2380376808cf412219f6c5d932b66631bb3aa553683cf`
and manifest hash `sha256:8b2e375a...c072de`. Its source-safe external run is
`20260802T081500Z-r1`, with precommit
`sha256:665532f2...b3c65137` and input
`sha256:0716b811...6b9295d3`.

The fixed causal event mask left only three active validation decisions, below
the precommitted 100-decision floor. Target-day returns were therefore not
evaluated, no aggregate performance result exists, and the family is neither
falsified nor a candidate. The run remained CPU-only, repeat-source-only, and
outside GPU, sealed-tail, KIS, Paper, broker, account, and promotion surfaces.
The requested Claude CLI drift check timed out, recorded only as
`review_unavailable`; it is not a substantive verdict or hold on independent
work.

## Latest Engine Outcome

`kis-spy-intraday-regime-micro-consensus-v1` completed as a CPU-only,
source-local falsification on the verified 21-session `SPY/AMS` 1m cache. Its
frozen `10 / 1 / 10` geometry and target-free 32-decision validation preflight
held. Once targets were opened, the candidate failed the precommitted 20-bp
net-total kill test and is `falsified`. The receipt contains aggregates only;
this is neither realized PnL nor model-selection, Paper-input, ensemble, GPU,
or promotion evidence. Do not tune the same long-only regime/micro family from
this result. Claude's two bounded review attempts remain `review_unavailable`,
not a verdict or a hold on the next distinct hypothesis.

## Latest Engine Outcome

`spy-first30-final30-momentum-v1` completed as a distinct CPU-only,
source-local falsification. Its fixed `10 / 1 / 10` structure retained all ten
validation decisions after causal prior-close/first-30m preparation, but its
signed candidate failed the 20-bp net-total kill test and is `falsified`.
Because the underlying cache is only 21 sessions while Gao et al.'s cited SPY
sample is much broader, this is a small rejection fact only. Do not retune or
promote this timing/sign family, make an ensemble member, request GPU, or form
a Paper input. Claude returned `review_unavailable`, not a verdict or hold on a
distinct next hypothesis.

## Latest Engine Outcome

`spy-intraday-mtf-logistic-10m-v1` completed as a CPU-only source-local
baseline with `input_unavailable`. All 190 scheduled causal feature rows were
available in both development and validation, but its fixed development-only
L2 logistic policy produced fewer than the precommitted 30 target-free
validation long decisions. It therefore did not read validation targets,
calculate any return/cost/kill metric, or claim falsification, PnL,
profitability, selection, ensemble eligibility, Paper input, or promotion.

The fixed threshold, model, costs, and floor remain closed to retroactive
repair. It has no GPU appointment, checkpoint, or artifact beyond its
aggregate-only external receipt; the next package must be a distinct frozen
hypothesis rather than a threshold retune.

## Norgate D1 Readiness

The new local `SPY/QQQ/IWM` D1 source is hash-attested with 511 common sessions,
but its successful materialization alone does not create a campaign. The source
is offline-only with unverified availability/PIT, adjustment, and corporate-
action semantics, and the raw snapshot remains non-ranking and non-promoting.
Do not train a model, allocate GPU, select, ensemble, or form a Paper input
from it. The next ready Engine package is one fixed source-local rule
falsification diagnostic: it names the limitations, uses a chronological split
and completed-bar timing, and ends in rejection, input-unavailable, or a
strictly non-promoting inconclusive observation. It cannot become an implicit
training, selection, or promotion path.

## Norgate D1 Trio Momentum Outcome

`norgate-d1-trio-momentum-falsification-v1` completed CPU-only as
`inconclusive_non_promoting`. The fixed 20-session strict-positive consensus
made 59 long decisions across 138 target-evaluable validation slots; its
aggregate directional hit rate was `0.559322...` compared with `0.536231...`
for always-long. This is not an alpha, PnL, profitability, model-selection,
ensemble, GPU, Paper, or promotion claim. Keep the exact split, rule,
comparator, and validation slice closed to retuning. The next Engine package
must be a distinct hypothesis or an independently specified source-stability
falsification.

`norgate-kis-d1-bar-conformance-v1` is closed as `input_unavailable`, not a
model input qualification. The present-vintage quiet D1 relationships match on
the fixed Norgate/KIS `SPY/QQQ` overlap, but the required discontinuity-adjacent
stratum has no observations. It creates no candidate, training, GPU
appointment, ensemble, sealed evaluation, KIS Paper input, or strategy change.
Do not relax the event condition after observing the empty stratum; a later
Engine campaign requires its own source and causal contract.

## KIS D1 Causal Representation Feasibility Outcome

The fixed `kis-d1-causal-representation-feasibility-v1` campaign completed a
four-step Docker CPU smoke and one 192-step Docker CUDA appointment from the
attested six-symbol D1 development phase alone. The external contract is
`sha256:1303c4f67694322dc3b9f70418c7e41203ffaab8221e5ba5080f6630e6007a7d`.
Both categorical loss-finiteness checks passed; the CUDA terminal-mini-batch
decrease flag is false. This is a runtime and causal-input fact, not a model
quality, alpha, forecast, ranking, ensemble, PnL, Paper, or promotion result.
No historical validation phase, target return, source blend, KIS request,
credential, account, broker, local-paper, or live path was used.

The first pretraining wiring attempt had no receipt or weight output and is
closed externally as `non_promoting_abandoned`; the completed `implementation-r2`
weights are safe external `.npz` artifacts only. Do not reuse them as a
representation input for a predictive, portfolio, or Paper candidate. Claude
reviewed the proposed `norgate-d1-spy-pullback-uptrend-falsification-v1` and
returned `unsupported` before target access: its unused 98-row segment would
likely yield only six to nine active rows. Preserve a 30-active-row floor and
record this as a longer-D1-coverage need, not as a rule rejection or a queue
hold on independent Engine/Paper work.

## KIS D1 Candle Noise-Floor Outcome

`kis-d1-candle-noise-floor-v1` completed CPU-only as `noise_not_separable`.
It used only 32 causal same-candle OHLC ratios from the attested six-symbol
development source, a fixed 1,000 / 33 / remaining chronology, five L2
logistic seeds, and 64 within-symbol contiguous-block label nulls. The
actual-label association did not clear the frozen null-margin and seed-spread
kill test. Its aggregate-only external summary is
`sha256:e84540377f7f1985a325d5e730334ed4c3d9a941fcb30a12737e0de3ab70b48e`.

Do not retune the candle features, split, C, threshold, seed set, null block
size, or kill margin, and do not dispatch LSTM/TCN/Transformer arms against
this exact source/split. This is not a broad ban on model research: a distinct
source-local hypothesis, fresh source coverage, or independent Paper-engine
work can proceed without consuming this closed family. No weights, GPU,
sealed evaluation, KIS/network, account, order, local-paper, PnL, or live path
was involved.

## Current Engine Preparation (2026-08-02)

No GPU-eligible predictive campaign exists now. The prior KIS causal-TCN
runtime study, candle noise-floor, Norgate trio momentum, and limited intraday
families are closed and cannot be retuned into a new selection pass. The active
Platinum build needs Data-owned revision evidence before any source-local model
contract is frozen.

Strategy Discovery identified a from-scratch, causally engineered LightGBM D1
baseline as the first comparative implementation candidate after a qualified
source contract; it must retain `always_flat`, exposure-matched `always_long`,
and a one-session availability-shift falsifier. PatchTST is comparable only
when initialized and trained within the project's causal development scope;
public pretrained Chronos weights remain isolated runtime/representation work
because their pretraining coverage is not fully disclosed. The immediate Engine
package is the independent target-free-plan integrity repair, not a premature
window/template or GPU dispatch.

## Norgate Revision Reattested; CPU Baseline Next (2026-08-02)

Data completed the fixed-trio active-build probe as `matching` with two stable
active reads per symbol, 1,533 equal bars, and source-safe receipt
`sha256:aa3989e4246a21db6d45f5e85605f896ac0550ee5f6e8f535ee47b328a510bc7`.
The target-free trio receipt boundary is also hardened against overridden or
mutated result projections. Neither fact is a predictive result.

Claude's falsification review is `uncertain`: build reproducibility is now
known, but cross-session raw-price targets remain adjustment-sensitive and 140
date groups cannot resolve a small edge. The next ready Engine package is one
frozen, from-scratch causal D1 gradient-boosted-tree CPU discrimination
preflight. It must use only per-session ratio features and a next-session
within-session ratio label, so a uniform session price multiplier cannot alter
either. It must predeclare decision/label availability, chronological split,
fixed hyperparameters, `always_flat` and exposure-matched `always_long`
descriptions, a one-session availability shift, a date-block permutation null,
and a minimum detectable-effect floor. It must not allocate GPU, open a sealed
holdout, load public weights, create PnL/profitability, rank, ensemble, or
Paper input.

## Fixed-Trio GBT Preflight Outcome (2026-08-02)

`norgate-d1-trio-intraday-structure-gbt-preflight-v1` completed CPU-only as
`noise_not_separable` (`effect_and_null_threshold_not_met`). The exact frozen
same-session 1/5/10/20 candle-structure features and next-session intraday
label did not clear the 0.08 balanced-accuracy advantage or 64-shift date-block
null threshold across 139 validation dates. Its one-session shift control was
below chance, so the result is a normal no-signal outcome rather than an
alignment incident.

Do not retune this feature/label/model/split/null family. No weights, GPU,
sealed evaluation, PnL, Paper input, KIS, credential, broker, or live path was
used. The next candidate needs broader independently reattested source coverage
or a distinct causal hypothesis; this closure does not suppress other ready
research or execution packages.

The existing no-network Docker `research` service reproduced the same
aggregate-only receipt through its `/app/market_data` and
`/app/model_artifacts` mounts. The run used sklearn CPU code only, not Torch or
CUDA. Host/container root mapping is now covered by the runner boundary tests.

## Broad Current-Build Reproducibility (2026-08-02)

The frozen 523-symbol Norgate D1 panel now has a narrow active-build matching
receipt: every one of 252,609 retained D1 bars matched two repeatable active
reads. This may support a later separately frozen, non-promoting engineering
consumer that explicitly tolerates its static current-listing, non-PIT,
adjustment, corporate-action, and availability limitations. It does not change
the panel's `model_eligible=false`, `gpu_eligible=false`, or `paper_trading_eligible=false`
scope, and it does not revive the closed fixed-trio GBT or momentum families.

## Injected Multi-Timeframe Replay Seam (2026-08-02)

The new injected-bar seam is complete as integration evidence, not a research
result. It reuses the existing causal `1m/5m/10m/1h/3h` window builder,
completed-bar `MomentumModel`, target-position policy, immutable decision
receipt, local-paper bridge/fill/replay, and next-bar timing harness. Two
independent deterministic fixture runs plus a same-store retry produced the
same safe projection and proved window availability, receipt-to-intent identity,
`source: local_paper`, and replay identity. The timing-only backtest is checked
before any local-paper event, so invalid or too-short injected 1m inputs cannot
leave partial local execution state.

It trains nothing, consumes no dataset, model artifact, GPU appointment,
holdout, public weight, KIS route, or Paper account, and makes no predictive,
selection, ensemble, PnL, or profitability claim. The next ready Engine
candidate is a fresh, CPU-only, source-local KIS NAS D1 volume-exhaustion
reversal falsification contract: volume/range/close-location conditions must
be frozen before target access, use a next-session within-session target,
include flat/candle-only/date-block-null comparators and a signal-count kill
test, and receive Claude's bounded challenge before implementation. It is not
yet an eligible GPU campaign or Paper input.

## KIS NAS D1 Volume-Exhaustion Outcome (2026-08-02)

`kis-nas-d1-volume-exhaustion-reversal-v1` is closed as `falsified` by its
final `cpu-falsification-r4` contract
`sha256:ffe46f6a81e0e44e736db69fefcc7809a33b1e8eef9d1cc66aacb1a05d5f2e9d`
and source-safe summary
`sha256:0fd63b26eaf6680825c13a02bb5fae4b642af0ef121a156e815d0e92e5f87eb4`.
It used only the attested six-symbol, 1,510-session development phase: a
target-free 5,880-slot census yielded 107 signals across all six symbols, then
one fixed 2,802-slot post-purge falsification opened only `t+1` targets.

At the frozen 10/15/20bp cost band, the candidate did not strictly exceed its
same-rule-without-volume comparator or its within-symbol block-null P95; the
primary 20bp relation to flat was also nonpositive. These are categorical
source-local kill facts, not a model-quality, PnL, or profitability claim.
Do not retune the thresholds, rule, chronology, comparator, cost band, null,
or this source partition. This family cannot become a model, ensemble, GPU
appointment, Paper input, or KIS order path.

The pre-final `cpu-falsification-r1` through `r3` receipts are retained only as
scoped, non-promoting recovery evidence. Independent review successively fixed
an Execution import route, incomplete code custody, volume abstention,
Git-root creation before rejection, and artifact-root symlink traversal. The
final r4 contract hashes direct campaign dependencies and accepts only a
non-symlink external root before writes. Claude's bounded architecture challenge
timed out as `review_unavailable`; no Claude endorsement is claimed. No KIS
call, credential, network, broker, local-paper, GPU, training, checkpoint,
sealed evaluation, or live behavior occurred.

The GPU remains unallocated. A future Engine package must be a distinct
source-qualified hypothesis with a fresh contract; the one-session NAS forward
cache is still not enough for an independent prospective outcome surface.

## Tiingo D1 Compression-Continuation Outcome (2026-08-02)

`tiingo-d1-trio-intraday-compression-continuation-falsification-v1` closed as
`falsified` with final r2 contract
`sha256:2b7be8338f99399d7c1af6c9710d9634fb6e2dc74eb428ccdefea9c649743c7b`
and source-safe summary
`sha256:d1964e6b40cff6691eafd6c8300f140d8727c300bd8d2d6a535f44595ed3a39d`.
It used the already-consumed Tiingo ETF snapshot only as explicitly
repeat-source, non-promoting evidence: 6,583 common sessions, 702 target-free
development signals across all three ETFs, and 214 fixed active validation
days after the 61-session purge.

At the frozen 10/15/20bp costs, its 20bp relation to flat was nonpositive and
it did not strictly exceed same-date equal exposure or the joint block-null
P95. These are categorical rule-family kill facts only. Do not retune its
compression threshold, close location, event/discontinuity rule, split, target,
comparators, cost, or null. It cannot become a model, ensemble, GPU appointment,
Paper input, KIS input, or PnL/profitability claim.

The r1 artifact is recovery-only. Final r2 summary custody reattaches an exact
allowlisted artifact before target access; `input_unavailable` preflights are
recorded as `holdout_access=none`. The GPU remains unallocated: this result is
not a reason to invent a depth training job. The next Engine package needs a
separate qualified source or a genuinely distinct non-reused hypothesis.

## KIS Intraday MTF Availability Integration (2026-08-02)

The fixed local KIS input contract is now verified: 21 aligned QQQ/SPY regular
sessions have each causal `1m/5m/10m/1h/3h` tail available at the fixed 15:30
ET `30/6/3/2/2` geometry. This makes the existing prospective baseline and
future pair observation technically reconstructible from KIS-shaped bars.
It is not a fresh historical campaign: 21 independent session blocks permit at
most a weak `10/1/10` session split, and prior QQQ/SPY intraday families have
already consumed or closed their own static evidence.

No GPU appointment is eligible from this receipt. The next Engine contract is
`kis-qqq-spy-mtf-prospective-observation-v1`: retain 30 new aligned QQQ/SPY
15:30 observations, exclude these 21 historical sessions, and persist only
source identities, structural availability, and content commitments. Only then
may a distinct model/target/cost/baseline/kill contract be frozen. This is a
research discipline, not a wait on the foreground or another lane.

## QQQ/SPY Forward-Observation Handoff

Data has installed the credential-free `kis-qqq-spy-mtf-prospective-observation-v1`
consumer behind its owned intraday collector. The current forward-record count
is `0`; its 30-record accumulation remains prospective input evidence only and
does not make a target, model, PnL, GPU, Paper, or ensemble campaign eligible.
The 21 earlier local-cache sessions remain excluded.

This does not idle Engine Research. Ready Engine work may improve the
model-neutral hierarchical decision contracts, causal feature adapters, and
offline validation fixtures without opening a return or reusing the future
observer as a selection surface. Any later training campaign still freezes its
own dataset, target, split, costs, baseline, kill test, artifact root, and GPU
stop rule before Research Steward allocation.

## Causal MTF Prediction-Window Binding

The pure `causal-mtf-prediction-window-binding-v1` extension is complete.
When a caller provides its existing `CausalMultiTimeframeSequenceWindow` to the
target-position policy, the policy revalidates the selected bars and requires
each expert's `feature_window_end` to equal the actual completed bar end for
its timeframe. This prevents a stale or partial slow-timeframe expert from
claiming a fast decision cutoff while leaving existing policy-owned freshness,
missing, duplicate, and future checks single-sourced.

The existing momentum producer passed an injected five-timeframe compatibility
smoke; forged H1 ends, header-versus-contained-bar identity/cutoff mismatch,
and future bars fail closed. The existing target-policy consumer that already
has a causal window supplies it explicitly. Claude's `supported-with-limits`
review rejected a duplicate evidence bundle and untyped metadata-based
source/schema convention. This work created no model, dataset use, target,
return, PnL, training, GPU appointment, artifact, Paper, or live claim. The
QQQ/SPY observer still has `0` forward records, but its collection is
independent of ready Engine work.

## Causal MTF Momentum Expert Adapter (2026-08-01)

The direct `CausalMultiTimeframeSequenceWindow` input path is complete for the
existing momentum experts. It revalidates caller-supplied selected bars through
the sequence-window builder, compares reconstructed identity with the outer
header, and supplies exactly the existing `lookback + 1` tail to each configured
expert. It adds no generic envelope, feature schema, source wrapper, model
family, or fallback resampling behavior.

The fixed five-expert raw/session path and direct-window path produced exactly
equal CPU evidence, then passed the existing causal-window-bound target policy.
A QQQ header containing SPY H1/3h or fully SPY bars, plus future, incomplete,
non-contiguous, and short windows, returns categorical empty evidence. The
Claude CLI check timed out as `review_unavailable`; the temporary independent
Review assignment instead confirmed the narrow API and forgery coverage. No
dataset, target, return, PnL, training, GPU allocation, artifact, Paper, or
live result follows. The 0-record QQQ/SPY forward observer remains a separate
Data-owned schedule, not a foreground wait.
