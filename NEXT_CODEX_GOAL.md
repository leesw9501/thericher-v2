# Next Codex Goal

## Objective

Complete pooled-equity-participation-value-development-v1: test absolute
basket-payoff prediction for buying versus cash, then joint expert selection.
This is a NEW mechanism, not a rank-model name swap or a rejected-family rescue.

## Scientific Scope

Same128 original current-listed keys, no replacements. Old exact compact800
sessions2023May17..2026Jul27 are SEEN TRAIN, including former DEV. Separate
pinned current100 sessions2026May18..Oct8 provide39 later dated targets
Aug14..Oct8, indices761..799 after61 warmup. No value-window merge, latest scan,
holdout, independent replication or39 independent-sample claim. Goal33 results
informed this hypothesis; current DEVELOPMENT is explicitly adaptive/seen.
Keep RAW/CA/TR/non-PIT/finality/actual historical availability limitations.

Prior61 complete scheduled bars decide eligibility BEFORE targets. Context is
exactly two channels: equal-weight eligible-cohort mean log overnight/intraday
returns over the prior20 completed sessions; use the SAME decision-time cohort
at every context step. Empty cohort has no model context; fewer10 stays
analytically flat, not a broker liquidation instruction.

Five fixed top10/equal fractional experts: component, momentum5/20/60 and
uniform centered-rank blend. Seal all baskets before target callbacks. TRAIN
labels are their five absolute nextOPEN-to-sameCLOSE NET returns at10bps round
trip, not centered cross-sectional ranks. Any missing selected payoff invalidates
the whole five-output training date; never shrink or replace a basket. One row
per date, not five independent targets; overlapping contexts/correlated outputs
and effective sample size unknown. Earliest367/final739 potential dates stress
GRU capacity; actual valid counts must be recorded, not assumed.

Exactly two models: alpha1 multioutput Ridge (one augmented lstsq, intercepts
unpenalized, flatten20x2) and fixed GRU(input2/hidden16/one biased layer/output5).
Identical prefix-only two-channel scaling: reshape TRAIN toN*20x2, population
mean, exact constant-channel correction, sqrt(mean squared deviations), zero
scale->1. Seed101/float32/batch64/AdamW1e-3/.01/512updates/deterministic/TF32off;
finite loss before backward and all present finite gradients before step.
No AMP/compile, seed/window/threshold search or output-based model removal.

Two expanding OOF fits plus final per model: fit61..427/score429..610,
fit61..609/score611..799, final fit61..799. Six actual fits total; five outputs
are ONE Ridge solve, not five extra allocations. OOF folds report separately
with unavailable dates visible, no tuning or selection.

Joint action selects greatest predicted10bps net return strictly>0, otherwise
cash. Cash wins zero ties; fixed lexical expert ties. Participation-only uses
the SAME fitted model's blend forecast>0 to choose blend, otherwise cash; no
extra fits. Freeze ALL39 forecasts/actions before DEV payoffs, then replay the
SAME actions at5/10(primary)/20bps. Missing selected DEV payoff is unavailable,
never cash or a dropped date. Four learned policies + five fixed experts +
equal-weight cohort + cash =33 full-view cost cells. Three13-date views remain
descriptive, no budget/sample multiplier or subperiod pass waiver.

Kill unmatched replay, primary growth<=0 or primary utility<=ANY fixed expert,
equal weight or cash. Joint value separately requires beating its own
participation-only arm; passing the fixed screen alone cannot prove selection
value. Any survivor needs a fresh non-promoting follow-up, never automatic
Paper qualification, alpha, model profitability or broker net-PnL claims.

## Parallel Ownership And Runtime

Engine owns the pure context/basket/label/action/multioutput-Ridge kernel. Infra
owns the fixed Torch model. Data attests separate inputs and the simplified
consumer: one exact metadata preparation, native compact OLD decode, ordered
CURRENT decode, all original frozen bindings hash-checked before/after. Profile
load/geometry separately; do not claim physical decode counts or raw-history
qualification from selected bars. Parent integrates/releases/freezes exact
science/source/custody; invoke independent Validation only on completed frozen
outputs. Execution's OC replay is ideal fractional/dailyflat/cost stress, NOT
actual latency, whole-share fills, fees, settlement or broker parity.

One600s family including audit/load/one fixed64-update synthetic CUDA timing,
all six fits and replay;110s bounded cleanup. Probe retains no weights and
cannot refund old compute. CPU smoke first, no actual market-label fit in smoke.
Use existing image d6b43213.../Python3.12.14/Torch2.7.0+cu128, networknone/
readonly inputs/no credentials and safe own NPZ onD:. One canonical GPU lease;
Execution inference/reliability preempts at a safe checkpoint. No dummy training
or memory/utilization KPI. Preserve Goal31 exhausted family and all used bytes.

## Predecessor And Independent Execution

Goal33 bounded run is CLOSED:9fits30cells/three fixed-screen rejections,
worker227.687s/parent231.679s; native cached30-cell replay exactly matches94.00s.
Independent validation is INCOMPLETE: host prefix-scaler and cached-economic
mismatches remain, final native attempt exhausted180s without a verdict.
Closure/custody3456fe65... explicitly preserve that limitation; no fourth retry,
model/scaler equivalence, independent validated comparison or Paper promotion.
Root D:/thericher-v2/model-artifacts/research/
kis-pooled-rule-fusion-forward-development-v1-failure-accounting-r2.

Keep Oct9 22:45KST/13:45UTC portfolio-control-20261009-v1/job2b20f908... and
23:05KST one-shot follow-up unchanged, original shared10% basis/SPY/TLT/GLD/QQQ
custody. No manual invoke/substitute/reset/schedule expansion or foreground wait.
Future submit/fill/closure remain not_observed. Dashboard127.0.0.1:8787 is a
retained reference, not current owned net profit.

## Completion And Continue

Truthful bounded comparison/rejected/input-unavailable/runtime-failed outcome,
exact source/input/output bindings and cached replay. Independent scope/failure
must be explicit; do not prolong rejected families with repeated equivalence
attempts or call failed validation successful. Fix a concrete defect in fresh
bytes only; no rescue fits or tolerance waiver. Continue independent packages.
Claude public-only falsification challengeb66abae8... returned review_unavailable,
not agreement; retained external receipt, no authentication wait.

Changed-path serial, one clean8-worker authority for integrated shared code,
Ruff and default/research/accounting sample-env Compose. Latest13734pass/
22skip/35warnings/337.16s/helper0 covers57e28af; do not repeat it per handoff.
Verify/commit/push owned changes, refresh changed stateboards/HANDOFF/RUNBOOK,
replace this file with exactly one material next company objective and continue.

M=D:/market_data; A=D:/thericher-v2/model-artifacts (/app/model_artifacts).
Preserve D15%floor. Private/no-cost KIS Paper standing approved; never read/route
KIS_LIVE_*, enable real money/pay/accept unclear rights/expose publicly/replace
major runtime without operator authority. Never output credentials/account/order
IDs, raw prices/amounts/broker bodies/private state or market rows.
