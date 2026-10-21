# Engine Research Stateboard (엔진 연구 담당)

2026-10-21. A=D:/thericher-v2/model-artifacts; M=D:/market_data.
Own targets/features/splits/fitting/replay, not broker risk or human approval.
Company NAS lifecycle UNFINISHED; Paper authority independent of research pass.
Parent shared MD/Git. MD is not proof of running model/GPU.

## Current / Next Research

Hubble: broad25 HGB pair and readout COMPLETE; no refit.
Next SOURCE-only current-broad25-missing-context-recurrent20-development-20261021-v1:
same30975FIT/15250INNER/1275PRED input keys, R21 LSTM64/head32,
four latecontext values plus usablemask/learnedunknown4token.
Validate rawunknownNaNs, sanitize hidden branch before torch.where; CONTROL
post-affine knownratio zeros only, FUND actualratios, same adapter/age/mask.
FIT-only observedcontext affines, no ID or missingrow removal.
One pairedseed3901/max256/pat30/LR/bestchronologicalINNER including0.
Native actualoptimizer/fullcheckpoint/RNG/allknown-allmissing-mixed/gradient
and400row pack+1000eval CPU-CUDA pace proof before numerical dispatch.
Source120+Claude60=180active/1800elapsed. ActualCPU400row/1000eval/fullstate/
mask/gradient/finalhandler PASS; initialpre-modelmount125 preserved.
NumericalGO3600TOTALactive inclclosedsourceonce/14400elapsed,2fits/
39936updates/one1275PREDintake12cells. ActualCUDAproof+pace/headroom first,
then automatic market dispatch if guards pass; no market fit inferred yet.
Review A/review/current-broad25-missing-context-recurrent20-20261021-v1,
responsecea35537 SOUND_WITH_NAMED_LIMITS. One paired draw, no general causal
ratio effect/absence; matchedmask does not eliminate retrospective leakage.

Einstein: broad25 Chronos forecasts and fixedreadout COMPLETE FAIL.
No more forwards/fits/weight search. Next close-only expert SOURCE proposal,
prior project indicator-kernel reuse plus causal/missing/tie SYN tests only,
not new market feature generation or an outcome-picked ensemble.

## Broad25 Data / Completed Baseline

Priceaudit4831e9b5 at A/data/current-broad25-price-input-support-20261021-v1:
all25everydate/FIT31450/INNER15625/PRED1275/input-only membership.
R21=prior21 logCLOSEdiffs, not fullBar/PIT/price-fidelity qualification.

Optionalproxy26 Data17c3ea82:
A/data/current-broad25-optional-proxy20-input-20261021-v1/CONSUMER.json.
R21, age, filedproxy, usablebit, knownnetmargin/liab-assets/noID.
Quarter usable FIT11091/INNER6017/PRED425, unknown20359/9608/850 retained.
30975/15250 known labels after physical20session purge; PREDlabels separate.
Acceptance-or-labelledfiled+2session proxy and captureafterorigin explicit,
not PIT. No matchedmask claim of value/metadata leakage elimination.
Separate PRED Eval9c0bd613/pred-eval-r1:1275keys/51dates/25axis/70marks,
sealed AFTER actual HGBscores/policies4466b99a. No old425label intersection.
Each actual producer/Engine access counted separately, not globalonephysicalread.

HGB baseline COMPLETE:
A/research/current-broad25-optional-fundamental20-development-20261021-v1/FINAL.json.
RESULTb3dfa8dc/VERIFY9b592e98/2CPUfits20-21rounds/selectedprefix0-1/
1readout/12logical9distinctcells/248.067898activeupper/alljoined.
Actual sklearn1.9.0/nativeNaN/explicitchronological X_val/safestate/curves.
10bp PERLEG growth/DDpercentNAV CONTROL=uniform+.294233/.207221;
FUND+.443503/.227658. ProperFAIL/financeFAIL/overallFAIL. No rescue.
Tiny properincrement/one boostinground is not robust accounting evidence.

