# Research Steward Agent Stateboard (연구 자원 및 평가 관리자)

`AGENTS.md` owns policy and `NEXT_CODEX_GOAL.md` owns the company objective.
This stateboard retains only cross-track GPU and sealed-evaluation custody.

## Current Resource State

2026-09-22 completed appointment: `regular-session-cost-matrix-v2` under the
existing FirstRate H30 family. Frozen contract:
`sha256:012497f503e322dcbc076aacc174dc10e039b1da185876b0744b07f33e4a0646`.
CPU completed all216 cells in 117.611 supervised seconds; its summary hash is
`sha256:5198f95a0c6a8863cd18a9fa8e74431a1e0f4b827b4cebab47b59b58cb14523b`.
Canonical GPU lock was absent and no research process/container remained.
The single Docker CUDA appointment completed all 48 LSTM fits, exactly eight
full chronological epochs and 13,248 updates, in 159.193 supervised seconds
against its shared 1,800-second budget. All 144 CUDA cells pass replay; summary
`sha256:4bacb76827f3de667c331e37b65a5a7b603e6be51b94034041524b268350e3b1`.
All 48 final models/configs are retained (435,104 bytes), with numeric/hash and
actual Torch CPU reload checks. Container/child jobs reaped; canonical GPU
lock absent, registry records `non_promoting_completed`. No successor job is
running or reserved. Recovery: complete.
Contexts12/36 and horizons30/60/120 share this family allocation; no sealed
evaluation, winner selection or Paper promotion. Models belong only under
`D:\thericher-v2\model-artifacts\research\firstrate-m5-h30-lstm-development-20260921-v1\regular-session-cost-matrix-v2`.
The existing RTX4090/image/runtime is unchanged; D: has 40.2 percent free.
v1 contract `39390e865930ad883021633997f508bef0d60ff3a71db4399eebfdb3ecced561`
was metadata-only and recorded `non_promoting_abandoned` before any phase after
review found a scoring-support omission. It spent no compute/evaluation.

The 2026-09-21 frozen FirstRate M5 open/open development comparison completed
four CPU fits and 48 aggregate local-paper cells, without GPU allocation,
retained weights, sealed evaluation, or promotion. Contract/summary hashes and
prior-family linkage are in `agents/engine-research.md`; they do not reserve
compute for a successor.

`firstrate-m5-h30-lstm-development-20260921-v1/20260921-h30-r1` completed its
previously frozen contract, SHA256
`be785361611db683afb3bd4bb80d245fc69e93fb90279e9ec8a1fafe459e22fe`.
It spends no sealed evaluation. The fixed budget is eight Ridge fits and
16 LSTM fits (two symbols/folds/contexts/seeds), 108 cost cells total,
600 CPU seconds and one exclusive 1,200-second CUDA appointment. All final
eight-epoch weights/scalers are retained externally only after whole-phase
success; no best-checkpoint selection or Paper consumer. CPU input/parity
readiness, not positive PnL, controls GPU dispatch. CPU completed all 60 cells
with parity in 33.664 seconds; summary SHA256
`06dc794bd575f42aa4079f5f7dac9a61d64f58659664a5587608a74c68b14142`.
The exclusive CUDA appointment completed 16 fits/48 cells in 26.733 seconds,
without timeout, and released its lock. CUDA summary SHA256:
`4329cf2727bd8adeded60742507ce596be6b20e134e6639db61dd71bdb95d99e`.
All 16 final numeric-only NPZ/config pairs passed hash/schema checks and actual
Torch CPU restoration with synthetic-input finite inference. No raw market
rows or predictions were emitted by that reload check. No GPU job remains
owned by this campaign; no successor appointment is implied.
The old installed image lacked an already-pinned calendar dependency; Infra
rebuilt the existing research image. Both actual phases use image
`sha256:d6b43213ee3877653e3c1e79c7238fb5caa71241abf238838fa0c3332cf4f039`,
Python 3.12.14, Torch 2.7.0+cu128, CUDA build 12.8, NumPy 2.5.1 and sklearn
1.9.1. Range-resolved research extras are a reproducibility limitation, not
a claim of a fully locked environment.

The same image completed the fixed train-only diagnostic in 13.201 CPU
seconds, restoring all 16 models without training, evaluation tensors, or GPU.
Its immutable appendix and hashes are in Engine Research. No allocation is
held. This diagnostic spent no sealed evaluation and did not reopen closed r1;
its finite learnability successor is recorded below.

