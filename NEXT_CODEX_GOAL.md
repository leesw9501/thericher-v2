# Next Codex Goal

## Objective

Complete kis-stock-five-session-paper-attribution-preparation-v1: prepare a
small reusable owner-local accounting projection for the already-owned five-
session Paper cohort, with explicit daily-close and fee evidence availability.
It improves Paper trading and PnL attribution, not a report or permission gate.

A=D:/thericher-v2/model-artifacts; M=D:/market_data.
Goal86 closed8ecd02b9... at A/research/kis-stock-five-session-catboost-development-v1/
integration-evidence.json: actual3GPU+3tree+3ridge/384iterations, fixed CatBoost
candidate rejected, no model/Paper replacement. CUDA runtime is available.

## Role Packages And Bounds

Execution composes existing cohort/custody, cumulative-fill and exact Fraction
portfolio gross-PnL APIs. Add only missing typed per-close state/mark/fee inputs
and a pure projection; reuse existing parsers, no new ledger or wrapper family.
No file/network/credential I/O, native observer, scheduler, service, model fit,
holdout, broker order or changed execution-risk behavior in this preparation.
In particular, native observe() may recover orders and is not a passive reader.

Bind exact cohort/calendar/owner/source and original shared budget basis. Use
an actually retained state at each close; final state cannot reconstruct earlier
quantity or fill availability. Preserve chronological uncertainty. Validate
close timestamp/instrument/source, cumulative fill deduplication, owner-local
cash/inventory and real fee availability. Missing a held close mark makes that
valuation unavailable, never zero/interpolated/censored. Unobserved fees remain
unknown; never present orderable funds as settled cash or gross as net PnL.
Historical closed-owned quantity is not current broker reconciliation proof.
Do not adopt foreign same-symbol inventory or silently reallocate another owner.

Engine independently reviews valuation/accounting semantics without tuning a
model. Data supplies calendar/source-contract synthetic facts only. Parent owns
API integration, focused/authoritative verification and Git. Keep the package
small: one projection module, focused tests, only required export wiring; do
not replace the existing portfolio/fill/cohort implementations. No new report,
worker, scheduler, dashboard, framework, public service or approval process.

## Completion And Strongest Kill

Produce reusable pure source, focused source-linked tests and one independent
readback covering partial/unknown entry and exit, repeated cumulative snapshots,
foreign same-symbol ownership, restart, five close states, held missing marks,
fee availability and chronology. A source-safe payload contains only categorical
status/counts, not identifiers, raw prices/amounts or private state.

Strongest kill: combine foreign inventory, repeated cumulative snapshots,
unknown/partial exit, one missing held close and absent fees. It must not invent
flatness, double fills, adopted quantity, censored marks or positive net profit.
Incomplete attribution remains scoped unknown and cannot pause recovery or
create a submission gate. Synthetic success is engineering preparation only,
not actual Paper fills, current inventory, provider finality or net profit.

Preserve job80012e77.../plan507ffbb6.../cohort387ee5f6..., original shared10%
basis/other owners/unknown SPY/exact pending. Entry Oct12 22:30KST, recovery
22:40, fifth EXIT Oct17 04:50KST/recovery05:00 remain exclusively owned; no
manual invocation, substitute order, basis/identity reset or schedule expansion.
Existing b860/ab65 due facts are unchanged. Never read KIS_LIVE_*.

Ask Claude to challenge materially changed accounting/recovery semantics;
ordinary pure implementation/tests do not need repeated review. The G86 next-
direction reviewb5d17be2... supported-with-limits is not runtime closure.
Run changed-path serial tests, full clean parallel authority if tracked runtime
changes, Ruff and three sample Compose configurations. Exact unchanged-source
authority may be reused only as AGENTS.md permits. Refresh current stateboards,
verify, commit/push, replace this file with exactly ONE material next objective,
and continue ready work without foreground waiting for Monday's market.
