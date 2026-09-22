# Engine Research Agent Stateboard (Engine Research)

`AGENTS.md` owns policy and `NEXT_CODEX_GOAL.md` owns the company objective.
This is current hypothesis and campaign custody, not an experiment diary. Git
and immutable external artifacts retain closed campaigns and source receipts.

## Ownership And Boundary

Engine Research owns hypotheses, features, rule/ML/DL campaigns, analytical
backtests, walk-forward evaluation, portfolio construction, ensemble research,
and model-side PnL attribution. Its output is evidence or a proposed target
state, never an order.

Before a predictive campaign or GPU appointment, freeze its dataset, target,
temporal split, feature availability, timeframe/window matrix, cost model,
naive baseline, compute stop rule, artifact root, and strongest kill test.

## Current Research State

Completed 2026-09-22 successor: `regular-session-cost-matrix-v2` in the existing
FirstRate H30 trial family. The old cohort first sampled 1,024 TRAIN times from
a 24-hour grid before checking past/future support. New development uses all
regular-session M5 TRAIN decisions, the same 36-bar eligibility for contexts
12/36, 30/60/120-minute targets and nonoverlapping H-cadence EVAL. Two expanding
session folds; TRAIN exits strictly precede first EVAL history start. Costs
remain 1/3/5 bps/side; model threshold 6 bps is a fixed rule, not exact
breakeven. CPU controls/Ridge precede 48 LSTM fits at eight full epochs, without
outcome screening, winner selection or a fresh holdout. Source timestamps are
an explicit unverified assumption, not KIS runtime parity. No Paper dependency.
Focused synthetic/runner tests passed 73 cases. Contract
`sha256:012497f503e322dcbc076aacc174dc10e039b1da185876b0744b07f33e4a0646`
is frozen; both phases used the pinned existing research image,
networkless, source/data read-only, without credentials or Paper changes.
The metadata-only v1 contract was abandoned before dispatch after independent
review found missing post-decision outcome support. v2 requires 32 scored rows
and eight disjoint-history blocks after decisions; insufficient observations
retain safe counts and no returns, rather than a successful all-zero result.
CPU completed 24 Ridge fits and 216 model/control/cost cells in 117.611
supervised seconds. TRAIN support is now 2,232-6,732 rows per fold/horizon;
H30 alone is 4,464-6,732 versus the old 230-241. EVAL contains 62-378 scored
observations per fold/horizon, zero future censoring, 62-63 disjoint-history
blocks. At 3bps/side, 7/24 Ridge cells are positive, 16 negative and one has
zero trades; SMA3/12 is positive in 1/12, previous-bar in 3/12 and always-long
in 1/12. At 5bps, 5/24 Ridge cells remain positive but all those rule/naive
cells are nonpositive. These are separate one-share experiments, not portfolio
returns or a selected winner. CPU summary:
`sha256:5198f95a0c6a8863cd18a9fa8e74431a1e0f4b827b4cebab47b59b58cb14523b`.
The CUDA phase completed all 48 LSTM fits (13,248 optimizer updates) and 144
cost cells in 159.193 supervised seconds, including data loading/replay rather
than pure kernel time. All 48 TRAIN losses improved and beat TRAIN-mean MSE;
that does not establish prediction skill. CPU/CUDA cohort/scaler/censor facts
match. All 48 final models passed numeric schema/hash checks and actual Torch
CPU reload; weights/configs occupy 435,104 bytes externally. CUDA summary:
`sha256:4bacb76827f3de667c331e37b65a5a7b603e6be51b94034041524b268350e3b1`.
At 3bps/side 10/48 LSTM cells are positive, 9 negative, 29 have no trades. At 5bps
6 are positive, 13 negative, 29 inactive. Only 2/24 symbol/horizon/context/seed
combinations are positive in both folds at 3bps; none at 5bps. Beating the
matched always-long control in 48/48 cases is largely loss avoidance, not
evidence of robust alpha. No winner, ensemble or Paper input was selected.
Both containers and child jobs exited, GPU lock released; recovery: complete.
127 focused/parent-regression tests, Ruff and both Compose checks passed.
Next useful research question is whether a persistent target-position policy
reduces unnecessary exit/re-entry costs versus these independent roundtrips;
freeze a new linked contract rather than retuning this closed matrix.

The 2026-09-21 FirstRate M5 open/open development comparison completed once:
two symbols, two expanding development folds, four fixed Ridge fits, and 48
SMA20/60, Ridge, previous-bar, and flat cost cells. It uses a fixed 60-bar
history, next-open/following-open payoff, one share, and 1/3/5 bps per side.
All cells pass independent fee/fill/cash/FIFO replay parity. Of 1,024 sampled
evaluation timestamps, 165 have past-eligible input and 154 observed outcomes;
missing future outcomes were not used to choose the 165 decisions. All four
folds satisfy the frozen minimums and label/history purge. No backfill/tuning.
The one-thread CPU run took 9.838 seconds; no GPU or weights were used.

Most active results are negative after costs. SPY Ridge sums +0.1727 at 1 bps
over only three independent one-share roundtrips and turns negative at 3/5 bps;
this is neither an edge nor a continuous-capital return. No winner was selected.
The old L2/trend/RSI summary hashes matched before this linked development run.
Claude's initial uncertainty was resolved by explicit purge, future-invariance,
no-backfill and exact replay tests; final verdict was `supported-with-limits`.
Already-seen data, unverified source clock/finality/actions, zero execution
latency, and censored missing payoffs prohibit generalization/Paper claims.