Chronos Data0131fedf at current-broad25-chronos512-input-20261021-v1:
1275known512 O/C,425exactsource-feature-context-model-mode cachematches,
850new/no changedorunknownmatches/50independent rawchecks.
Engine A/research/current-broad25-chronos20-completion-20261021-v1/numerical-r1/FINAL.json:
trusted95a9710 release2025-10-30 before every target/51modelreturns/
850new+425cached/0oldforwards/0fits/unchangedparameterbuffers/alljoined.
19.095469GPUallocation/10.227117worker/3.554894forward seconds/leasefree.
Sealed913fdbfd. Fixedreadout-r1/RESULTa8b97bb9/VERIFYdb9f6171 COMPLETE:
9distinctcells/1intake/0newmodelcalls/75.578542newactiveupper/alljoined.
10bp growth/DDpercentNAV Chronos-.026481/.406450 vsuniform+.294233/.207221,
financeFAIL. No CE/probability claim from medianC20-minus-medianO1 contrast.
Corpus not_disclosed/currentlisting-vintage/nonPIT/CA/finality/reuseddata,
not independent alpha. No further calls just to occupy GPU.

## Closed Families / No Repeat

- Recurrent20 7efaa9e0:2CUDAfits26epochs/best6/4056updates/29.194GPUworker.
  10bp FUND growth/DDpercentNAV+1.015525/.213627 vsBASE+.867644/.321372,
  uniform+.687260/.224125. IncrementalPASS, FITprior proper better.
- Patch512 FINAL54867822/RESULTddc4eee3:1CUDAfit21/best1/1638updates/
  44.017worker/405027params/+1.341353/.287486; proper/financeFAIL.
  Safeweightsaf4234c4/curvesf00fec5d. Two readers/oneintake, no refit.
- ID-mask dee22eff:1CPUfit58/best38/4524updates/33.568780worker/
  241.714533activeupper; matched3901initial8tensors exact. IssuerR2.165545
  mechanismPASS, growth+.706135/DD.270296 financeFAIL. CPU selected on
  near-tie projection, not GPU ban. No further small-universe mask/seed rescue.
- HGB20 27b417c4 prior0 uniformalias; HGB-RNNf65ca8e8/Patch-RNNbacc9f16
  exact recurrent allocation aliases, not diversification.
- Chronos peer914fa4f9 and fixedrankfusion12e05488 FAIL; rankfusion
  +.850532/.228229 percentNAV, not a fresh replicate.
- RankNet e9f5bbb6/54445662:21CPU/best1/1638updates/FAIL;
  originalHUBER0update missingidentity/pairUNAVAILABLE/debits unchanged.
- OOFc04d7aeb9fits and earlier GRU/MLP/TCN/attention/indicator/TimesFM/LoRA
  are histories in Git/A, not ready automatic grids.

## Prospective / Execution Separation

FUND20point0996dabb committedOct21 01:01:46UTC BEFOREOPEN; twoCPUforwards,
8known25axis17unknown/ONE.005cohort->Nov17 twentiethCLOSE21UTC, no reforecast.
Actualadapter2e31bb22/ABId045b4a5/composite68b8bd1a exact6+2feeds.
FinalNov17 DataTask d7854350 INSTALLEDenabled/next23:20UTC, not futurecapture.
Boole measurementTask95924e7e INSTALLEDenabled/nextNov17 23:55UTC,
parentRO4650d609 PASS; executor closed/futuremarksNOT_OBSERVED.
Earlier fifth-CLOSE pointcb1c1d9a/shadowd33490c9/Oct27measurement22db8f33
are separate installed scopes. Measurement is not a broker fill/PnL.

Wegener prepares savedpoint20session native .005cohort Paper runtime on
imagef31e; no model reforecast/risk change/currentR5swap. Profitability is
not an execution permission prerequisite. Research never adopts inventory.

Breadth: complementary mechanisms and useful cache reuse, not open grids.
Depth: frozen finite fit/epoch/time caps, train/INNER curves/LR/earlystop/
beststate; native proof/actualPREDhandler before market. GPU only useful work.