The distinct four-fit train-learnability contract completed its reviewed scope,
SHA256 `f2be555bc0b42f58237a6bc23ab258dcecd04491bcf70036f86a2cc9e4b663b2`.
After 24 synthetic CPU tests and an absent-lock/no-Python-worker check, main
ran one appointment on the same installed image: all 1,024 updates in 9.779
seconds, inside the 180-second parent limit, no retry/fallback. The lock was
released and its container removed. No new evaluation, weight retention,
model selection or Paper consumer. Main owns Execution preemption through
the existing parent lock/supervisor and child reaping.
The distinct H30 `full-cohort-u256-v1` contract is frozen and registered in
the same trial family, SHA256
`d7cceb5ab3642d2a727bc8f0f73ac3ee58a3b1393b196a553e057391c1ece596`.
The single 180-second CUDA appointment completed all eight context12 fits,
256 updates each, 2,048 total, in 27.336 parent-supervised seconds (25.403
worker seconds; 4.947554 summed fit-wall seconds, not CUDA kernel time).
CPU completed four Ridge fits/48 cells in 19.783 parent-supervised seconds,
matching r1 exactly; CUDA completed 24 cells. All eight final-update numeric
weights/configs are retained externally and passed hash/schema plus actual
Torch CPU reload checks. Summary hashes and results are in Engine Research.
The pre-dispatch recheck found no lock, host Python worker or GPU-enabled
running container. This run used the existing pinned image and exclusive
parent lock/supervisor, with read-only source mounts and no network, credentials,
image rebuild, retry/fallback or schedule. The child and named container are
reaped, lock released, no research Python worker remains; the existing registry
records `non_promoting_completed`. No sealed evaluation or selection spend.
Recovery class: complete. No further GPU allocation.

The separately frozen `fixed-nominal-hurdle-v1` CPU DEVELOPMENT contract links
to all eight retained full-cohort models, with zero GPU/optimizer/selection or
sealed-evaluation spend. Contract SHA256
`6e00636fe0eb2b507affbc22c296281997946a9a39de7df171317b6204832c73`;
the existing custody ledger records `non_promoting_completed`, summary SHA256
`8a54c24785716d04bd1958bcce951a6e9bbaa7881d24a47e7b9fd4ada24db86b`.
All84 cells and all60 prior sign/naive reproduction checks completed once on
the same pinned networkless image: 14.941 supervised / 8.822 worker CPU seconds,
under both 300-second limits. No GPU appointment or lock was acquired. Parent
models/source/data were read-only, no credentials/rebuild/scheduler/retry, and
no new weights. Child/container reaped; no research Python worker or temporary
job remains. Artifact pointer, limitations and mixed results are in Engine
Research. Recovery: complete; no follow-on allocation or promotion implied.

The bootstrap created no allocation or training run. Recheck actual GPU/process
ownership before an appointment; the historical idle facts below are not a live
utilization measurement. A frozen developmental campaign may use already-seen
lawful data with explicit assumptions under the 2026-09-21 `AGENTS.md` policy.
Custody still records family lineage and evaluation spend; this does not reopen
a sealed holdout, promote a candidate, or require a successful D1 pair.

## Historical Resource Facts

The dated closed studies below are not current GPU availability or dispatch
instructions. Recheck the owned lock and actual workers for each new job.

- The RTX 4090 is free. The bounded Tiingo IEX r1 source-isolated appointment
  completed and released its memory; no GPU process or sealed-evaluation
  allocation is held by Research Steward.
- No frozen, input-qualified campaign is ready for an appointment.
- The FirstRate 5m L2, fixed 20/60 technical-trend, and fixed Wilder-RSI
  mean-reversion controls all completed `rejected`: none beat always-flat in
  any of its six fixed nonzero-cost SPY/QQQ cells. Their aggregate-only
  local-paper matrices were terminal-flat and replayable, but no closed lineage
  holds a GPU appointment or sealed-evaluation allocation.
- The frozen Tiingo D1 trend-pullback rotation stopped before evaluation as
  `input_unavailable/insufficient_validation_active_decisions` (3 active
  decisions versus 100 required). It spent no GPU appointment, sealed
  evaluation, selection, or model allocation. Its completed mask audit was
  consistent and closes the lineage; it remains outside GPU custody.
