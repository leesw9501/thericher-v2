# Engine Research Stateboard

Current projection 2026-10-14 KST; AGENTS.md owns policy, NEXT_CODEX_GOAL.md
owns Paper recovery. This lane improves model learning and cost-aware replay.
A=D:/thericher-v2/model-artifacts; M=D:/market_data.
R=A/research/daily5-ohlcv-convergence-expert-composition-20261014-v1.
R130=A/research/daily20-remaining-reference-exit-development-v1.
R131=A/research/daily20-mean-versus-lower-quartile-exit-development-v1.

## Ownership And Current Stage

Engine owns targets/splits/fitting/composition; Steward owns GPU/family custody.
Strategy supplies proposals. Parent owns review/integration/Git/shared policy;
Execution owns broker risk/replay semantics. No implementation ownership changes.
Current campaign CLOSED/rejected/frozen; Parent reports independent readback PASS.
No worker/GPU allocation remains running; no further numerical rescue/selection.

## Actual Campaign And Shared Spend

Family daily5-ohlcv-convergence-expert-composition-development-v1; no holdout.
R/contract-finish.json SHA256 9e1605097cea9921489e56d03d41111033acfc59833481b3debf874385d7dae0.
R/integration-evidence-finish.json SHA256 76e5642db119257ac6288b2a54e1016a5a555ae941ca1aa25d99d7d49a864cae.
R/study-finish/output/result.json SHA256 7052ea0a6d2ca8ed0eb9af12c79a0a6d84fb81d417e123323b4fe3f406b3245e.
Cumulative CPU13/CUDA3 =16 market fits INCLUDES carried CPU4/CUDA1 =5.
Finish added CPU9/CUDA2 =11,26epochs208updates; cumulative39epochs260updates/0failedfits.
R1 intake Budget.check(publication=True) mismatch failed before fits (0).
R2 sklearn leaves numpy.int64 JSON failure followed five completed fits;
serialization-repro.json proves first cause. Receipt normalization/restoration
did not refit OOF1. Technical failures/debits remain, not scientific rejects.
Host.started_at inherits FAMILY budget start2026-10-13T16:54:24.587709UTC,
not finisher invocation start.1143.0095s is cumulative R1/R2/finish,not new-job time.
Finisher contract frozen17:08:26.732289UTC; exact invocation start not recorded.
Canonical registration1460.30481s/original1800s; no refund/reset/retry budget.
Fit budget exhausted; complete/non_promoting_completed is not promotion.

Retained daily512 source: prior21/raw20x5 + latest scalar20 indicators;
raw/indicator/augmented Ridge, depth4 tree, GRU32, trend/reversion rules,
fixed quarter blend, depth2 utility gate. No profitable-member prerequisite.
Payoff entry OPEN(e) -> fifth CLOSE(e+4),10bps/side; recost5/10/20bps.
135 TRAIN dates; OOF fit49/79,inner16/20,forecast34/34; final fit107/inner27.
Strict target-end < next decision; TRAIN ends695 < DEV719.
Gate uses680 chronological OOF rows/68 dates, not in-sample predictions.
78 cells: cash/raw/singles/blend/gate/matched-planned-gross; six seen cohorts.
Prior21 supports latest scalar Cutler RSI14, not full20-step RSI14 sequence:
require declared prior35/per-step causal support for that; never zero-impute.

## Results And Author Readback