Evidence root:
`D:\thericher-v2\model-artifacts\research\firstrate-m5-open-open-development-20260921-v1\20260921-proposed-r1`.
Contract SHA256: `e1aba1b5bbb91d74315e749f02541b9d9d069506e0bbf23edc265c883fd6fe6c`.
Summary SHA256: `2a0d4c9632f569ce2308ddcf306c986591d36cff908cf17562d318327b9a3ce5`.
The independently frozen successor
`firstrate-m5-h30-lstm-development-20260921-v1/20260921-h30-r1` completed
eight Ridge fits/60 CPU cells (33.664s) and 16 LSTM fits/48 CUDA cells
(26.733s, RTX 4090). It compares 12/36 M5-bar contexts, seeds 101/103,
hourly decisions and a 30-minute holding payoff, fixed eight epochs, with
the same 1/3/5-bps band and matched-cadence naive baselines. All four folds
passed strict history/label separation and all 108 cells passed local-paper
replay parity. There were 250 eligible evaluation decisions and 234 supported
outcomes; missing payoffs were censored after decisions, never backfilled.

Both context lengths produced the same aggregate threshold decisions within
each seed. Seed 103 was nearly always long; seed 101 was sparse. SPY seed 101
totals +2.7760/+1.3670/-0.0415 dollars at 1/3/5 bps across only eight separate
one-share roundtrips. The 1-bps positive cells do not establish model skill:
the matched always-long comparator is positive too, while all LSTM combinations
turn negative at 5 bps. No winner, generalization or Paper-input claim.

External root:
`D:\thericher-v2\model-artifacts\research\firstrate-m5-h30-lstm-development-20260921-v1\20260921-h30-r1`.
Contract SHA256: `be785361611db683afb3bd4bb80d245fc69e93fb90279e9ec8a1fafe459e22fe`.
CPU summary SHA256: `06dc794bd575f42aa4079f5f7dac9a61d64f58659664a5587608a74c68b14142`.
CUDA summary SHA256: `4329cf2727bd8adeded60742507ce596be6b20e134e6639db61dd71bdb95d99e`.
All 16 final weights and train-only scalers are in `models`, numeric-only NPZ
plus hash-bound configuration. Actual Torch CPU reload/finite synthetic
inference passed for all 16; no arbitrary-code deserialization or Execution
consumer. The existing research image was rebuilt to include its already-pinned
calendar dependency; actual version custody is in `agents/research-steward.md`.

The train-only diagnostic completed all 16 restored fits in 13.201 CPU seconds,
without optimizer steps, GPU, evaluation tensors or predictions. It binds the
original contracts/source/models/scalers and trims data before each evaluation
history cutoff. The immutable appendix is `train-diagnostic-v1\summary.json`
under the H30 root above. Diagnostic contract SHA256:
`d4334e56edc55368662c9a94ef0428a49365e6669102abc8f14730826311849f`;
summary SHA256:
`8dac1484b6e67087004fe79f3d65c4927a7bedd05b779c99f74f9e39cc800034`.
All 16 parameter sets moved (RMS 0.01146-0.01324) and improved over seeded
initialization, but final train MSE 1.00577-1.02045 remained worse than the
train-mean baseline. Each fit had only 230-241 train rows and 16 optimizer
updates. Masking the oldest 24 of 36 bars changed prediction RMS by only
0.00160-0.00703 bps, with no sign change in seven fits and one in the eighth.
These are training diagnostics, not comparative return or generalization facts.

The separate four-fit learnability check completed in 9.779 CUDA seconds on
the same image: LSTM16/context12/seeds101/103, fixed synthetic64 and first16
chronological SPY fold1 TRAIN batches, 256 updates each. Both batches had zero
duplicate/conflicting inputs. Synthetic final MSE/mean-baseline ratios were
0.013432/0.006089, satisfying the predeclared <=0.1 criterion for both seeds.
Real-batch ratios were 0.000672/0.0000528: near memorization, not prediction.
Finite gradients/movement and independent loss parity passed; no evaluation,
weights or individual predictions were retained. GPU lock released.
Immutable summary: `D:\thericher-v2\model-artifacts\research\firstrate-m5-h30-lstm-development-20260921-v1\train-learnability-v1\summary.json`.
Contract SHA256: `f2be555bc0b42f58237a6bc23ab258dcecd04491bcf70036f86a2cc9e4b663b2`.
Summary SHA256: `833a5aafbdf1ea561be2d9fb4d449f19c0c0f4e0df88ab42ec747ecf6abf653d`.
This demonstrates basic training/capacity, not full-cohort convergence or
profitability. Do not create another mechanics prerequisite from this result.

