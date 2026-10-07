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

## Current Research State (2026-10-07 KST)

`firstrate-forward-risk-baseline-development-v1` completed two actual CPU fits
in21.23s, with159/160 positive TRAIN and89/90 comparison observations per ETF.
Fixed160/1/90 scheduled split,45/45 halves before exclusions, L2=1 log Ridge,
TRAIN-only scaling, own/peer past119-return variance and two fixed controls.
Normalized QLIKE order is Ridge / own-past60/119 / same-TRAIN mean:

| ETF | All90 | First45 | Last45 |
| --- | --- | --- | --- |
| QQQ | 0.109475 / 0.230770 / 0.322889 | 0.104075 / 0.192624 / 0.292449 | 0.114754 / 0.268067 / 0.352653 |
| SPY | 0.213841 / 0.193768 / 0.527002 | 0.239396 / 0.183327 / 0.570821 | 0.188854 / 0.203976 / 0.484157 |

Overall incremental-risk premise REJECTED: SPY loses to past variance in all90
and first45, including every shared-date deletion there. QQQ's better values
do not permit ETF selection, retuning, a same-data rescue or Paper input.
Eligible halves44/45 and45/45; one early-close target shortfall in each split,
no zero targets or forecast clipping/flooring.611 causal mutation checks pass.
Independent ALL-RO replay matches exact model/scalers/cohort/forecasts/losses
in20.571s with ZERO refits.162 focused serial tests pass; source review's two
result-read/registry-recovery findings are fixed and independently rechecked.
Root `D:\thericher-v2\model-artifacts\research\firstrate-forward-risk-baseline-development-20261007-v1`;
contract `sha256:dbccc9e43f034e1c8fba12d4d28808279210629d3fcc6cae1d5fcfa9866e420d`;
result `sha256:d653fe8ef6cf4a921c89ddb0cfac1709a9f866b978a267bdaf48e5745ff3f0da`;
canonical numeric-model payload `sha256:e8d141162c8e7e7bfa1f18edd277c2a5db2b19b3210f377fcd2196a6b2e327c1`.
Numeric models and16 exact frozen code copies remain outside Git; replay uses
the pinned846a900b CPU image/networknone/2CPU/2GiB/120s bound. No GPU, sealed
allocation, broker call, returns, PnL or promotion. Same revised/seen source,
source clocks/actions/finality/PIT and conditional complete-case limits remain.
Claude supplied-result challenge exited1/review_unavailable, NOT agreement:
`D:\thericher-v2\model-artifacts\research\source-discovery\claude-forward-risk-result-20261007-v1.json`.
Next product priority is Execution's actual-fill accounting, independent of
research scores. No genuinely ready new frozen predictive/GPU campaign exists;
closed risk/return/allocation/foundation families stay closed.
GPU capability is freshly verified in existing research image d6b43213:
RTX4090/Torch2.7.0+cu128 CUDA matrix operation succeeds/networknone/no fits.
Bounded Engine preparation for one distinct retained-data GPU hypothesis runs
in parallel with accounting, rather than after Execution's external due time.
It is not yet a frozen campaign, appointment or training result.

## Prior Target And Input Preparation

Forward-risk target/input preparation is complete, revised/seen development
only, not a predictive campaign or return/allocation rescue. The new pure
`forward_variance_smoke.py` and `run_firstrate_forward_variance_smoke.py` reuse
`intraday_variance_targets.py`, `paired_completed_context.py`, the verified
FirstRate loader/normalization contract and the retained scheduled-date hash.
The finite contract froze/fsynced BEFORE source-value parsing: one decision
per scheduled date at min(open+150min, close-10min), own/peer past120 completed
M1 inputs, one60-minute squared adjacent log-OPEN target from decision+1min,
61 complete bars/final bar END availability at decision+62min. Past inputs and
each symbol's forward support are separate; no whole-session/future mask.
Actual source counts QQQ210,482/SPY207,824, regular M1 counts97,530/97,526.
All251 scheduled paired inputs are available; each ETF has249 available targets
and two session-horizon shortfalls (2022-11-25/2023-07-03 early closes).
June5 source gaps remain visible in source counts, not a global input exclusion.
502 prefix/future-removal,6 future-value/completion,8 target-only and16 forward
missing/incomplete checks pass; exact ALL-RO replay matches both commitments.
40 new synthetic tests plus target/context coverage yield227 passes/no skips
in1.91s/two helper workers; Ruff passes. Initial import-guard failure exposed the
legacy calendar helper's execution imports; the runner instead calls the same
pinned NYSE5.4.0 API directly and verifies the exact retained date-set hash.
Offline2CPU/2GiB/RO-source containers exited under a120-second hard bound;
focused pytest ownership is released. No fit/GPU/selection/holdout, raw values,
weights, predictive metrics, broker call, performance or Paper claim.
Successful test child cleaned; initial failed `C:\trpy\runs\r-8ed1a30b` remains
inactive after policy-rejected manual cleanup, with no lease/worker; helper
mutex is confirmed available. This retained sibling is not an authority hold.
Root `D:\thericher-v2\model-artifacts\research\firstrate-forward-variance-target-input-smoke-20261006-v1`;
contract `sha256:ae8bffb356c82d4a99f885ce17aecf7e1b14ac12822e317efcaac95b183a2e11`;
result `sha256:d7d3761265f6484b52db5e00c8f1a26fee7ba24e853da4e67bdc634179832ce8`.
Revised/seen source clocks, actions, finality and historical availability remain
unqualified; physical parsing is not target-isolated, and251 shared blocks are
not502 independent observations. Recovery complete; no research worker remains.
Its subsequent forward-risk predictive comparison is completed/rejected above;
do not repeat this preparation or its two-fit recipe.
Preserve prior seen-source trials and all three closed October5 families; no
retuning, independent-data relabeling or automatic Paper qualification.

First30-to-closing29 is closed/non_promoting_completed, family/root
`D:\thericher-v2\model-artifacts\research\firstrate-first30-closing29-development-20261005-v1`.
Primary long/flat sign is prior scheduled final M1 CLOSE to current completed
first30 CLOSE; equality flat, no stale predecessor or whole-day future mask.
Each ETF/fold starts separate NAV1; entry close-30 OPEN/exit close-1 OPEN,
including early closes, zero overnight/short/leverage. This29-minute variant
is not Gao et al.'s1993-2013 SPY result or the older21-day signed KIS contract.
125 TRAIN signs per ETF freeze an exposure-only control, no TRAIN payoffs/fits.
Seen April-June/July-September observations QQQ62/63/SPY61/63; SPY has one
opening-input shortfall, no target censoring. Candidate active counts31/36/33/41.
Five policies/three1/3/5bps-side costs/four groups yield60 cells, zero GPU/weights.
Stress candidate NAV returns QQQ-0.039516104304/-0.061019227296 and
SPY-0.032618756537/-0.058961257859 lose fixed exposure controls in every group.
Frozen net/increment/day-deletion kills apply; no best-cost/ETF/window rescue,
independent holdout, original-paper rejection or Paper input.
Source/contract/action/ordered execution/NAV/terminal-ledger ALL-RO replay passes.
Pre-payoff commitment flushes/fsyncs; rows are parsed in memory, not physically
target-isolated.47 pinned synthetic checks include early-close OPEN/CLOSE/
drawdown/censoring/increment/day-deletion tests;98 related tests pass8.91s.
Independent final review confirms four binding/smoke P2s fixed/no new P1/P2.
Worker4.940231s/2CPU/2GiB/network none/120s bound;11 critical code pins are
externally snapshotted, not a complete dependency bundle. No child remains.
Contract `sha256:c026e893d47478c56d924e05d477f377eca21bd3b54e4ea9b2ecdf2835596853`;
result `sha256:ed5c934debdb54699d3f3f4b098c00d16ab51b71649e2bd0770bb5928ee2721a`;
commitment `sha256:23a60f4260bfab3d6ee2045ca39dc45e32d1b809a735ed76bef741ab747d6a0f`.
Primary university source re-retrieved through web; publisher403 is not a source
byte hash. Copyright is reference-only, no manuscript/code/weight adoption:
https://profiles.wustl.edu/en/publications/market-intraday-momentum/.
Claude invocation exit1/uncategorized remains review_unavailable, not agreement:
`D:\thericher-v2\model-artifacts\research\source-discovery\claude-first30-closing29-drift-20261005.json`.
Revised/seen source clocks/actions/finality/PIT, cash interest, risk matching,
fees-only endpoint fills and absent Execution parity remain limitations.

