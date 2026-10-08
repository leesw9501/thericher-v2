# Next Codex Goal

## Objective

Complete kis-cross-asset-daily-risk-development-v1: fit a CPU HGB and a small
CUDA attention classifier on KIS-native SPY/TLT/GLD past daily moves, then
compare their five-session basket/cash policies and fixed probability blend against
four fixed controls. Produce actual model and continuous-capital evidence,
not another preparation-only objective. No live or research-to-Paper promotion.

Run C:/Users/Public/Documents/thericher-v2/scripts/start_next_codex_task.ps1;
read HANDOFF.md, AGENTS.md, RUNBOOK.md and active stateboards. Parent owns
contracts/runtime/custody/Git; Data owns pure daily adapter, Engine owns models,
Execution owns analytical cost/carry review; Infra and Validation are bounded
invocations. Disjoint packages may run in parallel.

## Exact Input And Hypothesis

A = D:/thericher-v2/model-artifacts; M = D:/market_data.
Use unchanged A/research/kis-cross-asset-d1-input-foundation-v1/input/cross-asset-d1-input-20261008-v1/input-commitment.json,
SHA02dcc0007a5aa2804c4b0ce497dfb51e21387122869f1ef90f539d597158e516:
1288 shared dates2021-08-20..2026-10-07/39 chunks/136 bindings/140 files.
NYSE calendar A/data/kis-cross-asset-d1-input-foundation-v1/calendar-nyse-20070821-20261007-v1.json,
SHAd2dab6f2ab27a7439ed4be91bacefc68b04908d0b3b7d509e4a2b19925a42721,
pmcal5.4.0. Exact source-grade raw MODP0 price endpoints; corporate actions/TR,
PIT/finality/decision-time availability and ideal fractional fills unverified.
Old monthly2008-start proposal stays unavailable; this is a distinct family,
not silent split shortening. Extended SPY/GLD OC history cannot be spliced in.
No Tiingo, Norgate, FRED, FINRA, new weights or uncertain-rights substitution.

Hypothesis: joint past moves contain information about a next-five-session
costed balanced-basket loss useful for fixed five-session basket/cash decisions.
The TRAIN proxy is not hedge-causality or direct utility. Its OPEN->fifth CLOSE
holding/exit path matches candidate evaluation; no daily-overwrite shortcut.
Primary-source motivation: https://www.bis.org/publications/correlation-equity-and-bond-returns
describes changing stock/bond relationships, not proof of this classifier's edge.
Implementation APIs re-retrieved2026-10-08:
https://scikit-learn.org/1.9/modules/generated/sklearn.ensemble.HistGradientBoostingClassifier.html
and https://docs.pytorch.org/docs/2.7/generated/torch.nn.TransformerEncoderLayer.html.
Freeze the entire contract/source/input/runtime/custody before actual labels,
outcomes or fits. Source-only review is not a predictive result.

## Frozen Finite Recipe

Dates refer to ENTRY sessions, decision at the immediately preceding scheduled
CLOSE. TRAIN2021-12-01..2023-12-20; exclude entry datesDec21..29 as embargo.
Last TRAIN label marksDec20/21/22/26/27, before DEV. DEV0 entry2024-01-02..
2024-12-31; DEV1 entry2025-01-02..2026-09-30. No gap deletion, older fallback,
outcome-selected sample or in-sample TRAIN economic performance claim.

Pure daily adapter: exact64 CLOSEs/63 OPENs, six asset-major channels x63
(SPY/TLT/GLD each close-to-close then open-to-close log returns), ending at
decision CLOSE. Preserve existing MONTH-boundary helpers/guards unchanged.
Freeze implemented Decimal50 log-price differences (ln CLOSE_b - ln CLOSE_a;
ln CLOSE - ln OPEN), not bit-identical Decimal ln(ratio). Bounded in-process
log cache changes no arithmetic, source eligibility or retained artifact.
TRAIN target first entry OPEN -> fifth scheduled CLOSE, finite equal thirds,
canonical actual-notional ledger5bps per side; factor below1 is loss. TRAIN-only
channel standardization/zero-variance divisor1; require30 observations/class
only for this fit. Contexts/5D labels overlap: report raw counts and disjoint
five-session block counts, never claim independent effective sample size.