The distinct `full-cohort-u256-v1` sibling is now frozen under the H30 family,
contract SHA256 `d7cceb5ab3642d2a727bc8f0f73ac3ee58a3b1393b196a553e057391c1ece596`.
Its context12 SPY/QQQ x original two folds x seeds101/103 matrix has eight
LSTM16 fits, exactly 256 chronological batch128 updates each, the same AdamW,
max36 eligibility/scalers/purge and 1/3/5-bps payoff/replay controls. Budget:
2,048 updates and one 180-second CUDA appointment; CPU cap 600 seconds.
Four fresh Ridge fits and all matched naive controls must reproduce the old
context12 CPU cells exactly. All eight final-update weights are retained only
after whole-phase parity and numeric/actual Torch CPU reload; no checkpoint
selection, tuning, fresh holdout or promotion claim. Claude's tool-disabled
challenge was `supported-with-limits`: TRAIN loss improvement is descriptive,
not a success criterion; seen-data behavior cannot establish independent skill.
The CPU phase completed four Ridge fits/48 cells in 19.783 parent-supervised
seconds; every fresh control cell equals r1. The one CUDA phase completed
eight fits/24 cells and all 2,048 updates in 27.336 parent-supervised seconds
(25.403 worker seconds, 4.947554 summed fit-wall seconds, not kernel time).
All 72 cells pass local replay parity. TRAIN final MSE/mean-baseline ratios
range 0.525285-0.739221, with 230-241 TRAIN rows per fold; these loss changes
are descriptive only. Evaluation retains the original 250 eligible decisions,
234 supported outcomes and 16 future-censored outcomes per seed. Across both
folds, fixed SPY seed101/103 net dollars at 1/3/5 bps are respectively
`4.2441/-7.2053/-18.6533` and `4.2165/-9.3278/-22.8699`; QQQ seed101/103 are
`1.8300/-8.6427/-19.1153` and `7.2627/-4.7186/-16.6990`. Every 3/5-bps LSTM
cell is negative; these are independent one-share roundtrips, not NAV or skill.
All eight final-update NPZ/config pairs are retained under the sibling's
`models`; hash/schema and actual Torch CPU synthetic reload passed. Per-fit
hashes, train losses, activity, censor counts and matched-control deltas are
in `cuda-summary.json`. CPU summary SHA256:
`5d8ecd2cf2e170a35b6115f8deda05c16f3d09736d42e433824e1d9071c50b3b`;
CUDA summary SHA256:
`4b26bfffb377be6462ac56346526f5089dc6214d800a8b0e8491662fc6f15237`.
Both phases used the existing pinned image, networkless, source read-only;
no rebuild, credentials, schedules, selection or promotion. Container reaped,
lock released, bounded assignment complete; no successor GPU allocation.
Original r1 and diagnostics remain immutable; D1/Paper work is independent.

The linked `fixed-nominal-hurdle-v1` DEVELOPMENT package is complete. It restores
ALL eight full-cohort final models without fitting, selection, holdout or GPU.
The target is gross return bps after inverse saved TRAIN normalization; the
single strict `>6` hurdle is nominal roundtrip 3bps/side, unchanged at 1/3/5bps.
It is not exact rounded-fee breakeven: even before fee rounding that is
`6/(1-0.0003)` bps. Claude's pre-outcome supplied-facts/tool-disabled challenge
was `supported-with-limits`; no suggested extra threshold arm was added.
All 84 cells pass local fee/fill/cash/FIFO replay; all 24 original sign-only
and 36 naive cells reproduce exactly. Source/model/scaler/cohort/mask hashes
reattach before/after; 250 eligible, 234 observed, 16 censored per seed remain.
Across both folds, SPY seed101/103 hurdle net dollars at 1/3/5bps are
`0.8351/-1.1750/-3.1849` and `3.8910/2.1729/0.4548` (12/10 trades versus
67/78 sign-only); QQQ seed101/103 are `3.6276/-0.9822/-5.5918` and
`2.3623/-0.7129/-3.7873` (32/21 versus 74/85 trades). No winner is selected.
SPY seed101 fold2 has zero hurdle trades; QQQ seed103 fold1 worsens versus
sign-only at 3bps. Aggregate improvement is not uniform per-fold or skill.
Seen data, unqualified clock/finality/actions, dependent capped histories,
future censoring, fees-only/zero-latency replay and no KIS parity remain limits.
Evidence: `D:\thericher-v2\model-artifacts\research\firstrate-m5-h30-lstm-development-20260921-v1\fixed-nominal-hurdle-v1\summary.json`.
Contract SHA256: `6e00636fe0eb2b507affbc22c296281997946a9a39de7df171317b6204832c73`.
Summary SHA256: `8a54c24785716d04bd1958bcce951a6e9bbaa7881d24a47e7b9fd4ada24db86b`.
The pinned networkless image completed once in 14.941 supervised seconds,
13.485 worker wall / 8.822 worker CPU seconds, below the 300-second limits.
All data/source/parent artifacts were read-only; child/container and temporary
job reaped, no research Python worker. Test scratch `C:\trpy\fixed-hurdle-20260922-a`
is inactive but retained because manual cleanup was tool-policy denied.
Focused synthetic tests: 18 passed; Ruff passed. Recovery: complete.
No retry, threshold extension, retraining, schedule,
new weights, promotion or follow-on allocation; main retains Execution.

## Historical Evidence (Closed Scopes)

The dated results below retain their original limitations. Statements about
then-active campaigns, eligibility, or readiness are historical, not current
dispatch restrictions. The current development package is described above.

- The 2026-08-19 UTC Tiingo Standard EOD fixed ETF snapshot reattests as one
  three-request prospective lineage record with a 2026-08-12 source-as-of
  boundary. Its closed scope leaves point-in-time, model, training, campaign,
  ranking, Paper, and GPU eligibility false. It is not a predictive input or a
  Research Steward appointment.