Joint daily-flat QQQ/SPY/cash allocation is also closed/non_promoting_completed,
family `firstrate-paired-allocation-development-20261005-v1`, actual root
`D:\thericher-v2\model-artifacts\research\firstrate-paired-allocation-development-20261005-v2`.
One shared300-second budget covered three CUDA fits: learned constant allocation
and linear softmax policies with completed30/120-minute M1 inputs at open+150min.
160 scheduled TRAIN days/one embargo/90 seen comparison days; no future full-day
mask. Entry is next M1 OPEN, exit last session M1 OPEN; actual notional fees and
one shared fractional NAV, flat each day, not independently funded sleeves.
All comparison weights were durably committed before payoff calculation.
Primary120 stress6bps-side NAV return is-0.13738611929734257, versus constant
-0.02772973189409822/equal-weight-0.13026533487740266. Net/increment/chronological-
half/day-deletion kills apply.30-minute ablation also loses; no best-window
selection, threshold/cost rescue, independent holdout or Paper input.
Worker10.965463s/Torch peak68,181,504 bytes; container/lock reaped. Three numeric-
only model JSONs retain coefficients and TRAIN scalers outside Git. ALL-RO CPU
reconstructs exact inference/actions/21 fee cells and20 future-feature checks;
weights/NAV tolerances1e-10. Source rows are loaded in memory: the commitment's
target-read flag means no comparison payoff calculation, not no physical parsing.
Contract `sha256:561478fd4bb1a033148830cea01b6386f772ea2007db02950f6ca54d8628bf13`;
result `sha256:0b1f9f2c611f9766c228c0af6b7722bb8f08d0f296fbe2a83f02c89f8b71da97`;
action `sha256:db7be83242ce08c5171a6bd60d9f963186ee898c2c5b9205b43db60872a17525`.
Fourteen critical code pins are externally snapshotted; remaining imports use
the verified repository/runtime, not a claim that14 files are a full dependency bundle.
Original v1 mount error failed before data targets/fits; original source, start
marker, contract12146043 and failed registry outcome remain unchanged. v2 fixes
only canonical-root mapping and binds CPU smoke to its contract, no model retuning.
Registry trial1 is identity-scoped after source-path correction, not a reset of
known prior trials. New helper88 tests plus integrated226/no skips pass locally
3.51s and pinned Torch2.7+cu1286.54s; independent review's two binding defects
are fixed. This isolated package does not claim another full-suite authority.
DIN/DeepDow source review is mechanism-only, no dependency/model adoption:
`D:\thericher-v2\model-artifacts\research\source-discovery\portfolio-objective-source-review-20261005.json`.
New Claude exit1/uncategorized remains review_unavailable, not agreement:
`D:\thericher-v2\model-artifacts\research\source-discovery\claude-paired-allocation-drift-20261005.json`.

`kis-paired-lag-development-20261005-v1` is closed/non_promoting_completed.
Fifty separate dated source pins/25 shared sessions froze before targets:
12 TRAIN blocks through September15, September16 embargo,12 seen comparison
blocks September17-October2. M5/60-minute context uses own4+peer4 channels;
next-M1-OPEN to OPEN60 minutes later payoff.1,296 overlapping TRAIN windows are
12 shared blocks, not IID examples;96 decisions are12 blocks, not24 ETF days.
Eight synthetic CPU smoke fits preceded four actual fits: own/paired Ridge CPU,
paired LSTM/compact-attention CUDA,128 epochs/final epoch only.48 cost cells;
no threshold, cost, architecture or ETF rescue. Attention stress mean net
`-1.605736673358` unit bps/decision loses own Ridge by`-0.457462665101`;
own/paired Ridge, LSTM and Attention all have negative stress means per ETF.
Nonpositive net/increment, ETF dependence and shared-day dependence kills apply.
Primary Attention trade counts QQQ7/SPY4; this is not NAV or settled broker PnL.
Worker12.249452s/Torch peak121,579,520 bytes; canonical GPU lock/container reaped.
90 pinned Torch2.7+cu128 CPU tests/no skips22.08s and exact ALL-RO48-cell
source/cohort/actions/cost/kills readback pass. Learned inference is unretained
and not independently reconstructed. No weights, winner, ensemble, holdout,
Paper input or runtime change. Verified-loader reconstruction fixes the sealed
catalog audit fault; importing the runner no longer mutates CUBLAS environment.
Root `D:\thericher-v2\model-artifacts\research\kis-paired-lag-development-20261005-v1`;
contract `sha256:540f72fa1cfb7c23637352cfefa654c78978647654a0a84bcf6db0444474bce8`;
CPU `sha256:da74ba32c7864deb00a0faf18a6a0b75c7028f8c385a667e287c03b1e8b1f333`;
CUDA `sha256:68e4fce0d5f1bbbf8cdd53d101e2fde96baf82a8d8e937401caeeda745453a7d`.
All38 frozen code pins also match the external
`D:\thericher-v2\model-artifacts\research\kis-paired-lag-frozen-source-20261005` snapshot.
Initial metadata registration lacked the ledger writer mount; exact contract
verification/idempotent registration recovered before targets/fits, with no
rewritten precommit. Recovery evidence is
`D:\thericher-v2\model-artifacts\research\kis-paired-lag-freeze-recovery-20261005.json`.

DeltaLag, Deep Momentum Networks and dynamic-cost trading were independently
re-retrieved as mechanism references, not financial benchmarks or code adoption.
DeltaLag is daily broad equities, the other two are futures/different costs;
ordinary temporal attention here is not their reproduction. Source-only receipt:
`D:\thericher-v2\model-artifacts\research\source-discovery\cross-asset-cost-20261005-engine-retrieval.json`,
SHA256 `28bfa6bffe3b0caaa6c3ce72b4a0342b617d59573023f95a6600f51d3db81934`.
The actual new Claude invocation failed exit1/cause uncategorized; this is
review_unavailable, not agreement or an inferred quota. Its exact source-safe
receipt is `D:\thericher-v2\model-artifacts\research\source-discovery\claude-paired-lag-drift-20261005.json`.
Broader FirstRate readiness is now checked:251 scheduled2022-23 dates/250 shared
complete sessions,160 TRAIN-session metadata proposal with one embargo/90 later
scheduled dates. All were previously seen; old campaigns/pins are not reset.
The small source-independent `paired_completed_context.py` now constructs exact
completed own/peer inputs for M1/M5/M10/H1/H3, exposing the latest complete end
and its lag rather than consuming a partial H1/H3 bucket. It validates only
the required past prefix, not later full-session/target availability.
79 focused tests pass1.27s, including early-close/DST/future perturbation and
large-window source shortfall before grid allocation; Ruff passes.
Eight input-only cells include30/120 M1,12/60 M5,12 M10,one H1,one/two H3 bars.
Actual251 scheduled dates yield2,008 paired cases:1,998 available/10 exact input
shortfalls; early closes and June5 gaps remain visible.78 prefix/future-mutation
checks and exact ALL-RO commitment reproduction pass. Zero targets/fits/GPU/
weights/costs/performance or Paper claims. Normalized source clocks, finality,
corporate actions and historical availability remain assumptions/limitations.
Root `D:\thericher-v2\model-artifacts\research\firstrate-paired-context-input-smoke-20261005`;
precommit `sha256:a6559daab618ef3bdf208574a4da7984a3bc9f28d3d7d27e1229f15c99c18e09`;
result `sha256:802aced4519c43120a2276bfee371b9781ce361e82834f9d0963ff024308bcc6`;
input commitment `sha256:5c3bb2f3cacd9a0babf17efd05e50de108f5bca15b46b1cbaa978a73fb59df1b`.
Six contract-pinned source files are also externally preserved under frozen-source.
Next predictive package must freeze its own distinct hypothesis/target/cost/
compute contract, retaining every prior seen-source trial. Reuse existing
compatible net-utility helpers; no duplicate objective or closed-recipe rescue.

The original FirstRate time-of-day band development recipe is complete and
`recipe_killed`: same fourteen SCHEDULED prior-session prefixes, first strict
semi-hourly upper-band close, next-M5-OPEN long entry/last-M5-OPEN exit, one share.
Both ETFs/two seen chronological folds/1,3,5bps-side costs yield12 cells, zero
fits/GPU/weights/holdout. Each fold has63 scheduled sessions; complete SPY62/63,
QQQ63/63; scored trades SPY23/27, QQQ32/23. At primary3bps-side costs, net unit-bps
SUMS are SPY+395.047943/-291.938855 and QQQ+406.158649/-108.492500. In-fold
matched-time long increments are positive in all four groups, but the two later
net losses trigger the frozen kill. These are not NAV returns, independent
performance, deployable controls or KIS PnL. No threshold/cost/ETF rescue.
All four decision tuples freeze in memory before full-session censoring.
Root `D:\thericher-v2\model-artifacts\research\firstrate-time-of-day-band-development-20261003-v2`;
contract `sha256:b790a6355210997bd3b7dacd198e6ce34692e7f1ef8833f03e152abad378d565`;
summary `sha256:03e24e1664768e3ce16ade1f12eb9229fa8fe7bd6fee6ccd2dc1fcd3bcb95dc5`.
Original v1 worker41.238s/12 cells remains immutable; its archive-write readback
failed. Same-family v2 changes only verification control locks to temporary
scratch, preserving real EmergencyStore parsing/stopped/malformed fail-closed
behavior. Corrected worker39.363s, exact ALL-RO source/action/control/fee replay
passes; all normalized v1/v2 cells/actions agree. No recipe/selection change.
`readback-repair.json` SHA256
`ba18371bef2b420bb40614c4283f1384306249040a162980f6e7233e9f6b7bd5`
links both original pins and retained183a849a source snapshot. Independent final
source review supported-with-limits/no remaining material P1/P2; fees-only,
zero-latency/seen/revised source, censoring and no KIS parity remain limitations.
Final formatting is AST-identical, but does not rewrite the frozen code pin.
Archival replay mounts exact `frozen-study-source.py` over the current study
module, SHA256 `5840e26354cf30e8119c251561bacba1cd8ff831f215455d6a1c688db9ed7d28`;
that exact frozen-source ALL-RO reconstruction also passes. Committed formatting
SHA256 `56275776d297b54dc5bf1c0efe0f395d63a75c4ef900b48449c6b17f7613eec6`.
Final113 mechanism tests include unsafe archive controls; helper100 are separate.