At10bps gate/blend growth: DEV1.7921%/0.7471%; later_seen0.4071%/0.2239%.
Gate/blend DD: DEV0.4684%/0.2941%; later_seen0.1877%/0.1191%.
Frozen kill: U>blend/cash AND DD<=blend in EACH block;4 true/2 DD false.
Rejected named gate recipe, not all models; no substitute winner/Paper adoption.
OOF2 GRU TRAIN MSE167.8152->166.9538,inner180.5368->180.4409;
final TRAIN166.3978->165.3964,inner1009.4370->1009.4775 (percent-scale targets).
Both stop13epochs/inner_patience12,restore epoch1 under >0.1% improvement rule,
NOT global minimum: final epoch3 inner1009.2900 was lower,but below min_delta.
Source scaled_y=y*100 is uncentered percentage points,not standardized/bps.
26 actual curve points retained. OOF1 original curve missing; selected-checkpoint
MSE recomputed,epoch1 inferred from13epochs/patience12,not recovered trajectory.
Early stopping is not convergence proof; target conditioning remains a hypothesis.
Safe numeric NPZ checkpoints retained D:,allow_pickle=False.
R/readback_check.py API synthetic_check()/verify(root): author/Parent PASS,
chronology/purge,680 unique OOF keys,spend,cost/utility/checks/bound hashes.
R/model-stage-frozen.json SHA256 6af55bb4efd997ce98f0c058bfd37442b259b08fdcf77f0f5cb2977cf1572148.
19 finish SYN passed; R/review-result/claude-dual-result-outcome.json:
supported-with-limits. Readback is not independent raw-price/OS/PIT replication.
Seen/current-listing/nonPIT/revised/raw-action/nonTR/availability/finality,
fractional-fill/latency/capacity/small-correlated-support limitations remain.

## Ready Successor And Historical Custody

Strategy handoff A/strategy-research/next-breadth-20261014-v1/handoff.json SHA256 7c9eb632a3183b191fc1f426596eadcd2d3741b15c1fbbf042bf2c09326b8d2e.
Ready source proposal: MIT TCN2f8c2b817.../Chronos2v2.2.2; no new frozen allocation.
Prefer CURRENT OPEN(e)->CLOSE(e+4) payoff/rows/costs for clean conditioning contrast:
TRAIN-only target centering/scaling,normalized GRU + TCN/raw Ridge; not LR brute force.
Inverse head -> percentage points (pp); decimal=pp/100,bps=pp*100; costs once.
Test10bps=0.1pp per side. Predeclare constant-zero/TRAIN-mean loss,output dispersion,
pre/post-clip gradients,standardized/economic losses,relative inner patience/purge.
Freeze finite axes/budget before fits; old results/debits/curves remain unchanged.
WITH foundation member, EVERY compared TRAIN/calibration/OOF/DEV target must follow
95a9710... release2025-10-30T14:58:57UTC; common postdates, no pre-release old800 OOF.
Current payoff needs verified joint OPEN/CLOSE forecast h5: OPEN1,CLOSE5,not CLOSE proxy.
If exact official API/alignment unsupported or unverified,isolate runtime/reject comparison.
OPEN1->OPEN6 is a distinct target: freeze for ALL new models/replay; never reuse old
percentage-target checkpoints/predictions as comparative controls for that target.
Corpus/instruments not_disclosed/context overlap remain; no OOD/independent/Paper claim.
Source9fits is not a global cap. No successor fits allocated/dispatched here.

130 CLOSED/rejected,integration de64b98f681527e4247c8814bb5450cd7e9283ba8e07f3f8f9a2628b596bf29d;
CPU1/CUDA1,16epochs1568updates,78.42165s/original600s,0failedfits;
132complete TRAIN/25080rows/674dates,30cells/36checks27true9false0unknown,
both rejected; no weights/sealed spend0. Exact outcome/debits unchanged.
131 SUPERSEDED UNFINISHED/SOURCE-READY/QUEUED; no actual fits/allocation/weights.
R131/engine-r1/source-release.json SHA256 102f2685feb889c6c77a8c02f001b778011725192347765e254c686ad95015a5.
Model7fd85816.../interfaceed8364f4.../reuseee1fe908.../validation831c0f20...;
16 NumPy/mock SYN only,no canonical scientific row/native mean parity.
Never replay source creators. Existing A/_control/ledger/2026-10.jsonl and
A/engine-research-agent/locks/gpu.lock retain custody; history stays Git/roots/RUNBOOK.
Old settings stay local; fresh convergence/features/ensembles allowed.
Paper independently retains shared initial10%basis/losses/reservations.