- `firstrate-5m-after-cost-control-v1` is complete and `rejected`. Its frozen
  source-local, CPU-only 60-bar L2-logistic control did not beat `always_flat`
  in any of the six SPY/QQQ cells under the fixed 1/3/5-bps per-side band.
  All 18 model/baseline local-paper cells reattached as replayable and
  terminal-flat. It cannot allocate GPU, tune, select, ensemble, or reach
  KIS/Paper. The immutable source-safe summary is
  `firstrate-5m-after-cost-control-v1/20260820-r2/summary.json`
  (`sha256:249a55dc53605e5381cfbaaef370ce9d36302c93594abc421a65b6685857fb2c`).
- `firstrate-m5-trend-rule-after-cost-control-v1` is complete and `rejected`.
  Its fixed calibration-free 20/60-bar technical trend rule did not beat
  `always_flat` in any of six SPY/QQQ nonzero-cost cells. All 18 local-paper
  cells were replayable and terminal-flat. It cannot be tuned, selected,
  ensembled, allocated GPU, or made a KIS/Paper consumer; the summary is
  `firstrate-m5-trend-rule-after-cost-control-v1/20260820-r1/summary.json`
  (`sha256:539463a0d6cb84ba16fd75e750493277adc5e9f00f94a5e51f00d1cb44a78d00`).
- `firstrate-m5-mean-reversion-after-cost-control-v1` is complete and
  `rejected`. Its frozen long-only completed-bar Wilder-RSI(14) <=30 entry,
  >=50 exit, and predeclared terminal flatten did not beat `always_flat` in
  any of six SPY/QQQ nonzero-cost cells. All 12 local-paper cells were
  replayable and terminal-flat. It cannot be tuned, selected, ensembled,
  allocated GPU, or made a KIS/Paper consumer; the source-safe summary is
  `firstrate-m5-mean-reversion-after-cost-control-v1/20260820-r1/summary.json`
  (`sha256:b437e8e39e9cb3963e13bf4778daee7e92d0de6c32cec6e9dac24e462f16266f`).
- The isolated QQQ/SPY D1 v2 forward cache is collection/provenance evidence
  only: its initial 18 common sessions reattach under the v2 identity, but
  point-in-time availability, provider finality, and corporate-action
  qualification are unobserved. It cannot freeze a target/split, enter a
  campaign, reserve GPU, or become a KIS/Paper consumer.
- The current QQQ/SPY D1 prospective observation receipt is a scoped
  `input_unavailable/first_observation_target_failure` first stage for completed
  session 2026-09-04, with no
  first-receipt binding or later observation, so it is not a pair result. Its
  first/later hash comparison remains a Data-only disqualification measurement;
  a match cannot freeze a campaign, allocate GPU, select a model, or create a
  KIS/Paper consumer.
- No frozen, input-qualified predictive campaign is active. The latest
  task-owned QQQ/SPY M1 chain is `input_unavailable`; its optional causal
  attestation is `not_recorded`, so it cannot freeze a target, split, or
  30/60/90-minute candidate matrix. One direct host collection completed the
  two-target/four-page scope, but it has no Task/Docker provenance, causal
  availability/finality evidence, or research-consumer promotion. The first
  container attempt yielded at the shared token-start gate before a token POST,
  so it likewise creates no dataset, target, split, or campaign change. The
  due-gate container attempt reached retained-cache quarantine for both targets;
  the later direct Compose recovery capture completed cleanly, but remains
  unbound and non-promoting until distinct task-owned causal qualification
  conditions are independently met.
- The 2,119-target KIS daily-broad continuation is exhausted under its current
  historical cursor contract: its short reattachment made no KIS request and
  advanced no cursor. It creates no refreshed daily input, campaign, GPU
  appointment, or Paper consumer; later sessions require the separate forward
  cache path.
- The first QQQ/SPY D1 forward-cache refresh required collection but deferred
  at the shared token-start gate, adding zero pages and zero target changes.
  It leaves the seven-session source-local cache non-promoting and creates no
  campaign, GPU appointment, model selection, or Paper consumer.
- The completed Data-only forward causal-qualification predicate classified the
  seven-session QQQ/SPY D1 cache as `input_unavailable`: source/pair identity,
  complete-calendar continuity, and chronological boundary are satisfied, while
  named clock/session, decision-time availability, and provider finality remain
  `not_observed`. Its source-safe external receipt is
  `data/kis-daily-forward-causal-qualification-v1/run=20260820-kis-daily-forward-causal-qualification-r1/receipt.json`
  (`sha256:9b361addc7e76dd5cd8ff6bf9800077c8a8866f3b5a21eeedbeb6d2a2dcdc3cf`).
  It does not qualify a Research campaign, GPU appointment, model selection,
  replay, or Paper consumer.
- The fixed source-safe D1 failure stages and networkless readiness now passed
  synthetic checks. The one readiness receipt was `ready/aggregate_ready`,
  token due, and rate-open without network or cache writes; its one allowed
  collector invocation still returned `unavailable/collector_unavailable` with
  no cache payload and no `failure_stage`. That receipt therefore does not
  attest the stage-aware runtime image, and no retry followed. The offline
  cache remains readable at seven common sessions; no causal requalification or
  consumer change follows. Even a successful collection cannot satisfy named
  clock/session, decision-time availability, or provider finality, and no
  consumer may interpret a newer `latest_session` as those facts. It creates no
  campaign, GPU appointment, model selection, replay, or Paper consumer.
- The three pair-forward Compose services now share one local image tag. Their
  one credential-free networkless preflight emitted a payload-only static stage
  contract hash matching the host source contract, then returned
  `collection_required`. This proves no full image freshness, data availability,
  finality, or causal qualification, and it made no collector/KIS call.
  Research receives no campaign, GPU, model-selection, replay, or Paper
  consumer from it.