The original time-of-day feature preparation and real-input smoke are complete:
`intraday_noise_band.py` computes fourteen strictly prior sessions' mean
absolute CLOSE/OPEN move at the same elapsed M5 cutoff, anchored to today's
OPEN. Homogeneous complete prefixes, UTC/DST alignment and missingness are
tested; future OHLCV is unread by the helper. No previous-close gap adjustment,
shorting, leverage, entry/exit rule, target or paper reproduction is implied.
100 feature tests pass; parent feature/VWAP group111 passes/one known skip1.88s.
Source `sha256:191bbe38e29b2c5a88d9b83e408527f67e34f4c445336c75bc0f77820db3ba2a`.
Forty September QQQ/SPY metadata pins froze before real feature construction.
Fourteen warmup sessions plus six shared later days/five cutoffs produce60
feature cases,30 per ETF, not twelve independent days. Whole-source and
prefix-only outputs agree; exact RO reconstruction/source/hash verification
passes. Pinned offline2CPU/2GiB/90-second bound,0 targets/fits/GPU/weights;
feature values remain in memory, only their commitment is retained. The first
inline attempt used an absent adapter.inputs attribute before any feature
calculation; its immutable failure remains. Recovery uses the existing verified
catalog resampler, not an invented adapter field.5.816s recovery command and
5.559s RO readback completed; these are command times, not worker timings.
Root `D:\thericher-v2\model-artifacts\research\kis-time-of-day-noise-band-input-smoke-v1`;
contract `sha256:46c34768c21aca0b8f022bc68a9bc002355bda379251c5f79c993b2e36b9606b`;
summary `sha256:053a3e38ee6ce27c91f059d53164c7e1fca2e3a60f78b184696e0669d25e4a6a`.
Custody non_promoting_completed, source/revised/PIT/finality limitations remain.
This prepares a distinct hypothesis; it is not a performance result or Paper input.

The pooled return campaign is complete/non_promoting_completed:
`kis-pooled-patch-return-development-v1`. Forty exact QQQ/NAS and SPY/AMS
dated sources freeze before labels. Ten shared TRAIN days provide960 overlapping
M5/120-minute windows; September17 is embargoed and nine seen comparison days
provide72 decisions. These are10/9 shared blocks, not960 independent examples.
TRAIN-only normalization; next M1 OPEN entry, OPEN30 minutes later exit.
One pooled ridge CPU fit precedes one LSTM16 and one completed-patch16 CUDA
fit, fixed seed107/128 epochs,6bps decision hurdle. Seven fixed policies,
two ETFs and3/4.5/6bps per side form42 cells under one300-second appointment.
Six synthetic CPU smoke fits are separate from the three actual fits.
All three learned policies and TRAIN-mean control emit zero comparison trades.
Patch stress net and increments versus ridge/LSTM are0 unit bps; every frozen
kill applies, including ETF/shared-day deletion. Momentum and always-long lose
after stress costs. No profitable candidate, threshold rescue, selected ensemble,
weights, sealed spend or Paper input. Capacity/feature-exchangeability confounds,
revised/seen data and unobserved PIT/finality remain explicit.
Actions are sealed as an immutable tuple/hash in memory BEFORE comparison
payoffs; there is no separate durable pre-payoff receipt. Exact read-only
source/contract/cohort/action/fee/42-cell replay passes, but unretained learned
inference cannot be independently reconstructed. Pinned Torch2.7.0+cu128,
2CPU/6GiB/network none; canonical GPU lock held through supervisor reaping.
Container exited/lock absent; duration/VRAM peak were not instrumented.
153 focused tests pass locally and in the pinned Docker runtime20.75s/zero
skips; independent source review supported-with-limits/no material P1/P2.
Root `D:\thericher-v2\model-artifacts\research\kis-pooled-patch-return-development-v1`;
contract `sha256:becd4875246e0c601d437b0af9f771dbab37961fa7c4c7631a3e674146b510bf`;
smoke `sha256:2584f7d3756330a8b4d2902c02b46bc0da1a955cf8b0ff5bedfa2319beff3a55`;
CUDA `sha256:80ea4b867b544ddee3b42a88690a512aaba1c45e4d2d49c9bd4715cde5b843a0`.
The metadata reader's optional SPY target leaves QQQ defaults/old contracts
unchanged. Latest8,186-test authority predates this isolated package; focused
verification covers it, not a claim of a repeated full suite.

Closed references below retain exact scoped findings. Statements about an old
unavailable input or a then-pending worker are historical, not current dispatch
facts. Current readiness is in Current Tracks and Active Constraint And Handoff;
immutable family history/custody must never be reset by this projection.

The dated QQQ downside-hurdle CPU campaign is complete, not a winner:
`kis-qqq-dated-downside-development-v1`. Twenty September2-30 sessions bind
exact dated indexes/manifests/raw hashes; ten TRAIN sessions/40 examples,
September17 embargo and nine comparison sessions/36 decisions. Fixed M5
120-minute context/four features/four daily anchors; entry next M1 OPEN,
exit30 minutes later. One fixed quantile0.25 histogram tree and one logistic
fit, six policies/3,4.5,6bps per side produce18 development cells. Four synthetic
smoke fits are separate from the two actual fits. Network-none/2CPU/2GiB,
120-second supervisor; no GPU, new dependency, weights or holdout spend.
The tree emits zero trades, stress mean net0 unit bps: the predeclared
nonpositive_stress_net kill applies. Mean increments versus linear/momentum
are+0.929351784098/+6.029588453068 unit bps, representing avoided losses,
not positive return. No threshold/parameter rescue, ensemble or Paper input.
Exact read-only contract/source/cohort/action/fee/math verification passes;
it cannot independently reconstruct unretained learned inference. One ETF,
correlated small session blocks, revised seen data, assumed fees and unobserved
PIT/provider finality remain limitations. Before actual freeze, independent
review closed480-native/390-regular geometry and missing dated cursor custody
faults; first-creation path regression is also covered.66 focused tests/5.25s
and final independent source review pass. Data's earlier8,092-test authority
predates these isolated repairs and is not their verification claim.
Root `D:\thericher-v2\model-artifacts\research\kis-qqq-dated-downside-development-v1`;
contract `sha256:09f4e730df8dc72f9232c48849eb7b7ef787fd446eceea094ee52e4e6e1aa5aa`;
smoke `sha256:5cb12caa42ac1507900fcc30189770d449508300876dacd0cd0ac4cd1ab8fa85`;
CPU `sha256:e86d393a71691a3493a590275ef5fd6b67927890a609fe942a5f0ced04127ed0`.
Custody non_promoting_completed; child/container exited. Broader dated input
and an independently specified mechanism are preferable to retuning this result.

The small completed-patch, channel-independent Torch encoder preparation is
complete, separate from old architecture IDs/defaults. Shared weights, causal
whole-patch attention and fixed channel aggregation are an architectural probe,
not a full PatchTST reproduction or a pretrained trading model.59 local CPU
tests/2.11s and59 pinned Torch2.7 Docker CPU tests/3.33s pass, zero skips; final
independent source review finds no actionable P1/P2. Pure test dependencies
were mounted RO; no runtime install, GPU or real-market fitting occurred.
Source `sha256:a2b4e1379419cd2d26658b751a4f22e577335cf732eddcf959efe3cef284b9c5`.
Shared-source authority now8,186 passes/22 skips/317.40s/eight workers/clean
helper, Ruff/both Compose pass, including the downside's isolated repairs.
Caller owns completed-bar cutoff/normalization; incomplete patches, invalid
dtype/device/nonfinite input fail. Data's matched SPY adapter proceeds separately.
A later campaign must
freeze its own pooled/transfer hypothesis, context, splits, costs and finite
compute/kill rules before labels/fits; this preparation has no training grant.
Primary papers re-retrieved October3 show complementary directions, not an
architecture winner for our data: arXiv2603.01820v1 benchmarks daily multiasset
futures/feature-gated temporal models; arXiv2606.09420v1 uses CRSP2018-2024
daily stocks and shows constrained net portfolios can erase gross signals.
Neither supplies free compatible intraday data or disclosed adoptable code.
PatchTST arXiv2211.14730/official Apache-2.0 source supports completed patching
and shared channel weights; its generic forecasting gains are not ETF alpha.
No external code/checkpoint/runtime was adopted. Exact source-only receipt:
`D:\thericher-v2\model-artifacts\research\source-discovery\architecture-cost-transfer-20261003.json`,
SHA256 `c5cbdcf78a9d35d0a73e0dbc1632a86d5cbe9d437aa8e2351dc717b114ba93f5`.

The distinct causal four-expert development campaign is complete: linear/LSTM16,
12-month momentum and TRAIN-risk constant; uniform initial weights/fixed rate0.1,
strictly prior completed-month feedback from continuous10bps expert ledgers,
and a separate Decimal50 mixed-policy ledger. Two pooled TRAIN2002-2012 fits,
seed101/128 epochs; six later seen ETF/fold groups, eight policies/three costs
yield144 cells. No monthly reset, whole-period feedback or averaged expert NAV.
Metadata froze before real targets/fits;8.022s synthetic CPU smoke/zero fits
preceded CUDA. Exact RO verification passes; two external numeric NPZs reconstruct
on CPU. Independent validation recomputes25 source pins/144 unique cells/48
cost-invariant action groups/144 fee identities,18 cash and18 always-long controls.
Primary10bps online-minus-fixed-blend mean NAV delta+0.000390539797,
kill_applied=false. It loses TRAIN-risk constant by0.064010583668 NAV units;
leave-QQQ-out delta-0.000781313792. This fragile seen-data gain is not annual
return, alpha, a winner, BOA reproduction, sealed evaluation or Paper input.
Do not retune the rate/experts or rewrite the predeclared kill from these outcomes.
Root `D:\thericher-v2\model-artifacts\research\tiingo-causal-expert-mixture-development-v1`;
precommit `sha256:b900a1bb6c37633a857ed1e4c7b9d53b0b391b5f93056843820477e0f51ce944`;
CPU `sha256:ff89896f723fe1320052d52535c2d75856f2e5306f70fa3e5b7bfe73bccb6640`;
CUDA `sha256:f90858cbaa644bfaffe56e151fc50cd231ffda68864913aff57f950518889333`.
Actual metadata duration/peak and weight custody belong to Research Steward.
73 new campaign plus83 helper serial tests pass; final integration authority
8,014 passes/22 skips/326.01s/eight workers/clean helper, Ruff/both Compose pass.