- The completed QQQ/SPY D1 forward causal qualification is Data-only and
  `input_unavailable` for three unobserved runtime facts: named clock/session,
  decision-time availability, and provider finality. It consumed no GPU custody,
  sealed-evaluation history, or model allocation.
- The separately bootstrapped QQQ/SPY D1 v2 forward cache reattaches 18 common
  sessions under a distinct identity, but does not change those unobserved
  clock, availability, finality, or corporate-action facts. It consumes no
  GPU custody, sealed-evaluation history, or model allocation.
- The current KIS D1 prospective observation receipt is a Data-only scoped
  `input_unavailable/first_observation_target_failure` first stage for completed
  session 2026-09-04, without a
  later observation. Even a matching pair cannot allocate GPU or sealed
  evaluation; an absent or changed decision-time identity only disqualifies its
  scoped session.
- The QQQ/SPY historical D1 CPU baseline reproductions and the later frozen L2
  logistic control completed without a GPU appointment, model-selection
  allocation, or sealed-evaluation spend. The L2 QQQ/SPY after-cost replays
  were both negative and below their fixed previous-bar-direction controls;
  the later CPU-only shallow-tree reproduction was also below those controls
  for both symbols and retained no serialized estimator. GPU custody remains
  free; neither failed descriptive lineage reserves an appointment or creates
  a follow-up allocation.
- The completed Tiingo IEX r1 receipt is
  `D:\thericher-v2\model-artifacts\research\tiingo-iex-r1-representation-integration-v1\r1-cuda-20260810-r1\summary.json`.
  It records one non-promoting runtime appointment only: no holdout spend,
  source-derived weights, model selection, predictive result, KIS input, or
  Paper input. Its lineage cannot receive follow-on allocation by implication.
- The completed Granite TTM R1 structural smoke used one bounded appointment
  and released it. It is runtime compatibility evidence only, not a predictive
  campaign or a reason to reserve GPU capacity.
- The reattached Chronos-T5 Tiny R4 CUDA diagnostic is a completed source-local,
  non-promoting zero-shot probe, not an open allocation or predictive campaign.
  Its fixed zero-return baseline was not surpassed, so it releases no follow-on
  GPU work without a distinct eligible contract.
- Five historical frozen contracts are now terminally reconciled as
  `non_promoting_abandoned`: four
  `norgate-broad-target-free-representation-v1` records and one
  `profiled-mtf-flat-mlp-runtime-smoke-v1` record. The immutable source-safe
  reconciliation receipt is
  `D:\thericher-v2\model-artifacts\research\campaign-custody-reconciliation\historical-frozen-outcomes-r1.json`
  (`sha256:8f93082e4cd5323e201c9a60bd1fb945ecc0850ed0fd79187ab52451c945a162`).
  No sealed evaluation, GPU appointment, model run, or promotion was reopened.
- Model artifacts and source-safe receipts remain external under
  `D:\thericher-v2\model-artifacts`; Git holds neither model weights nor raw
  market data.

## Appointment Contract

Before a GPU appointment, Engine Research must freeze:

1. dataset identity and source/availability limits;
2. target, chronological split, purge/embargo, and effective sample rule;
3. timeframe/window matrix and shared family budget when applicable;
4. costs, naive baseline, strongest kill test, compute stop rule, and artifact
   root; and
5. family lineage and sealed-holdout access status.

For development, source timing/finality limitations may be explicit assumptions;
they need not be mislabelled qualified to obtain a bounded appointment.
Missing information defers only that campaign. It never creates an operator
approval request or blocks CPU preparation, Data collection, or Execution.

## Allocation Rule

When the GPU becomes idle, allocate the first ready frozen campaign. Break a
real tie by independent replication or underrepresented hypothesis family, then
the shorter bounded job. Execution reliability/inference preempts research at a
safe checkpoint. Do not consume GPU for closed historical lineages, static
source controls, timing probes, or utilization-only training.

## Evaluation Custody

The external `research_campaign_custody` record retains campaign identity,
family lineage, GPU appointment, and sealed-evaluation spend without raw labels,
predictions, prices, weights, credentials, or broker data. Cross-track synthesis
is a new family and cannot reuse a sealed allocation or select weights from
previous results.

## Handoff

Reattach custody before a new appointment. Record only the current allocation,
result category, evidence pointer, and next eligible campaign. Historical GPU
and evaluation evidence remains in Git and external receipts.