- That fresh one-shot collector is now closed as
  `unavailable/collector_unavailable/failure_stage=commit` with a matching
  static contract hash and no cache payload. The offline cache still reattests
  with seven common sessions and no observed cache-file/index write in the
  invocation window. This is an unknown commit-stage fact only; it creates no
  campaign, GPU appointment, model selection, replay, or Paper consumer.
- The v2 preflight then permitted exactly one new collector call, which closed
  as `unavailable/collector_unavailable/failure_stage=commit` with fixed
  `commit_failure_kind=cache_contract`. The cache reattests unchanged at seven
  common sessions, with no cache payload or observed cache/index mutation. This
  narrows a Data recovery family only; it creates no campaign, GPU appointment,
  model selection, replay, or Paper consumer. A local-only future phase
  diagnostic cannot change that boundary.
- The completed local phase diagnostic gives a future `cache_contract` receipt
  one optional static boundary label only; it does not reinterpret the v2
  receipt. Its v3 contract is not a campaign input, GPU appointment, model
  selection, replay, or Paper consumer.
- The v3 one-shot is now `commit/cache_contract/cache_prepare`, while the
  external cache reattests unchanged. This is a narrower Data recovery fact
  only; it still creates no campaign, GPU appointment, model selection, replay,
  or Paper consumer.
- The v4 source-only subphase contract can label a future matching exception by
  fixed source region only. It does not interpret the v3 result, create a
  campaign, consume GPU custody, select a model, run a replay, or create a
  Paper consumer.
- The one permitted v4 collector deferred with source-safe KIS authentication
  and token-gate states, not a v4 commit subphase. Its bound cache retains the
  same seven common sessions and remains Data-only; it creates no campaign,
  GPU appointment, model selection, replay, or Paper consumer.
- The later token-only KIS Paper capability receipt is `authenticated`, but it
  has no daily page, finality, or decision-time availability fact. It changes
  no campaign, GPU appointment, model selection, replay, or Paper consumer.
- V5 readiness was gate-open but its one D1 collector failed before cache
  commit at the static `incoming_merge` region; the current seven-session cache
  reattached unchanged. The completed source/fixture reconciliation now makes
  exact duplicates idempotent, preserves retained conflicts under durable
  target-local quarantine, and lets only strictly later sessions append. The
  causal reader rejects every non-ready target, so this remains Data-only and
  creates no campaign, GPU appointment, model selection, replay, or Paper
  consumer.
- The post-policy fixed-pair observation then retained two target-local revision
  conflicts and quarantined both targets. Its offline causal receipt is
  `input_unavailable` with source-pair identity unsatisfied in addition to the
  existing clock, availability, and finality gaps. This is not an independent
  recovery, model input, campaign, GPU appointment, replay, or Paper consumer.
- The fixed historical KIS D1 CPU baseline reproduced independently for QQQ and
  SPY from the same 4,756-bar common panel. Each exact four-cell local-paper
  matrix completed, and every after-cost result was negative; QQQ
  `previous_bar_direction` holdout at `-0.3965` is only the closest negative
  control. The one fixed development-only L2 logistic control then completed on
  the same hash-pinned panel: its QQQ/SPY after-cost replays were `-109.2703`
  and `-139.3587`, below the corresponding previous-bar-direction controls.
  All two model and six comparator cells used `local_paper`, validation labels
  were excluded from fitting, and no GPU/model-selection/Paper consumer follows.
  The one fixed shallow regime-tree reproduction then completed under the same
  constraints, with QQQ/SPY after-cost results `-45.8296` and `-73.7783`, also
  below their fixed previous-bar-direction controls. It retained no serialized
  estimator. Both failed lineages are closed descriptive controls; neither has
  a retry, tuning, selection, ensemble, GPU, or Paper consumer.
- The RTX 4090 source-isolated Tiingo IEX r1 appointment completed and released
  its memory. Its M5-only masked reconstruction used the fixed
  LSTM/causal-TCN/compact-attention order with no target, holdout, selection,
  retained weights, or promotion path.
- QQQ 20-session M1/M5/M10/H1/H3 resampling and six canonical causal window
  profiles are complete source-local mechanics. They are target-free and
  non-promoting.
- FirstRate SPY/QQQ canonical M1 data has source-local UTC-anchored
  1m/5m/10m/1h/3h mechanics plus a completed fixed target-free window matrix.
  It retains only geometry/count evidence, not labels, features, predictions,
  a campaign, GPU appointment, model selection, KIS equivalence, or Paper input.
- Claude's 2026-08-19 falsification-first review found a FirstRate GPU
  representation study `unsupported`: without a meaningful source time-grid
  contract, retained artifact, or decision path it would only manufacture a
  runtime benchmark. The subsequent FirstRate source retrieval confirmed only a
  vendor timezone label and zero-volume omission; offset convention and bar
  boundary remain `not_disclosed`. The completed Norgate host bridge is
  `input_unavailable/local_api_not_ready`, so it unlocks no trial data work.
  The completed six-source contract inventory leaves every class non-promoting:
  three are `input_unavailable`, and the remaining FirstRate/Tiingo classes are
  mechanics, retrospective-control, or runtime-only. GPU custody stays free;
  no frozen predictive campaign is ready.