The pure causal online-mixture preparation is implemented: independent convex
target projection and exponential completed-loss/Hedge-style weight updates,
strictly prior UTC feedback plus an advancing caller-owned watermark. Finite
float64/simplex checks and numerical extremes are tested; inputs are unchanged
and output weights are read-only.83 focused tests/0.23s and Ruff pass.
Source `sha256:0d805c411debb530e7e2913de3c0a8056207634bf6f66598b6a4f47b51fdf785`.
The helper alone is not BOA reproduction, a fitted ensemble or a performance
result; its distinct campaign above now has actual development output. The
distinct hypothesis is causal adaptation versus
the existing static vote/utility tree. Next preparation must align genuinely
later-OOS expert decisions, use completed prior-month continuous-ledger losses,
and give the mixed target its own cost/turnover ledger. Never average expert
NAVs/fees or liquidate/reset each month to fabricate feedback. A new contract
must freeze rate/experts/state-update timing before outcomes. Old parent code
pins remain immutable; current replay changes cannot silently bypass them.

Latest source-derived fixed-band package completed. Existing Decimal50 replay
now optionally clamps actual predecision OPEN exposure into center+/-0.1,
clipped[0,1]. Default replay is unchanged; terminal CLOSE always liquidates.
Finite Decimal callback validation closes an independent-review defect where
bool could silently become0/100-percent allocation.112 focused tests/2.88s,
Ruff and final source review pass; no new runtime or broker path.
One metadata-frozen CPU study carries capital across months within each fold,
not across folds. Existing TRAIN2001-2012 variance/risk calibration, three ETFs,
two seen comparison periods, six policies and0/2.5/5/10bps form144 cells.
Actual pinned offline1CPU/2GiB/180s Docker run completed in1.799s worker time;
zero predictive fits, weights, GPU allocation or holdout spend. Exact read-only
source/contract/summary/fee/center-hash/paired-math readback passes.
Mean stress band-minus-direct NAV delta-0.104884986156, turnover saving
6.384099408956 initial-NAV units, minimum leave-one-ETF-out delta-0.144494762197:
the predeclared primary kill applies. These are descriptive fold NAV-unit
differences, not annual returns or alpha. Band alters exposure as well as fees;
controls are not exposure-matched. No winner, tuning rescue or Paper input.
Root `D:\thericher-v2\model-artifacts\research\tiingo-fixed-band-continuous-development-v1`;
contract `sha256:b9bc2842e5304e5c4149554ecad968868e40a061c60a997adb60dece194478e9`;
summary `sha256:6300b535e803366fe576f95c78db780461f032ea48e4a07bd7dcc69cb9ee10b0`.
Custody non_promoting_completed; worker/container exited, no active appointment.

Two public proposals were independently re-retrieved, without code adoption:
No-Transaction Band option hedging (arXiv2103.01775, official MIT repository),
and expert portfolio aggregation (arXiv2111.15365v4, code rights not_disclosed).
The former's simulated30-day derivatives and omitted terminal cost do not
establish ETF alpha; the latter's US-stock1987-2016 tests are not evidence for
our post-cost hierarchical gate. Exact source-safe receipt:
`D:\thericher-v2\model-artifacts\research\source-discovery\cost-aware-policy-20261003.json`,
SHA256 `64776177f42e1bbae15a6d4a3f36400929fa9f9fae06fee02178a83867dfa070`.
Source-only feasibility found a distinct online mechanism; the pure helper
above is complete and the separately frozen development campaign has run.
Neither source nor campaign turns rejected studies into a profitable/Paper claim.

Completed one finite equal-elapsed M1/M5 CUDA development experiment.
Context30/120 minutes means M1
30/120 versus M5 six/24 bars, common cutoff/entry/exit support. Ten TRAIN
sessions, July7 purge, five descriptive comparison sessions; latest five are
excluded from THIS package, not globally unseen data. Rule/logistic/TCN and
cash/long form one120-cell budget, not independent per-cell experiments.
Five synchronized session blocks give32 sign patterns; the fraction is
descriptive, not a significance claim or independent ETF/day count. Full-context
TCN kernels differ in parameter capacity, so a difference cannot be attributed
solely to resolution. No holdout, selected model or Paper input follows.
Independent review found and closed a date-relabeling TRAIN-anchor bypass.
Main38 synthetic tests/3.07s and Ruff pass; final source
`sha256:5adb809155c2f63011e2d9f753d5642882f9d9af8dd04219db17c62dd8b1fc17`.
The temporary source invocation is closed; Orchestrator owns the integration.
Actual CPU geometry smoke prepares480 windows/5,850 selected M1 bars per symbol
and all four TRAIN-only normalization geometries in3.144s. No targets/fits/GPU.
Root `D:\thericher-v2\model-artifacts\research\kis-equal-minute-resolution-input-smoke-r2`;
contract `sha256:f919156fbdc14dcbe0f0087b905ff517a8439f94508f2d8c67b0ac51ac3a4ec6`;
outcome `sha256:ea69cdbe7903575059a68ba09f9af4969ebe0b1395df3dc2e7b05d7065d21049`.
The failed v1 is retained: parent's SPY cache selector NAS was wrong, not absent
SPY data. r2 explicitly pins QQQ/NAS and SPY/AMS under the same unchanged index
`sha256:f816b940c3419caec4bdd1595b79615e6895782dad012edc12785aef6f05a53f`.
The actual metadata freeze initially failed before targets/fits because the
reused artifact reader's2MiB cap was smaller than the4,232,279-byte index.
Only this index read now has a measured8MiB cap; original identity/pin checks
remain.61 launcher tests plus38 helper tests pass in10.26s; Ruff/independent
source review pass. Exact launcher SHA256
`8aecabc966a508cc8db26982d21e67c1d610124eac32e4210f4e0fe3a1b3816d`.

Metadata-only contract froze before real labels, then7.652s pinned-Docker
synthetic CPU smoke preceded one10.753s CUDA appointment. Four pooled80-window
logistic fits and four full-context TCN16 fits at8epochs produced120 cells,
with20 comparison decisions per symbol. No model weights/predictions retained.
At stress6bps per side, all eight momentum cells lose to cash; linear is cash
in all eight; TCN has one positive cell but pooled mean net-unit payoff is
-4.7133bps. TCN pooled M1 means at30/120-minute context are-4.4792/-1.1026bps,
versus M5-4.1095/-9.1619bps. Primary M1 stress mean is negative, so the frozen
nonpositive_stress_net kill applies despite a positive average resolution delta.
No favorable cell is selected;32-pattern family fraction0.125 is descriptive,
not a p-value. These are equal-unit30-minute payoff proxies, not portfolio NAV,
actual fees, settled cash or broker PnL. Five seen/revised session blocks are
not independent evaluation or provider-final/PIT data.

Root `D:\thericher-v2\model-artifacts\research\kis-equal-minute-resolution-development-v1`;
contract `sha256:ad8f9dbf89e8d7543cd6f0e092c335db2278cf3039b9b86a3550f20d5f7956fe`;
CPU summary `sha256:e7fba28f24e5f36842564a179979c293d9274e3fc4ce09c2f6b9b43a500f8db2`;
CUDA summary `sha256:3d0b2b42c94cd28b5316065708b0059dab3ff7153ba59e44d9d42023edea4ad5`.
Exact source/contract/worker-summary/120-cell read-only Docker verification
passes. Registry non_promoting_completed, container exited/GPU lock absent.
Do not run an outcome-informed tuning rescue. Current Data replacement repair
may change its source pin after this readback; retained contract/result pins
remain the evidence, not a claim that later mutable source still matches.

Primary sources re-retrieved October3: TCN causal convolution/context design,
https://arxiv.org/abs/1803.01271; joint trend/sizing and turnover-aware loss,
https://arxiv.org/abs/1904.04912; regime/turnover-aware portfolio design,
https://arxiv.org/abs/2601.05975 and https://github.com/kieranjwood/deepm.
These are mechanism references, not US-ETF profit evidence or framework import.
The futures/universe/data requirements do not match this small ETF panel.
Official https://github.com/google-research/timesfm still distinguishes
Apache2.0 weights through2.5 from3.0 non-commercial/non-production weights.
Keep the already-used2.5 checkpoint; no3.0 rights acceptance or runtime adoption.

Completed frozen-policy August/September readback on one new adjusted vintage:
zero fits/new weights,12 learned monthly actions,126 cells,36 matched-exposure
identity checks,36 forwards/171 Decimal replays. Original TRAIN risk constants
reproduce all six parent hashes; no recalibration on the new months. Main86
synthetic tests and independent86-test review pass; actual pinned offline CPU
run completed in8.641s including Docker startup. Separate read-only exact
contract/result/weight/code verification passes. No GPU was needed for this
small inference-only job; existing models/artifacts remain unchanged.
At10bps per side, both models beat cash5/6 and their own TRAIN-risk constant1/6;
both beat buy/hold1/6 (IWM September). Linear/LSTM IWM September NAV is
0.971190369182/0.953662940506: losses, not a profitable candidate. Each single
monthly action has identical exposure/turnover/cost to its matched constant;
these identities are integrity checks, not predictive evidence. Two revised,
non-PIT months remain developmental, not independent holdout/selection/Paper.
Root `D:\thericher-v2\model-artifacts\research\tiingo-monthly-frozen-policy-aug-sep-2026-v1`.
Contract `sha256:e0bd3c78321cc4ae7e6b1126692c9c8381d80b41f55d42d48f28c970fc25bd37`;
summary `sha256:a17b149862861fac6f0653e64296c5a5fed70fbb8709d0bd23708b6c2b00a4a3`.
Worker/container exited; no retry, extra training or tuning rescue follows.