Exactly one sklearn1.9.1 HistGradientBoostingClassifier fit: flattened378,
log_loss/100 iterations/.05 learning rate/max leaves3/depth2/min leaf20/L2=1,
seed101, no early stopping/class weighting/search. Exactly one Torch2.7 CUDA
attention fit:6->16 projection/fixed sinusoidal positions/one encoder/two
heads/FF32/GELU/dropout0/mean pool/one loss logit; float32, unweighted BCE,
full-batch AdamW lr.001/weight decay.01/512 final updates/seed101. No final
checkpoint selection or rescue. Fixed50/50 probability blend, no learned fuser.

Partition DEV valuation sessions from2024-01-02 into successive disjoint
five-session groups, without resetting at the DEV-view boundary. Predict only
group entries at previous CLOSE. Each candidate invests finite equal thirds iff
P(loss)<.5, otherwise cash; hold quantities unchanged, liquidate fifth CLOSE.
Final incomplete group (at most4 sessions) is cash, determined ONLY by frozen
calendar, not observed price support; no truncated holding or target.
Exact geometry:517 TRAIN entries/104 earliest-thinned non-overlapping5D labels
(not independent ESS);689 DEV marks split252/437;137 complete groups,
51/86 group entries; crossing groupDec30/31 2024-Jan2/3/6 2025. Last group
Sep18..24 2026; four cash-tail marksSep25/28/29/30. First required CLOSE
Aug31 2021/OPEN Sep1, last TRAIN labelDec20/21/22/26/27 2023.
Seal ALL DEV actions before DEV payoff evaluation; same actions at every cost.
Controls: cash, five-session balanced thirds, uninterrupted buyhold, constant basket
fraction equal to TRAIN non-loss fraction. Last is not exposure-matched to DEV;
classification class-prior control is separate, not an economic winner.
Seven policies x three side costs2.5/5/10bps x two DEV views =42 cells.

Candidate/balanced/null five-session roundtrips, no intermediate rebalance;
buyhold initial OPEN/final CLOSE only. NAV1 initialized ONCE per policy/cost;
inventory/cash/denominators cross DEV boundary even inside a five-session group.
Use complete daily marks/carry, not fresh-capital segment replays. Existing
Decimal50 ROUND_HALF_EVEN actual-notional ledger, no fresh monthly accounts.
Daily utility252*(mean log return -5*population variance). Original kill at
10bps in BOTH views: HGB positive growth and growth/utility greater than all
four controls by1e-10; attention/blend also beat HGB by1e-10. This is noncyclic:
HGB need not beat its alternatives. Failure closes this exact recipe; no new
threshold/window/seed/period/budget, holdout, replication or deployment claim.

## Runtime And Completion

One shared300-second family allowance covers actual preparation/two fits/
evaluation, not300s per member. CPU synthetic smoke first. Exact existing image
sha256:d6b43213ee3877653e3c1e79c7238fb5caa71241abf238838fa0c3332cf4f039,
Python3.12.14/Torch2.7.0+cu128/CUDA12.8/sklearn1.9.1. No framework replacement.
Steward freezes eligible custody and takes canonical exclusive GPU lease before
actual CUDA; parent hard deadline with invocation-bound exact container stop/
reap, lease released only after containment. Execution preempts at safe point.
Network-none/input+source RO; own results/checkpoints under A only. Trained
weights use safe tensor/known-source format, never untrusted pickle/custom code.

Exact all-RO replay uses frozen actions/results and reconstructs42 economic
cells with zero refits/search/writes; separately attest saved-model predictions
or their exact immutable binding without a new GPU campaign. Invoke independent
Validation only after frozen actual candidate outputs. Close custody on actual
completion or bounded failure; planned fits are not completed-fit evidence.

Claude concise falsification-first split/target/control/cost challenge is
review_unavailable at A/research/source-discovery/claude-kis-cross-asset-daily-risk-20261008-v1.json:
one .993s cli_nonzero_other, not agreement; don't repeat unchanged diagnosis.
This review preceded the pre-label five-session holding correction. Independent
Execution review found the original5D-target/daily-overwrite mismatch; parent
aligned holding/exit without changing a policy or adding an approval gate.
Independent exact review and other ready work continue. No provider/account/
order/task/schedule/dashboard change required. Existing private Paper10-percent
basis/identities/owned schedules remain independent; never read KIS_LIVE_*.

After actual result/replay/independent review/custody evidence, run changed-path
serial, clean-root eight-worker authority, Ruff and three sample-env Compose
configs. Commit/push owned integration, refresh current projections, replace
this file with exactly one material next objective and CONTINUE until genuinely
reserved operator authority or no ready package advances the company outcome.