- The completed Norgate reconciliation narrows its local host condition to
  `local_api_not_ready_updater_not_observed`; it adds no data input. Claude's
  later direction check is `supported-with-limits` only for a KIS D1
  prospective decision-time/post-finality observation pair. That work can
  disqualify revision leakage but cannot freeze a target, spend GPU, or create
  a candidate until a separate qualified input contract exists.
- Fixed session-reset 15/30 EMA and 20/10 Donchian local-paper replays have
  replayable, terminal-flat accounting evidence and negative fixed baselines.
  Do not retune their windows, costs, thresholds, or signs under a new label.
- The shared sequence encoder now also exposes a causal GRU baseline and the
  Tiingo D1 breadth runner uses that same factory. This is implementation
  consistency only: no frozen screen, campaign, GPU appointment, model
  selection, or Paper path changed.
- The minimal action-vote ensemble now maps a highest-vote tie to `hold`,
  canonicalizes prediction-ID order, and labels a tie `tied_vote_hold`. Its
  full decision projection is independent of caller order. This is deterministic
  local fusion only: it does not select a model, create a campaign, consume
  data, allocate GPU, or authorize Paper behavior.
- Target-policy proposal identities now use canonical tie-break fields before
  hashing, and validation consumes that same order, so a mixed invalid evidence
  set has one categorical abstain and identity regardless of caller order. This
  preserves replay and deduplication semantics only; it
  changes no model, campaign, input qualification, or Paper behavior.
- Existing CPU/CUDA structural screens for LSTM, causal TCN, and compact
  attention prove only a local runtime path. They do not select a model.
- A caller-owned synthetic two-step local-paper policy replay now proves that
  independent decisions can submit and fill sequentially at next-bar boundaries
  with the same fee/slippage and replay/PnL accounting semantics. It is an
  interface capability fixture, not a market, model, or PnL result.
- The pure target-policy cycle now accepts only an existing monotone
  current-source eligibility attestation, composes caller-ordered per-symbol
  policy outcomes with the same-snapshot allocation helper, and retains both
  proposal layers for later attribution. It has no data, model, ranking,
  reservation, execution, or Paper authority; without a qualified input it
  cannot create a candidate or research result.
- The pure source-attested selection-policy cycle now adds the upstream
  cross-sectional decision layer. It requires one shared snapshot/as-of,
  completed-bar semantics, availability grade, frozen selector, and score schema before
  top-K selection; stale, duplicate, unqualified, future, or mixed inputs
  reject only that cycle. Every valid candidate retains a selected or
  not-selected outcome, and selected candidates retain their later policy and
  allocation outcomes separately. Claude's `supported-with-limits` review
  requires a future campaign to freeze the ranking key, K, turnover, capacity,
  correlation, and cost assumptions before any comparative, ensemble, or Paper
  claim. Distinct candidates must also carry distinct opaque score-evidence
  references before ranking, so one reference cannot be reused inside a
  cohort. This pure mechanism has no score generation, data, training, GPU,
  reservation, execution, or Paper authority.
- For a selected candidate only, Research now replays the entire supplied
  selection, per-symbol policy, and allocation cycle from the original inputs
  and frozen configs before issuing an opaque lineage `proposal_ref` for the
  existing decision-receipt and local-paper bridge. Cohort lineage commits the
  full source attestation of every selected and not-selected candidate, so a
  changed valid source time/state cannot reuse a prior lineage. A substituted
  downstream target fails closed. It still proves neither a complete universe
  nor a predictive score or Execution correctness; a mismatched receipt/binding
  reference also fails closed.
- The local-Paper replay now retains both entry and exit decision identities on
  valid FIFO close segments, with separate role and pair accounting totals.
  Its pure receipt resolver attaches only exact opaque campaign/model/input/
  proposal lineage and fails closed on missing, duplicate, role, or instrument
  mismatch. Descriptive trade-path attribution also requires every local-paper
  fill to match its declared artifact market and symbol. This is future
  PnL-attribution plumbing only: it neither assigns causal credit nor changes
  the lack of a qualified dataset, candidate, model, execution result, or
  Paper outcome.
- A bounded candidate evaluation passes one in-memory model-byte snapshot to
  its runner and records its SHA-256. Direct Local-Paper replay and the
  threshold variants derived from a saved probability trace each require that
  completed evaluation's candidate identity, parameters, and exact model hash
  before invoking a runner or creating an event store; an unbound trace remains
  analyzable but yields prepared, no-fill variants after clearing matching stale
  variant artifacts. A descriptive candidate comparison runs its baseline only
  after completed, aligned candidate replay evidence. Candidate replay and
  comparison namespaces reject existing exact metrics/event/SQLite/emergency
  outputs before a runner or baseline write, preserving completed and partial
  evidence rather than clearing it. Claude's `supported-with-limits` review
  exposed and narrowed a stale-baseline-delete interaction; output concurrency
  remains the job owner's responsibility. This binds the candidate stack only;
  generic rule-model provenance plus trace immutability and mutable runtime,
  feature, and sidecar contracts remain separately scoped. It is replay-evidence
  custody, not a promotion, GPU appointment, or Paper authorization.
- Persistent campaign Local-Paper replays reject every exact partial-file name,
  including SQLite journal/WAL/SHM sidecars, so a failed deterministic run
  cannot silently mix with a later attempt. `discard_partial_campaign_replay`
  is an explicit, artifact-root-guarded recovery operation only when that run
  has no completed validation artifact; it removes only those exact regular
  files, preserves unrelated work-directory content, and never recurses or
  removes an artifact. Its Claude drift-check returned no response
  (`review_unavailable`), so no Claude verdict was relied on. This is offline
  replay hygiene, not a model result, promotion, Paper action, or authority
  change.