Current implementation package: `adjusted_monthly_policy_inputs.py` separates
252 past signed returns (253 scheduled closes ending before monthly OPEN)
from realized gap/daily adjusted-close payoff marks. It requires a complete
calendar-bracketed month, not next month's source OPEN. The new differentiable
NAV math mirrors the unchanged Decimal monthly ledger, including overnight
carry, post-fee target solving, ragged daily marks and final CLOSE liquidation.
109 synthetic tests pass, including real CPU Torch optimizer/reconstruction,
ambient Decimal-context invariance and gradient checks. Independent review also
ran30 randomized Decimal-ledger and90 finite-difference checks; its context-
precision finding was fixed before any campaign freeze. No actual training
or GPU appointment follows from these helper tests alone.

Completed `tiingo-adjusted-monthly-net-utility-development-v1`: two pooled
shared linear/LSTM16 fits, complete2002-2012 months, one252-return window,
fixed128 epochs/seed101, TRAIN10bps per side, final epoch only.132 TRAIN months
per ETF;84/79 EVAL months across2013-2019/2020-July2026. Seven policies at
2.5/5/10bps produced126 cells, without selecting costs/models/epochs.
Pinned Docker CPU smoke preceded actual CUDA fitting; RTX4090/Torch2.7.0+cu128,
2 CPU/6GiB/network none/900s supervisor,81.300s reservation-to-summary.
Peak262,698,496 bytes against23,030,923,264 available-VRAM budget. Numeric final
NPZ weights reconstruct on CPU; exact contract/source/weight/result readback
passes in the same pinned image without GPU. Worker/container exited and the
canonical GPU lock is absent.49 focused synthetic tests pass, no skips.

At10bps per side, normalized starting NAV1 gives:

| Symbol / period | Linear NAV | LSTM NAV | Linear own-risk NAV | LSTM own-risk NAV | Buy/hold NAV |
| --- | ---: | ---: | ---: | ---: | ---: |
| SPY2013-2019 |1.7212|1.5265|1.7318|1.7093|2.5414|
| SPY2020-Jul2026 |1.5778|1.4314|1.7481|1.7257|2.5295|
| QQQ2013-2019 |1.9220|1.7900|2.1023|2.0657|3.4257|
| QQQ2020-Jul2026 |1.9366|1.5419|2.1042|2.0687|3.3311|
| IWM2013-2019 |1.6795|1.4345|1.6518|1.5984|2.1066|
| IWM2020-Jul2026 |1.3698|1.2042|1.5725|1.5307|1.8881|

Both beat zero-interest cash6/6 and trail buy/hold6/6. Linear beats its own
TRAIN-risk constant1/6, LSTM0/6;85/80 monthly trades versus two for buy/hold.
Positive development NAV is not alpha, an independently evaluated portfolio,
or actual PnL. The strongest risk-control test does not support selecting
either learned policy. Revised/non-PIT seen data, correlated surviving ETFs,
provider-adjusted marks, assumed OPEN availability and no broker parity remain.
No rerun, tuning rescue, holdout, ensemble selection or Paper replacement.
DeePM is a turnover-aware concept reference, not a Sharpe/SoftMin replication.

Root `D:\thericher-v2\model-artifacts\research\tiingo-adjusted-monthly-net-utility-development-v1`.
Contract `sha256:e3499c501a0c494b3766cb868385780ab6a478e9084e03dfcc5469956a1c1941`;
summary `sha256:ccbece56af83c34c9b7df0563172ff89e38490904372b0824b0104fc123f483c`.
Final linear/LSTM weight hashes:
`sha256:599cbbd75c9a37a0fead6c2635aae5d394cb9ad1b6de92744082d6b867c43084` /
`sha256:3f540bb76f5eb2f9ce566f33a9cbff7a3641c296d542e2edb5ad9b5d36012df9`.
Registry non_promoting_completed. Prior frozen families remain unchanged.

Completed `chronos2-tiingo-return-group-development-v1`: official120M Chronos-2,
same immutable Tiingo input/payoff and128 past signed intraday returns as the
TimesFM reference below. Single-series, same-origin SPY/QQQ/IWM attention and
duplicate-self placebo were frozen before inference. No group contains a later
forecast origin. Fixed >20bps long/flat decisions;5/10/20bps round-trip accounting.
145 origins,1,305 scored forecasts,126 cells; duplicate-self makes2,175 native
output rows across725 calls. All72 parent controls/cohorts/naive metrics match.

RTX4090 completed in30.163s from attempt reservation to summary (not container
startup). Peak allocation487,938,048 bytes with23,030,923,264-byte VRAM budget.
The existing Torch2.7.0+cu128 image was unchanged;2 CPU/6GiB/900s supervisor,
network none, read-only source/data, canonical GPU lock released. One real-weight
CPU synthetic smoke took5.352s. No fitting, fine-tuning, selected weights,
retained predictions, sealed holdout, broker calls or Paper replacement.

| Symbol / period | Targets | Isolated20bps mean / trades | Trio20bps mean / trades | Duplicate20bps mean / trades |
| --- | ---: | ---: | ---: | ---: |
| SPY Jan-Mar |61|0 /0|0 /0|0 /0|
| SPY Apr-Jul |84|0 /0|+0.5253 /2|0 /0|
| QQQ Jan-Mar |61|-0.3306 /1|-0.3306 /1|-0.3306 /1|
| QQQ Apr-Jul |84|-7.0231 /19|-5.0106 /17|-7.0231 /19|
| IWM Jan-Mar |61|0 /0|+1.0881 /2|0 /0|
| IWM Apr-Jul |84|-1.8292 /4|-4.8339 /11|-1.8292 /4|

These are mean analytical net bps per observed session, including flat days,
not NAV, broker parity or realized PnL. Trio beats zero-return MSE in1/6 groups;
isolated and duplicate do so in0/6. The duplicate placebo's identical accounting
does not prove identical underlying forecasts. Mixed benefits and two-trade
positives do not select a model, symbol, ensemble or threshold. Keep revised
seen-data, correlated ETF/context, unknown corpus and assumed availability limits.

Official Apache-2.0 model checkpoint95a9710 is dated October30 2025, before all
2026 targets. Config/weight SHA256s are checked at load, direct safetensors and
constructors only; no remote code/Hub lookup. Model root:
`D:\thericher-v2\model-artifacts\foundation-models\chronos-2\95a9710e2596287d08352589f42634fa5abdf0a7`.
Source/runtime evidence:
`D:\thericher-v2\model-artifacts\research\engine-source-retrieval\chronos2-runtime-20261002-v1\source-retrieval.json`
and `runtime-verification.json` in the same directory. Existing runtime modules
match official source/wheel; no dependency replacement. D: remains40.19% free.
100 adapter and57 harness tests pass, plus52 matched TimesFM tests (209 combined).
Independent source review found no blocker; exact immutable readback passed.
Claude CLI returned review_unavailable/weekly limit, not agreement; no promotion
or authority change relies on it.

Campaign root:
`D:\thericher-v2\model-artifacts\research\chronos2-tiingo-return-group-development-v1`.
Contract `sha256:8bc0cfc2708becd5bd01fc092ddaf332804f28b663fe2a8d5b630ea72de9194b`.
Summary `sha256:6cb6e776293d5e1287e0670c952a0072691983b6678b40adc04a69b4dba5da4b`.
Registry non_promoting_completed; never rerun/retune this closed attempt.

Completed CPU allocation track `tiingo-d1-volatility-allocation-development-v1`:
one22-prior-session inverse-variance daily ETF adaptation, TRAIN2001-2012 median
variance and risk-matched constant,2013-2019/2020-July2026 descriptive comparison.
Each ETF has1,762/1,653 observed targets, no exclusions/censoring.72 cells,
3.949s from reservation to summary,1 CPU/1GiB/600s/networkless supervisor.
At20bps the six vol-managed mean nets range-14.4691 to-18.9007bps; every group
loses to its TRAIN-risk-matched constant by4.8469-7.2387bps. Mean exposure is
0.8092-0.9625; risk-control constants0.5275-0.6472. Lower losses than always-long
do not establish an edge against risk-matched exposure or cash. Daily turnover
cost is charged proportional to actual exposure; no cross-ETF independent-sample
or NAV claim. This daily-flatten adaptation does not reject the original monthly
factor result or a distinct low-turnover overnight holding mechanism.
39 synthetic tests and independent source review pass; immutable readback passes.
Root `D:\thericher-v2\model-artifacts\research\tiingo-d1-volatility-allocation-development-v1`.
Contract `sha256:41129dfbf253a698528cd7b5568f8dfaaf1544a2dc95460a962187af5240cc81`.
Summary `sha256:9963b4dcaaab60392e7cd946dd253188c6da52f4bb44bccf6e2f9b4ef4b41151`.
Registry non_promoting_completed; no fitting, saved weights or Paper input.
Distinct `tiingo-adjusted-monthly-holding-development-v1` is also complete:
22 prior adjusted close-to-close returns, TRAIN2001-2012 median variance;
target stock weight is set monthly from the previous completed close, with
overnight fractional adjusted-unit holding and zero-interest cash. Post-fee
target solving charges actual traded notional, including entry and liquidation,
not a daily round trip. Four policies/three per-side costs2.5/5/10bps,72 cells.
No missing support;1,762/1,653 EVAL sessions and84/79 monthly opportunities.
TRAIN has3,017 sessions/3,014 warm variances per ETF. One CPU/2GiB/network none,
600s supervisor;3.177s reservation-to-summary, not container startup.

