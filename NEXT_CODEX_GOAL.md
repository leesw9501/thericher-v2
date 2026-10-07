# Next Codex Goal

## Objective

Complete firstrate-cross-day-clock-continuation-development-v1: determine whether
signed recurrence across prior days at the same market clock adds post-cost value.
Use existing QQQ/SPY M1 data. This is not a reroll of the killed absolute
noise-band/current-day breakout, first30 momentum or TCN families.

## Frozen Design Before Values

FirstRate exact retained sources and NYSE schedule must be pinned. Use the
existing251-date plan: first160 TRAIN, one embargo, last90 comparison dates,
reported as first45/last45 and the continuous90-day path. Revised/seen
development only; no independent holdout, broker-fill or Paper-promotion claim.

Three fixed decisions10:00/12:00/14:00 ET. Entry next M1 OPEN, exit OPEN30
minutes later: E=C+1min, X=E+30min, historical returnOPEN(X)/OPEN(E)-1.
Each same-clock estimate is mean signed OPEN-to-OPEN return for
exactly20 prior scheduled NYSE sessions. No current/future values/support/
completeness can affect past feature eligibility. Select keys before inspecting
values. Known early-close geometry is explicit, never an imputed return.
Prior history with a nonexistent14:00 window is unavailable, never replaced
by an older available day; current nonexistent clocks are not scheduled.
Use only required windows, not future whole-session completeness filtering.
Missing past input yields scoped no-intent; missing future marks remain explicit
and cannot silently remove losing observations or become zero PnL.

Fixed long/cash rule enters when the mean exceeds10bps, the predeclared primary
5bps-side approximate roundtrip hurdle, not guaranteed exact fee coverage.
This threshold/window/slot is not selected from values.
Keep the same actions for1/2.5/5bps sensitivity; no fee-based action selection.
Controls: same20-day clock-pooled signed history with the same fixed filter,
unconditional same-clock long, cash and TRAIN-frozen activity/exposure-matched
constant allocations for same-clock and pooled policies respectively. Pooled
history is the same ETF/same20 dates/three clocks, never cross-ETF/current-day.
Matching uses TRAIN eligible active-slot fractions only, never payoff
optimization; distinguish exposure matching from beta/risk matching. Freeze
one common past-only control eligibility contract, without a future support mask.

Continuous shared capital, eachETF at most50% long, other sleeve stays cash when
ineligible/flat; no renormalization, shorts/leverage, independent funded sleeves
or daily capital reset. Intraday positions close at each declared exit.
Use actual traded-notional fees, entry/exit and existing analytical/local-paper
ledger semantics. Do not invent an approximate target-distance fee simulator.
Report shared daily NAV/log growth/global variance utility, turnover and exact
per-asset cashflow attribution without treating sleeves as separate capital.
Freeze exact matrix/cost/utility/availability/stop rules before outcomes.

Strongest primary5bps kill: positive shared net growth and utility increment
over cash, clock-pooled and TRAIN exposure-matched controls in BOTH comparison
halves; also report unconditional-long controls and exposure limitations.
Per-ETF/half cashflow attribution is descriptive, not a separate capital path
or a mandatory profitable-member gate for this fixed joint portfolio; do not
select/remove an ETF afterward. This narrows the independent review's proposed
four standalone kills to the stated shared-portfolio question before values.
Zero trades or one good period is not a profitable engine. No threshold/clock/
window/ETF rescue or reselection. One<=120-second CPU evaluation, zero
predictive fits/GPU allocation; no new runtime, model weights or data purchase.

## Disjoint Ready Packages

Data owns pure causal same-clock history/window joins and scheduled geometry,
focused future-value/support/completeness mutation tests, exact source metadata.
Do not parse/use FINRA for software/ML/trade prediction: official website Terms
Restrictions(m) conflicts with general free non-commercial catalog wording;
no overriding permission is retained. Preserve original bytes; only that
proposal is deferred, not research or Paper.
Source: https://www.finra.org/terms-of-use

Engine Research reuses FirstRate loaders, chronological plans, campaign registry
and ledger primitives; implement one compact bounded experiment and zero-refit
readback. Do not build another generic report/gate/worker framework. Independent
Validation reviews the frozen inputs/control/cost contract before actual values.

Execution independently reattests shared-capital/cost attribution. Existing
corrected-account SPY strategy/shared10-percent virtual basis continue under
their current owner; no substitute request, identity reset or budget expansion.
Data inspects the existing owned04:24 KST head opportunity only through the exact
offline current chain after it exists. New head imagee6f74905... carries safe
token HTTP class/exactEGW00201 diagnostics; no extra provider call or pacing/
schedule change. Observer/head token contention is unproven: finalization times
do not establish POST ordering. Preserve next_due and continue research.

## Completion And Continuation

Completion: frozen source/code/contract, exact eligible/missing counts, bounded
evaluated/rejected or precise input-unavailable result, independent zero-refit
readback and ledger parity. Use focused feedback; company integration requires
AGENTS.md changed-path serial/eight-worker clean-root authority, Ruff/default+
research Compose and relevant overlay. Commit/push, replace this file with
exactly one material next company objective, refresh concise stateboards and
continue. Current independent review/Claude availability is evidence, not a
new approval gate; CLI-nonzero is not agreement.

Run C:\Users\Public\Documents\thericher-v2\scripts\start_next_codex_task.ps1.
Follow HANDOFF.md, AGENTS.md, RUNBOOK.md and active stateboards. Standing private
KIS Paper authority is unchanged. Never read/route KIS_LIVE_*, print credentials/
private account/order/market values, pay, accept unclear rights, expose a public
service or replace a major runtime without the reserved operator decision.
Data remains D:\market_data; artifacts D:\thericher-v2\model-artifacts.