- The refreshed Tiingo SPY/QQQ/IWM raw-D1 snapshot is a non-PIT continuation of
  already inspected history. A new bounded developmental contract may reuse it
  with its assumptions and trial-family history visible. It cannot become a
  fresh holdout, independent replication, or a silently substituted KIS input.
  Existing frozen masks/results remain unchanged; revision is a new linked
  contract, not an opportunity to relabel the failed experiment as successful.
- The frozen Tiingo D1 trend-pullback rotation reattached its exact snapshot
  and independent receipt, then stopped as
  `input_unavailable/insufficient_validation_active_decisions`: 3 active
  decisions against a fixed minimum of 100, with 1,892 of 1,896 scheduled
  validation decisions excluded by the existing event/discontinuity conditions.
  Its completed aggregate audit found every exclusion was event-driven, with no
  discontinuity-only exclusion or semantic contradiction. This closes the
  source-local lineage, not performance evidence, a selection result, a GPU
  appointment, or a Paper input.

## Current Tracks

| Track | Current status | Next valid trigger |
| --- | --- | --- |
| Technical/chart and momentum/regime | Existing controls remain rejected or structurally sparse | Freeze a new development-only hypothesis on existing lawful data; test action-invariant features rather than retrospectively weakening the closed mask |
| Classical ML/statistical | Existing L2 result remains rejected | Match label and replay payoff in a linked development contract; separate past-known eligibility from future outcome censoring |
| Sequence/DL/public model | Existing runtime/representation studies remain closed | After CPU feedback, freeze a finite small sequence comparison with explicit source assumptions and GPU custody; no D1 dependency or automatic promotion |
| Portfolio/allocation/meta-decision | Deterministic allocation foundation exists | Fixed-baseline risk/sizing development may use aligned source-local data; candidate ensembles still need the existing independent aligned-evidence contract |

The fresh QQQ/SPY intraday terminal remains
`input_unavailable/session_coverage_incomplete` despite verified capture and
availability bindings. The new future-only causal-attestation writer correctly
leaves that immutable terminal unchanged. It creates no frozen contract,
candidate, training run, GPU appointment, sealed-evaluation spend, ensemble
input, or Paper input. Only that exact causal intraday consumer waits for
complete-session recovery; the independent developmental queue continues.

The first post-writer 2026-08-19 KST dispatcher marker reattached as an exact
task-path `collection_exit_nonzero / reason_unavailable` terminal. It remains
one Data diagnostic, not a cause attribution or recovery premise: its stage
label and one category binding cannot establish collector-process entry,
provider state, or a capture remedy. It creates no qualified dataset, target,
split, campaign, GPU allocation, or change to the frozen 30/60/90-minute
candidate matrix.

## Public-Source References

| Reference | Status | Limit |
| --- | --- | --- |
| Qlib | MIT `architecture_reference_only` | No package, code, data, model, runtime, or campaign adoption. |
| PatchTST | Apache-2.0 `future_sequence_architecture_reference` | General time-series claims only; financial pretraining/evaluation scope is not disclosed, and no runtime, code, weight, or campaign is adopted. |
| Crossformer | Apache-2.0 `future_cross_dimension_multivariate_sequence_architecture_reference` | DSW segments, router-mediated temporal/cross-dimension attention, and hierarchical multiscale decoding are source-only references; generic non-financial evaluation and undisclosed pretraining leave KIS causal timing, session, finality, and multi-timeframe mapping unproven. |
| TiDE | Apache-2.0 `future_mlp_multihorizon_baseline_reference` | Source-only reference for an observed-feature MLP encoder-decoder baseline. Its generic long-horizon benchmark, TensorFlow reference runtime, and any future-known market covariate are not adopted; a qualified campaign must independently prove causal feature availability. |
| TimeMixer | Apache-2.0 `future_multiscale_mlp_baseline_reference` | Source-only reference for past decomposable mixing and multipredictor fusion across scales. Its generic non-financial benchmarks, optional future temporal features, and average-downsampled hierarchy are not adopted; a qualified campaign must freeze its own causal 1m/5m/10m/1h/3h scale mapping. |
| N-HiTS | Apache-2.0 `future_single_timeframe_hierarchical_forecast_reference` | Source-only reference for past-observed hierarchical interpolation and multi-rate pooling within one timeframe. Its generic long-horizon benchmarks, automatic tuning, and future/static covariate interfaces are not adopted; internal multi-rate sampling does not establish a 1m/5m/10m/1h/3h cross-timeframe mapping. |
| Temporal Fusion Transformer | Apache-2.0 `future_multihorizon_sequence_architecture_reference` | Source-only reference for a strict static/past-observed/known-future covariate partition. Its TensorFlow reference runtime, non-trading evaluation, and any future-known market feature are not adopted; a qualified KIS campaign must independently prove causal feature availability. |
| StockMixer, MASTER, CMLF | `source_retrieved_source_only` cross-sectional and multi-granularity structural references | StockMixer claims indicator/temporal/stock mixing but has no disclosed license in its retrieved official repository. MASTER's official MIT code is China-equity/Qlib scoped and its README reports a validation-data processor defect and later source substitution. CMLF claims adaptive multi-granularity fusion but exposes no code/license or compatible scope. None supplies a KIS-compatible universe, point-in-time availability, feature contract, model code, weight, campaign, or Paper input. |
| FinRL | MIT `rl_environment_interface_reference_only` | Its official classic framework is an educational/research train-test-trade pipeline that assumes external data and a new DRL runtime. Exclude its data preprocessing, same-bar reward timing, and cost/fill conventions; only its environment-to-agent separation is a future allocation-design reference. No package, code, data, weight, runtime, campaign, or Paper route is adopted. |
| Heston et al.; Gao et al. | Re-retrieved source-only completed-30-minute OHLCV mechanism references | Their claimed intraday continuation/momentum effects require a fresh, causal, full-session input and a separately frozen campaign before any test. No parameter, model, data, campaign, GPU, ensemble, or Paper adoption follows. |
| Chronos, TimesFM, Granite | Isolated source/runtime studies only | Unknown or incompatible financial pretraining/evaluation scope prevents comparative or Paper use. |
| MOMENT, Time-MoE | MIT / Apache-2.0 `source_retrieved_source_only` references | MOMENT is a general patch-reconstruction representation family with a Python 3.11 recommendation; Time-MoE is a general autoregressive MoE forecasting family whose official usage specifies `trust_remote_code=True` and a separate Transformers version. Financial pretraining/evaluation scope is not disclosed for either. No code, package, weight, model, campaign, GPU, ensemble, or Paper route is adopted. |
| PyPortfolioOpt HRP | Source-only allocation reference | Requires causal candidate returns, PIT universe, and completed rolling windows. |