At stress10bps per side, normalized starting NAV1 gives:

| Symbol / period | Vol-managed NAV | TRAIN-risk-control NAV | Buy/hold NAV | Vol-managed / buy-hold close drawdown |
| --- | ---: | ---: | ---: | ---: |
| SPY2013-2019 |2.1672|1.7560|2.5414|15.73% /19.34%|
| SPY2020-Jul2026 |1.9912|1.7723|2.5295|20.82% /33.70%|
| QQQ2013-2019 |3.0709|2.0347|3.4257|15.84% /22.79%|
| QQQ2020-Jul2026 |2.6270|2.0386|3.3311|20.42% /35.12%|
| IWM2013-2019 |1.8688|1.6971|2.1066|25.73% /26.80%|
| IWM2020-Jul2026 |1.3564|1.6071|1.8881|32.74% /41.07%|

All six beat zero-interest cash, five beat the TRAIN-risk-matched constant,
and all trail buy/hold while reducing its close-mark drawdown. Managed trades
are24-64 per fold versus buy/hold's two. This is an analytical NAV result,
not a robust edge, selected ETF/model, source-paper replication or actual PnL.
Risk matching is fixed on TRAIN, not equality of EVAL risk; ETF correlation,
revised seen data, provider-adjusted marks, assumed availability/auction access
and omitted cash interest remain material. No additional dividend/split credit.
Independent synthetic ledger/causality review found no blocker;100 current
reader/holding tests pass,2 native-symlink tests skip. Immutable readback passes.
Root `D:\thericher-v2\model-artifacts\research\tiingo-adjusted-monthly-holding-development-v1`.
Contract `sha256:920cdb14688a76d03e17ac58b8e82eeffe95997c6f8f9b1909738c2117f55429`.
Summary `sha256:2b45317b6f25ea2addfdbd303b15cc06cfc849aafcc80d771cff1da31e8b0c07`.
Registry non_promoting_completed; frozen code/attempt must not be retuned.

Distinct `tiingo-adjusted-monthly-momentum-development-v1` is complete:
fixed12-calendar-month positive adjusted-close momentum, equality flat,
monthly overnight holding under the same ledger/cost controls. Jan2013 uses
Dec2012/Dec2011 closes, not a shifted12-session/month selection. TRAIN2002-2012
uses2,769 scored days/132 months with2,782 unique support dates;2001 is warmup
only. EVAL groups have1,775/1,666 support dates and1,762/1,653 scored days;
no missing/invalid support.72 cells, one CPU/2GiB/600s/network none,2.878s
reserved duration. No fitting, parameter search, holdout or GPU appointment.

Stress10bps per-side analytical NAV (initial1):

| Symbol / period | Momentum NAV | TRAIN-risk-control NAV | Buy/hold NAV | Momentum trades |
| --- | ---: | ---: | ---: | ---: |
| SPY2013-2019 |1.9151|1.7478|2.5414|8|
| SPY2020-Jul2026 |2.1515|1.7640|2.5295|6|
| QQQ2013-2019 |2.8119|2.2213|3.4257|8|
| QQQ2020-Jul2026 |3.2044|2.2188|3.3311|4|
| IWM2013-2019 |1.4711|1.6531|2.1066|8|
| IWM2020-Jul2026 |1.2248|1.5735|1.8881|14|

