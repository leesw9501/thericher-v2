# Next Codex Goal

## Objective

Complete kis-causal-risk-allocation-development-v1: actually compare one causal
monthly SPY/TLT/GLD minimum-variance allocation with common capped ex-ante risk
budgets against inverse-volatility and equal-third controls. Produce continuous
capital, cost, risk and utility evidence, not another preparation-only goal.
This is a distinct economic hypothesis, not a rescue or rescore of closed models.

Run C:/Users/Public/Documents/thericher-v2/scripts/start_next_codex_task.ps1;
read HANDOFF.md, AGENTS.md, RUNBOOK.md and active stateboards. Parent owns
contract/runtime/custody/Git; Engine owns the small worker/tests; Data owns
past-source geometry; Execution reviews sizing/carry/cost semantics; invoke
Validation only after frozen actual outputs. Disjoint work may run in parallel.

## Input And Source

A = D:/thericher-v2/model-artifacts; M = D:/market_data.
Use unchanged A/research/kis-cross-asset-d1-input-foundation-v1/input/cross-asset-d1-input-20261008-v1/input-commitment.json,
SHA02dcc0007a5aa2804c4b0ce497dfb51e21387122869f1ef90f539d597158e516:
three ETF1288 shared dates2021-08-20..2026-10-07,136 bindings/140 files.
Calendar A/data/kis-cross-asset-d1-input-foundation-v1/calendar-nyse-20070821-20261007-v1.json,
SHAd2dab6f2ab27a7439ed4be91bacefc68b04908d0b3b7d509e4a2b19925a42721,
NYSE/pmcal5.4.0. Raw MODP0 price-only; splits/dividends/TR/PIT/finality/
decision-time availability unverified. No Tiingo, Norgate, new dataset or
extended SPY/GLD OC splice. Existing Paper owners and shared10-percent basis
are independent and unchanged. Never read KIS_LIVE_*.

Mechanism inspiration, not a replication or KIS ETF edge claim:
https://www.anderson.ucla.edu/documents/areas/adm/Volatility%20Managed%20Portfolios.pdf
(Moreira/Muir2015-11-23 draft, independent Engine retrieval2026-10-08 03:10:23UTC)
and https://onlinelibrary.wiley.com/doi/10.1111/0022-1082.00327
(Fleming/Kirby/Ostdiek2001 covariance-allocation abstract). No public code,
weights or data rights adopted. Do not copy unconditional/full-sample volatility
normalization. Our10-percent cap/thresholds are fixed engineering choices.
Claude challenge one1.026s cli_nonzero_other/review_unavailable, not agreement:
A/research/source-discovery/claude-kis-causal-risk-allocation-20261008-v1.json.
Independent Engine/Execution source checks continue without an approval wait.

## Frozen Recipe

Freeze source/input/runtime/contract/custody before actual numeric preparation.
DEV valuation dates2024-01-02..2026-09-30,689 daily marks:252 in2024 and437
in2025-Jan..2026-Sep. All are seen development, not a fresh holdout. Exactly33
monthly first-session OPEN decisions, previous scheduled CLOSE, full schedule.
No window/asset/period/cadence/seed search or missing-date deletion.

At each decision select exactly253 prior scheduled CLOSEs and252 simple daily
returns in SPY/TLT/GLD order. Decimal50 ratios then finite float64; population
covariance, mean subtraction/ddof0. Reuse the existing pure
joint_portfolio_covariance._population_covariance and
tiingo_quarterly_joint_allocation.minimum_variance_weights; no Tiingo I/O or
adjusted Bar wrapper. Pass UNSHRUNK covariance to the existing solver because
it internally applies0.9*C+0.1*diag(C). Reuse its fixed simplex-face solution,
1e-45 weight quantum/residual rule. No new framework or duplicated optimizer.

Policies: candidate minimum variance; inverse volatility; equal thirds; cash;
uninterrupted equal-third buyhold. For inverse volatility use the same shrunk
diagonal; a zero diagonal allocates equally among zero-variance assets; all
zero gives equal thirds. Normalize with the existing finite weight quantum.
For the three monthly allocations use the SAME shrunk covariance and cash cap:
vol=sqrt(252*w'C_shrunk*w), exposure=min(1,.10/vol), zero vol=>exposure1.
Multiply each sleeve under Decimal50; exact residual cash calculated at enough
precision for Fraction(weights)+cash==1. No leverage, short, outcome-derived
volatility normalization or exposure-matching to observed results. The same
cap is not identical attained risk when exposure cannot exceed1: retain attained
forecast risk/cap-binding diagnostics; never call this risk-matched alpha.

Seal all33 actions/policy before forward payoff calculation. Canonical existing
three_asset_nav.replay: NAV1 once/policy/cost, rebalance at monthly first OPEN,
carry quantities/overnight gaps through month and view boundaries, final CLOSE
exit only. No monthly liquidation, fresh-capital views or five-day cash tail.
Every scheduled daily mark, Decimal50 HALF_EVEN, fees on actual traded notional.
Side costs2.5/5/10bps; five policies x3 costs x2 views =30 cells. Buyhold only
initial entry/final exit is an opportunity-cost reference, not mandatory wealth
dominance. Cash earns0; no fabricated interest/dividend/fee settlement.

Use utility252*(mean daily log return -5*population variance). Report daily-log
realized annual volatility sqrt(252*variance), growth, actual-notional turnover,
costs and drawdown. Drawdown uses the running NAV peak from the single initial
NAV1 across both views; do not reset it at the view boundary.
Original strongest kill at10bps in BOTH views: candidate positive net growth
over cash; utility greater than BOTH common-cap controls by>.001; realized
annual log volatility<=.15; running-peak maximum drawdown<=.25. These thresholds
are engineering choices, not cited paper findings. Lower exposure alone is
not skill. Failure closes this exact recipe; no threshold/window/period rescue,
holdout/depth/ensemble/Paper/live qualification or rescoring prior failures.

## Execution And Completion

Use existing image sha256:d6b43213ee3877653e3c1e79c7238fb5caa71241abf238838fa0c3332cf4f039,
Python3.12.14/pmcal5.4.0/numpy2.5.1. CPU synthetic smoke first, then one shared
120-second actual source/action/evaluation allowance, CPU2/memory2GiB.
Network-none/source+input RO/own output A/research/kis-causal-risk-allocation-development-v1
only; all-RO exact30-cell replay with zero refits/search/writes. No model fits,
GPU allocation or public checkpoint is needed for this statistical mechanism;
do not train a dummy job for utilization. Preserve categorical bounded faults.

Reuse source loader/calendar/binding, solver and shared ledger. Keep the worker
small; don't create another platform/report/gate or independent goal file.
Independent Validation checks frozen actual kill/cashflow/source binding, then
close non-promoting custody. Completion requires actual outcome/replay/closure,
not only code/smoke. No provider/account/order/task/schedule/dashboard change
is required. Existing Paper authority and owned jobs never wait on this study.

Run changed-path serial, clean-root8-worker authority, Ruff and three sample-env
Compose configurations. Commit/push owned integration, refresh current
projections, replace this file with exactly one material next company objective
and CONTINUE until reserved operator authority or a genuine company block.