Qlib evidence:
`D:\thericher-v2\model-artifacts\research\engine-source-retrieval\qlib-architecture-source-20260809-r1\source-retrieval.json`.
PatchTST source-only evidence:
`D:\thericher-v2\model-artifacts\research\engine-source-retrieval\patchtst-source-20260809-r1\source-retrieval.json`.
Crossformer source-only evidence:
`D:\thericher-v2\model-artifacts\research\engine-source-retrieval\crossformer-source-20260819-r1\source-retrieval.json`
(`sha256:826f75a4ae05ca0f0955ebe711cb6887045c3dfc708d87f9cb3483e03982b7b6`).
TiDE source-only evidence:
`D:\thericher-v2\model-artifacts\research\engine-source-retrieval\tide-multihorizon-source-20260819-r1\source-retrieval.json`.
TimeMixer source-only evidence:
`D:\thericher-v2\model-artifacts\research\engine-source-retrieval\timemixer-multiscale-source-20260819-r1\source-retrieval.json`
(`sha256:b52a069032a04077158a6614b296513e7f5b238a96f519650d018da86cfe5a12`).
N-HiTS source-only evidence:
`D:\thericher-v2\model-artifacts\research\engine-source-retrieval\nhits-hierarchical-forecast-source-20260819-r1\source-retrieval.json`
(`sha256:4a6352247e061bd4b28a62e3cec4b52189d3ddc6c2147a336b5caff1741de1d2`).
Temporal Fusion Transformer source-only evidence:
`D:\thericher-v2\model-artifacts\research\engine-source-retrieval\tft-multihorizon-source-20260819-r1\source-retrieval.json`.
Cross-sectional and multi-granularity source-only evidence:
`D:\thericher-v2\model-artifacts\research\strategy-discovery\cross-sectional-multigranularity-sources-20260820-r1\source-retrieval.json`
(`sha256:abe767637e6197757e759c59dcd6306216db5d15edceaf282dea48689b91f6a7`).
FinRL source-only evidence:
  `D:\thericher-v2\model-artifacts\research\engine-source-retrieval\finrl-environment-interface-source-20260819-r1\source-retrieval.json`.
Completed-30-minute OHLCV mechanism source-only evidence:
  `D:\thericher-v2\model-artifacts\research\engine-source-retrieval\intraday-ohlcv-us-equity-sources-20260819-r1\source-retrieval.json`.
MOMENT and Time-MoE source-only evidence:
  `D:\thericher-v2\model-artifacts\research\engine-source-retrieval\moment-time-moe-source-20260828-r1\source-retrieval.json`
  (`sha256:d7147c4e334cafdd311d5ec9e2c08ebb801062a06c8c731cffed39a35f93bb41`).
Public source proposals never authorize code import, weight download, training,
ensemble use, or Paper routing on their own.

## Promotion Sequence

This sequence is for independent/promoted claims, not permission to start a
developmental study or a separately scoped baseline Paper experiment.

1. Data provides a qualified, immutable consumer input.
2. Freeze exactly one campaign with a predeclared horizon or finite
   30/60/90-minute window matrix, shared family budget, causal observation
   rule, cost band, and naive baseline.
3. Run CPU preparation, then submit a GPU-eligible frozen campaign to Research
   Steward if its compute stop rule warrants it.
4. Treat screening as non-promoting until an independent later/disjoint
   replication and sealed evaluation agree.
5. Obtain Execution replay-parity evidence before a comparative, ensemble, or
   Paper-candidate claim.

## Active Constraint And Handoff

Dispatch the ready development comparison above. Keep the original FirstRate
losses and Tiingo sample shortage intact; neither proves all model families
unusable. A later independent performance claim needs genuinely unseen evidence.

The completed source-isolated CUDA appointment proved only loader, geometry,
finite-run, and cleanup facts. It cannot change the unavailable QQQ/SPY causal
input, create a predictive candidate, or feed KIS Paper. Its lineage is closed
to selection; a later distinct ready track needs its own frozen contract.