All six beat zero-interest cash, four beat TRAIN-risk-control, none beats
buy/hold. Close drawdown improves buy/hold in2/6, equals it in3/6 and worsens
in IWM2013-2019 (28.98% versus26.80%). Low turnover alone is not a robust edge.
Do not choose QQQ, tune lookback or blend these seen outcomes into a winner.
Independent synthetic review and six falsification probe groups found no blocker;
50 new tests pass,150 reader/holding/momentum tests pass with2 native-symlink
skips; exact immutable readback passes. All adjusted/non-PIT/availability/cash-
interest and non-replication limitations above remain. Parent code is unchanged.
Root `D:\thericher-v2\model-artifacts\research\tiingo-adjusted-monthly-momentum-development-v1`.
Contract `sha256:1889637db6257008f75ffc92447a47798dc7e23639011f49aa9a8f99842edfac`.
Summary `sha256:2072fd77fef0f6c203c8d0aad87a94a75858cc751fb00a869b0bafb47a3db89d`.
Registry non_promoting_completed; no retuning/retry of this closed study.
Main re-retrieved Antonacci's original monthly excess-return/T-bill mechanism
and DeePM's original cost-aware portfolio objective plus pinned official MIT
source. Neither source's results apply to these ETFs; no upstream code, data,
weights, framework, optimizer sweep or source manuscript is adopted. A learned
net-utility comparison needs its own finite contract/ledger parity, not more
MSE-only forecast sweeps. Exact source receipt:
`D:\thericher-v2\model-artifacts\research\engine-source-retrieval\monthly-holding-next-mechanisms-main-20261003-v1.json`,
SHA256 `cfa5ad7a4c2d0338b5bf5db7197d5d61b934b1e54fc2346b61d57bd84b9b496f`.
Source proposals independently retrieved by the orchestrator:
[volatility-managed portfolios](https://law.yale.edu/sites/default/files/area/workshop/leo/leo17_moreira.pdf),
[same-clock intraday continuation](https://arxiv.org/abs/1005.3535),
[Chronos-2 cross-series forecasting](https://arxiv.org/abs/2510.15821).
The first and third are consumed by bounded packages; the intraday proposal
needs its own source-local complete-session contract, not a new agent/backlog.

## Closed TimesFM Reference

Latest completed study: `timesfm-2p5-tiingo-intraday-return-development-v1`.
The existing200M TimesFM2.5 checkpoint now consumed real market histories,
not only synthetic input:435 zero-shot forecasts,90 fixed policy/cost cells.
Each signed input is128 prior raw daily intraday returns `10000*(close/open-1)`;
the median predicts the next scheduled session's open/close return. No training,
fine-tuning, weights update, positivity clamp or future covariate. Histories
can predate the checkpoint; every target is January-July2026, after the exact
public October2025 weight hash. The official dated-weight interpretation and
unknown-corpus/source limitations are in DECISIONS, not a new promotion claim.

Each symbol has61 January-March and84 April-July targets, no past exclusions
or future censoring. The fixed >20bps long/flat threshold is identical across
5/10/20bps all-in round-trip costs. Cash, unconditional intraday long, previous
return and rolling128 mean use the same observations. The table reports
TimesFM mean net bps per observed session, with flat sessions included; these
are analytical unit-notional returns, NOT portfolio NAV or broker/local-paper
fill parity. No overnight holding or pooled independent-sample claim.

| Symbol / period | Targets | Trades | Mean net at10bps | Mean net at20bps |
| --- | ---: | ---: | ---: | ---: |
| SPY Jan-Mar | 61 | 4 | +1.1501 | +0.4944 |
| SPY Apr-Jul | 84 | 6 | +1.6047 | +0.8904 |
| QQQ Jan-Mar | 61 | 10 | +1.0302 | -0.6092 |
| QQQ Apr-Jul | 84 | 30 | -1.0237 | -4.5952 |
| IWM Jan-Mar | 61 | 7 | -3.8728 | -5.0203 |
| IWM Apr-Jul | 84 | 8 | -2.7714 | -3.7237 |

SPY's ten trades are a limited positive development observation, not selection
of a profitable model/symbol. TimesFM MSE improves rolling mean in2/6 groups
and MAE in3/6, but MSE is worse than zero-return in all six. Forecast error and
thresholded payoff answer different questions. Rolling mean never trades at
the fixed threshold. No lower-cost/threshold/context rescue or fine-tuning on
these outcomes follows; preserve every comparison and the revised seen-data,
correlated-ETF/overlapping-context and assumed-next-open availability limits.

Existing networkless Torch2.7.0+cu128 image with offline hash-verified TimesFM
2.0.2 wheel completed in31.213s including installation/startup. RTX4090 peak
allocation1,033,671,168 bytes, available-VRAM budget23,030,923,264 bytes.
2 CPU/6GiB host RAM and600s supervisor; parent held/released canonical GPU lock.
Independent inert-wheel review confirmed per-context statistics/attention,
not cross-series leakage from later contexts in the batch. Source review found
no blocking issue;52 new tests exposed/fixed five malformed-result checks
before freeze. Combined325 focused tests pass in20.51s, Ruff/both Compose
configs and separate immutable readback pass. No full-suite rerun for this
isolated package. Worker/container/agents closed; registry non_promoting_completed.
Existing weights remain unchanged/external; no new model download, market
acquisition, predictions retained, KIS call, schedule or Paper input.
Root: `D:\thericher-v2\model-artifacts\research\timesfm-2p5-tiingo-intraday-return-development-v1`.
Contract: `sha256:f8947da5f099267348e61f492e22462a319172edbbcbe1fcb662031ccf5d9ff9`.
Summary: `sha256:ba936e9d99a34f7366351c9a1337801005a6d49ae24fe55e894ea44eee7244b3`.
Claude's supplied-contract review was supported-with-limits; corrections:
`D:\thericher-v2\model-artifacts\research\timesfm-2p5-tiingo-intraday-return-development-v1-review.json`.
Outcome review supports runtime viability, not predictive skill. Retain the
small-sample caution; reject an unmeasured single-session reversal, the claim
that worse MSE proves no directional value, and the claim that fixed actions
invalidate cost sensitivity. Fixed actions deliberately separate accounting
sensitivity from strategy retuning; they do not establish robustness either.
Categorical verdicts and adjudication:
`D:\thericher-v2\model-artifacts\research\timesfm-2p5-tiingo-intraday-return-development-v1\outcome-review.json`.

Previous H180 study remains closed: four Ridge/16 TCN-attention fits,120 cells,
260.569s; uniform-four net sum-27.9622 at3bps and MSE worse than TRAIN mean
in all four folds. No winner or universal DL rejection. Its16 retained models
and complete accounting remain in Git/external evidence, not a new allocation.
Root: `D:\thericher-v2\model-artifacts\research\firstrate-m5-single-session-h180-development-v1`.
Contract: `sha256:9e53a350a4afa6020cfb56fd01c332f75e7a8fed53442b90bf95057b396c5427`.
Summary: `sha256:97fdc734f10b402600cfb1626e0fcb568a30f20d29bdc2d01d76f8a186f94dbf`.

The preceding feature-boosting study remains closed: four Ridge/four64-tree
fits,64 cells in67.879s. Boosted hurdle/stateful nets were-8.0852/-17.6684
at3bps, negative in every fold. Its full comparison remains in Git and
`D:\thericher-v2\model-artifacts\research\firstrate-m5-feature-boosting-development-v1`.
Contract: `sha256:15a55ae80ffed75eeaa4391e709c18d33186745e790d5eb0fedd47f57a64075d`.
Summary: `sha256:379d80823edc5df4128dcec534aea7e0d9c696b892d0b2d63735a692e556a0ef`.

The feature-Ridge parent remains closed with its negative gross sums unchanged.
Root: `D:\thericher-v2\model-artifacts\research\firstrate-m5-causal-features-development-v1`.
Parent contract: `sha256:95f522834a8d846b9f600602e9a9a1efa8fbcaecbb55a328f9cfcbbc6995866d`.
Parent summary: `sha256:57ded7f558db276fde1bdd058d67eae4db10356a91d279085f0c1f29f5ee417b`.

The preceding transition-policy study is closed, reproduced by the Ridge parent.
Its raw-stateful274 roundtrips and negative3bps folds remain unchanged;
the138-trade feature policy does not rewrite its parent. Exact parent root:
`D:\thericher-v2\model-artifacts\research\firstrate-m5-transition-cost-development-v1`.
Parent contract: `sha256:140944b6be72926440582fa317dc1de1cabc98440fb1cd140f680cec717e53d1`.
Parent summary: `sha256:a164d95f7632c0e181c08c6fbbde4b2eb64da347fcb592c0cc3d72f24390080f`.

The parent composed-policy study remains closed:16 Ridge/four tree fits and
160 paired cells in126.944s. Its tree earned+1.3782 at3bps over only two SPY
earlier-fold trades; other folds were flat. Majority was negative in every
fold. No profitable ensemble was selected. Prior details remain in Git and
`D:\thericher-v2\model-artifacts\research\firstrate-m5-policy-graph-development-v1`.
Parent contract: `sha256:74087f84dc70001685689ffb1747fe47b6a76587aba4e5345c2952a9806688d4`.
Parent summary: `sha256:9df32417e4e3abca22cf1f7540bb3c2ae51645a972c0aadd3da1486295f1a736`.

Previous geometry Ridge study remains closed, with12 fits/108 cells and
cost-fragile results;11/12 MSEs worse than TRAIN mean. Exact evidence:
`D:\thericher-v2\model-artifacts\research\tiingo-d1-ohlc-geometry-ridge-development-v1`.
Its full facts remain in Git and its immutable summary, not a new tuning seed.

Latest completed CPU study: `tiingo-d1-first-session-month-development-v1`.
Fixed first NYSE session each month, same-day open/close, versus fixed11th
session and cash; SPY/QQQ/IWM,2013-2019 and2020-July2026,5/10/20bps all-in
roundtrip. All54 cells completed with84/79 paired months per symbol and no
censored pair. At20bps all six candidate means are negative and below the
fixed comparison day: `descriptive_criterion_not_met`. No retuning or winner.
This is seen-data descriptive evidence, not a new holdout, statistical
rejection, portfolio NAV or executable auction-price claim. Shared same-day
scaling cancels, but independent price revisions and cost/fill uncertainty do
not. No event-based exclusions, cross-day feature, training or GPU allocation.
Independent static review and80 synthetic tests pass. Claude's frozen-contract
challenge was supported-with-limits; its unverified no-split suggestion was
not adopted. The existing Docker base image used one CPU/1GiB, network=none,
read-only source/data and the existing600-second process supervisor. The
actual run exited zero in4.18s including container startup; no child remains.
Root: `D:\thericher-v2\model-artifacts\research\tiingo-d1-first-session-month-development-v1`.
Contract: `sha256:cd61ca5b78138374cf916dbf82f943b7ecd1705710097ced3b142e32ac6d80c9`.
Summary: `sha256:3e8f6a8bc05d4ef175a8caae62eaae7f8b95d61cf5b0b7db01708bafbb64b30e`.
Source is the existing August9 Tiingo snapshot, overlapping prior studies,
not newly acquired independent data. Registry outcome non_promoting_completed;
no model, Paper input or successor compute appointment. Do not reopen this
fixed comparison by optimizing the calendar day on its observed outcomes.

Completed `fixed-forecast-diagnostic-h30-c36-v1` on CPU in 84.497s: all28
retained LSTM/LightGBM/TCN/attention models reloaded, all84 parent model/cost
cells reproduced, no training, GPU, new weights, retuning or held-out data.
Root: `D:\thericher-v2\model-artifacts\research\firstrate-m5-h30-lstm-development-20260921-v1\fixed-forecast-diagnostic-h30-c36-v1`.
Contract: `sha256:d3fa577bbf005492c340e9147c76b71ab8f35c4440240adb792e45fcd9874ab8`.
Summary: `sha256:47ed62aa043511e01f5550a5e81fb26a5d0d4b8081ce373453ea1d4b8aeb0b8f`.
Scored counts remain377/372/378/372 with63/62/63/62 history blocks, no future
censoring. Fixed >6bps selections: LSTM4, LightGBM36, TCN14, attention0.
Prediction standard deviations are approximately0.60-2.66bps across cells;
21/28 cells have worse MSE than the TRAIN-mean forecast. Seven improve it,
but no same-symbol/family/seed repeats that improvement in both folds.
These are seen-data descriptive reads, not independent skill tests. Counts
and dispersion explain sparse action; OLS slopes/correlations must not become
fitted calibration or a threshold choice on these same evaluation outcomes.
Claude supported the diagnostic with these limits. Independent review found
and main fixed a worker-payload field-validation gap before the actual run;
112 focused numerical/integration/runner tests pass.

The distinct opening-range CPU study is complete in259.329 supervised seconds:
`firstrate-m5-opening-range-development-20260923-v1`, contract
`sha256:8a02e63b4e2d08b5993625c20c2429d1bb62807bd86663bd87e0190d5143a83c`.
Its external root is `D:\thericher-v2\model-artifacts\research\firstrate-m5-opening-range-development-20260923-v1`.
First30 regular-session minutes define the high; the first later completed M5
close above it enters at the next open, once/session, and exits at close-minus5
minutes OPEN, including early closes. No overnight or fitted parameter.
Freeze decisions before complete-session censoring; retain all planned,
observed, censored and selected/censored counts. Compare1/3/5bps against cash
and the in-fold unconditional long mean at matched entry offset/session length.
The comparator is descriptive, not a deployable strategy or independent test.
Minimum16 complete sessions and8 scored entries per symbol/fold;600-second CPU
budget; two seen-data folds. No training, GPU, holdout or Paper replacement.
Claude's initial economic-interpretation verdict was uncertain; after narrowing
to descriptive_criterion_met/not_met, its verdict was supported-with-limits.
Known bar-start uncertainty and posthoc censoring remain, not silently resolved
by synthetic clock tests. Independent review and109 focused tests pass; bool
identity and cross-cost consistency checks were tightened before freezing.
Summary: `sha256:aa92f3677c328196fbd306b43f941627d7fb69f28f5cfd0df8bf51e47226e07b`.
All12 cost/symbol/fold cells completed,159 independent one-share roundtrips
(39/41 SPY,40/39 QQQ). Each fold has63 scheduled sessions; SPY fold1 excludes
one opening-unavailable session, and no selected trade is censored. At3bps/side,
SPY fold1/fold2 net dollars are21.5310/-22.1273 and QQQ19.4992/-22.2182.
SPY beats its descriptive matched mean in both folds; QQQ only in the first.
The predeclared result is `descriptive_criterion_not_met`; not statistical
rejection of the mechanism, a portfolio return, or a reason to retune the rule.
The immutable contract/output and custody are closed, with no active research
container. Next priority is the existing Paper lifecycle result; later research
should use a separately declared mechanism/replication, not rescue this matrix.

Completed `persistent-position-h30-c36-v1`: CPU re-inference of all eight
retained context36/H30 LSTMs and fixed cash/long/previous-bar/SMA controls.
72 paired cells (144 policy cells), all 72 parent controls reproduced in
317.730 supervised seconds, with no training, GPU, tuning or new holdout.
Contract: `sha256:823c8f6ca908f6965bc015cc196da9ae3a12a1630376932b74a20daebbcad41b`.
Summary: `sha256:aa432d909f42d76d1d0f9233d0e177ff67685a1f568f2f56d780d5fdf02710b0`.
Root: `D:\thericher-v2\model-artifacts\research\firstrate-m5-h30-lstm-development-20260921-v1\persistent-position-h30-c36-v1`.

Every policy pair has exactly equal gross payoff and exposure; net difference
equals removed boundary fees. This verifies an accounting identity, not alpha.
At each cost, always-long roundtrips fall from 1,499 to 250, previous-bar from
843 to 455, and SMA from 863 to 388 across four symbol/fold cells. Their combined
independent-trade net remains negative at 3/5bps; totals are not portfolio NAV.
The LSTMs have only four trades across eight cells, no removable boundaries,
and no cost improvement. Six cells are inactive. All four folds retain their
377/372/378/372 decisions and 63/62/63/62 blocks; no session was censored.
Do not retune thresholds or describe merging as predictive improvement.
80 focused synthetic/runner tests pass; independent static review found no
blocker. Container/worker/scratch exited; no new weights or GPU appointment.
The subsequent fixed-forecast diagnostic is complete above. Do not reopen
this closed matrix or optimize already-absent LSTM turnover.

Completed bounded comparison: `model-family-h30-c36-v1`, linked to the existing
FirstRate H30 family. Fixed H30/context36, unchanged two session folds and
1/3/5-bps costs; four LightGBM fits precede sixteen TCN/Transformer fits.
The eight existing context36 LSTMs are reloaded, not retrained; 84 parent
control cells must reproduce. Contract
`sha256:9625f31d0fc0d879a106cc0fad3d058752658728c6a310d0684b9610c749cb0a`
is frozen. CPU completed96 cells/four new models in89.446s, reproducing all84
parent controls. CUDA completed48 cells/sixteen models and5,632 updates in
499.058s. Both used the same pinned networkless image and matched cohort facts.
No model selection, holdout, public-model comparison or Paper replacement.
LightGBM4.6.0 is MIT, installed from a verified external wheel into ephemeral
`/tmp`; no base/Paper image dependency changes. Independent review caught and
fixed normalizer and fold-identity binding gaps before freeze.
CPU summary: `sha256:c514f0a4a2da5a9a4c5e3a5d66279de7f43971e53af22bfb819347ffbc686b41`.
CUDA summary: `sha256:db1cfc4d127449615c824cc4550e3d4bd103c456830e0056c91b2eb7006ab813`.
All20 final models beat TRAIN-mean MSE, not proof of predictive skill. At both
3/5bps per side LightGBM is negative in4/4 cells; TCN is positive1/8, negative5/8,
inactive2/8; compact attention is inactive8/8. No new model has positive net
PnL in both folds. The matched LSTM has only four trades across eight model/fold
cells, so its tiny aggregate is not a robust baseline edge. Attention's zero
trades mean this fixed rule never crosses6bps, not a universal architecture
failure. Models/configs occupy500,891 bytes externally and all passed numeric
or native-text restoration and exact decision parity.225 focused tests pass.
Both containers and scratch jobs exited, GPU lock absent; recovery complete.
The recommended persistent-position comparison is now completed above.
Do not select new parameters from either closed matrix.

2026-09-22 public-model decision: use official Apache-2.0 TimesFM 2.5, not the
3.0 weights whose separate license excludes revenue/production uses and also
restricts outputs. Private offline noncommercial research is not categorically
prohibited; personal ownership is simply not a blanket trading-use permission.
See DECISIONS for the actual text and Claude resolution.
The `timesfm_local` adapter verifies local config/safetensors and calls the
constructor/checkpoint loader directly: the inspected upstream Hub convenience
method attempts a Hub call even for local directories. Device is pinned before
weights move; no CPU fallback or automatic download. Source and weights stay
research-only. Synthetic inference is not a financial benchmark, training,
model selection, or Paper qualification. The model card lists pretraining
sources, but their exact overlap with our financial panel is not verified.
That recommended predictive breadth is now completed above, with fixed naive
and LSTM controls and a full-context dilated TCN.
Do not silently retune the closed 48-LSTM matrix. The completed target-position
comparison above separates turnover cost from prediction error without
establishing a new predictive edge.

The exact `timesfm-2p5-offline-runtime-20260922-v3` synthetic appointment
completed CPU (8.882s) then RTX4090 CUDA (6.730s), four contexts12/36/128/256,
horizon12, finite outputs `(4,12)` and `(4,12,10)`. CUDA peak allocated memory
was 946,213,376 bytes; this includes a pretrained model, not trained weights.
The official 925,181,104-byte safetensors and wheel remain external under
`foundation-models/timesfm-2.5-200m/1d952420fba87f3c6dee4f240de0f1a0fbc790e3`.
Result root: `D:\thericher-v2\model-artifacts\research\timesfm-2p5-offline-runtime-20260922-v3`.
Contract: `sha256:5dd84883513ae88225d19bc68d3cc07d92fb909626409e9893c0804ced3aa5d5`.
CPU: `sha256:1d18836c7b328cfe813ce0ed04a8814ea56f3d5660ce5361b427fc23892e12a4`.
CUDA: `sha256:ba80f8bd9765a132e230f3ba13f21ff02db61fd52bd13e59dc9d12daa70bacfc`.
No financial inputs, targets, forecasts or scores were retained. Both workers
exited; recovery complete. Independent runner tests found missing source-key
and model-identity checks; main fixed them before this final run. The earlier
valid v1 runtime result is preserved, and metadata-only v2 is abandoned before
CPU/CUDA. Focused integration passes 108 tests; no shared Paper runtime changes.

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
| Technical/chart and momentum/regime | First30-closing29 completed60 CPU cells/zero fits; all four stress ETF/fold NAVs lose cash and fixed exposure controls. Earlier time-of-day band remains killed | Preserve kills; no cost/threshold/window/ETF rescue or original-paper rejection; a distinct question needs its own finite contract |
| Classical ML/statistical | Forward-risk two-fit Ridge comparison is closed/rejected: SPY fails the past-variance control in all90/first45. Paired-lag/downside/pooled history stays closed | No QQQ-only, window, cost or parameter rescue on seen data; a distinct mechanism needs its own finite contract |
| Sequence/DL/public model | Paired LSTM/attention actual CUDA fits complete, both stress-negative; TimesFM/Chronos/TCN/patch history unchanged | Source-independent five-timeframe completed inputs pass target-free smoke; new campaign needs its own shared finite compute contract |
| Portfolio/allocation/meta-decision | Joint daily-flat allocation completed three CUDA fits/21 cells; primary120 loses stress NAV and constant/EW controls; numeric weights and exact CPU inference retained | Preserve kills/seen-source history; no same-data window/fee/ETF rescue or Paper qualification; a distinct future question needs its own finite contract |

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
| TimesFM2.5 | Existing pinned Apache-2.0 weights; real-data daily-return comparison completed on CUDA | Official October2025 exact-weight history supports January-July2026 target scope under trusted publisher dates. Context/instrument overlap and revised seen data remain explicit; no independent/Paper claim. |
| Chronos-T5, Granite | Prior isolated source/runtime studies | Their old source contracts stay unchanged; no automatic extension to a market comparison or Paper input. |
| Chronos-2 | Official Apache-2.0,120M dated/hash-pinned external checkpoint; matched real-data CUDA comparison completed | Same-origin cross-ETF and duplicate-self controls completed with no robust winner. Unknown corpus and revised seen-data limitations remain; no Paper/depth selection. Exact evidence is in Current Research State. |
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

Chronos-2 official sources re-retrieved2026-09-25:
https://huggingface.co/amazon/chronos-2
https://github.com/amazon-science/chronos-forecasting
Its related-series group attention is relevant to the next cross-ETF question,
unlike TimesFM's independent per-series batches. Future covariates in examples
are not permission to pass future market values. No AWS/cloud service or paid
runtime is proposed. Source benchmark claims are not equity-profit evidence.

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

Corrected-account QQQ Paper round trip completed October7, independent of
research profitability. Actual-fill accounting is the next product priority;
SPY23:50 KST and Data head00:29 KST retain their existing owners. No research/
permission/GPU runtime block exists.
September20 matched QQQ/SPY days and October1/2 context are complete revised
development inputs; old unavailable causal consumers stay scoped to their own
contracts. They do not block these sources or the separate Paper opportunity.
Data's subsequent dated acquisition is closed and fills August28/31 and SPY
September1. With the existing QQQSeptember1 source, recent per-session coverage
spans25 shared regular days August28-October2,9,750 M1 per ETF. This is useful
development coverage, not50 independent blocks. The new paired-lag contract
explicitly froze50 separate source identities; it does not rewrite older pins.
Do not reuse the closed20-date contracts as though their source pins changed.
Net-utility, public-model, fixed-band, causal-mixture, downside and pooled-patch
campaigns are closed; retain their kills/controls and do not repeat them.
Current time-of-day feature,60-case input preparation and12-cell FirstRate
mechanism comparison are closed; its frozen net-loss kill remains.
Their14 prior session prefixes/current OPEN/completed M5 cutoff introduce no
previous-close gap, short, leverage, target, fitting or Paper input. The source's
2007-2024 SPY/VIX/IQFeed return claims do not transfer to this variant.
Official author PDF/university text was read with the web tool; direct fetch
403 is separately retained, not a fabricated raw-source hash or code license.
Exact source-only receipt:
`D:\thericher-v2\model-artifacts\research\source-discovery\intraday-mechanism-20261003.json`,
SHA256 `b81abdb76587cf05184eb028a73953022d41054a2c112cb91fcd1e312f33e885`.
Data's dated-close-key reach packages are closed; no collector wait remains.
Preserve their exact source identities and scoped-empty findings.
No active campaign or GPU appointment remains. A next distinct mechanism needs
its own frozen entry/exit/cost/control contract, not a changed hurdle or repeated
architecture run; broader existing FirstRate inputs are available independently
of the exact KIS older-date probe. Do not make that probe a research wait.
