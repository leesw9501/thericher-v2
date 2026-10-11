# Next Codex Goal

## Objective

Complete kis-peer-relative-momentum-entry-development-v1: test whether removing
prior peer-market movement from stock ranking improves fixed-five selection.
Workdir C:/Users/Public/Documents/thericher-v2.
A=D:/thericher-v2/model-artifacts; M=D:/market_data.

Prior105 CLOSED/rejectedaa330c36.../result43e5ad42.../outcomea66484b4....
One CPU fit spent;27of30 pass,3 DEV DD-versus-matched failures. Positive return
improvement does not erase that frozen rejection. No105 cutoff/model rescue.

## One Fixed Intervention

Use the SAME512 identities, old800/later71, prior21 completed bars, DEV15/later9
cohorts and all130 marks. No new universe, acquisitions, dates, windows or models.
Nearest sector-relative study used4ETFs/126-return lookback/21-session rebalance;
G92 changed covariance allocation. This study changes stock-level ranking,
not those policies or105 loss veto. Bounded nearest audit, not global novelty.

Freeze eligible peer pool at each prior CLOSE, including existing>=128 and
>=64 added support. Compute20 float64 CLOSE-to-CLOSE log returns; for stock i,
peer return is the equal mean of OTHER eligible names on the same20 dates.
Beta=covariance(de-meaned stock,peer)/variance(de-meaned peer), with the common
normalization cancelling. Exact zero denominator gives beta0; no epsilon,
clipping, search, future returns, self inclusion or coverage-selected cohorts.
Score=sum(stock returns)-beta*sum(peer returns). DO NOT subtract the fitted
intercept or sum fully demeaned residuals: that would trivially sum to zero.

Reuse original top10/ordinal ties, inverse-vol/gross<=.50/name<=.10/triangle<=.08
and fixed proxy>.003 semantics, changing only ranking score. Freeze both raw
plain and residual entry weights before prices. Common G=min(their gross);
downscale BOTH paired baskets to G before next OPEN and new quantity freeze,
never increase caps or resize after seeing OPEN. Keep raw rule as another arm.
Common gross is not equal realized risk or market neutrality; no hedge/short.
Record prior beta/concentration and analytical estimator counts separately from
predictive training. Nonfinite selected statistics/support fail that comparison.

Arms residual_common, momentum_common, rule_unscaled, cash:24tables at5/10/20bps
per-side actual legs. q=predeclared prior weight/(entryOPEN*1.001), fixed initial
capital, forced OPEN(e+5), sell-before-buy, all cash-tail daily CLOSE marks.
Selected missing context/payoff for either original basket cannot be censored
by matching, cash or a later substitution. No reinvestment/cash repair/reentry.
Uresidual>all3controls and DDresidual<=momentum_common/rule_unscaled in BOTH
blocks at ALL costs:30 fixed conjunctions. Failure ends this bounded mechanism;
no window/beta/model/threshold/cost rescue. Seen samples remain seen.

## Owners And Completion

Engine owns nearest-source/finite recipe, causal peer kernel and small worker
delta. Execution independently owns prior-common-gross/quantity replay parity.
Data standby for concrete support/clock defects; no new data or quality gate.
Parent integrates, owns actual Docker/Git and original clock. Infra invoked for
concrete ABI only, reusing frozen105 transport/catalog rather than a new platform.
Temporary Validation receives frozen source and actual aggregates, never tunes.
One CPU numerical runtime<=600s,2threads/4GiB,0 predictive fits/CUDA/weights/
holdout/retry. Analytical beta estimation is explicit, not concealed training.
Freeze science/source/custody before numerics. Source/SYN fit0/market mounts0;
numerical exactly four existing market files RO; fresh outputs only under A.

Done: one exact24-table comparison or linked duplicate/input-unavailable/
technical-failed closure, exact runtime/cleanup and unchanged-source evidence.
Claude next direction supported-with-limits at105 parent/claude-next/
claude-dual-result-outcome.json, completed2026-10-11T14:00:00Z; challenge actual
interpretation before reliance. Factor-decomposition source inspiration:
https://math.nyu.edu/~avellane/AvellanedaLeeStatArb071108.pdf
NOT its PCA/ETF mean-reversion, market-neutral or published-performance replica.

No credentials/KIS/provider/account/order/scheduler changes, downloads, paid
commitments or live behavior. Existing13 owners/shared10%basis/pending identities
unchanged. Data M/artifacts A/15% D: floor; no market or global approval wait.
Focused tests plus exact-source authority reattachment for external-only work;
changed shared source follows AGENTS.md. Ruff/three sample Compose, stateboards/
HANDOFF, verify/commit/push, ONE next goal and continue.
