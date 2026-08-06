# Codex Orchestration Stateboard (제품개발 총괄)

`AGENTS.md` owns policy and `NEXT_CODEX_GOAL.md` owns the company objective.
This is a current cross-lane projection, not a role queue or history ledger.
Git and external artifacts retain historic receipts and implementation evidence.

## Company Objective

`intraday-head-0424-source-safe-followup-v1` will reattach one exact outcome
from the existing 2026-08-07 04:24 KST intraday-head task. It advances the data
collection loop by preserving only receipt-bound categorical collection,
coverage, QQQ-session, validation, terminal, and Scheduler facts. It must not
manually call KIS, duplicate a task, infer raw-data quality beyond the receipt,
or reinterpret the result as a Paper lifecycle, fill, PnL, alpha, or model
claim.

The completed same-cycle allocation helper is pure caller-ordered model-side
plumbing: unique identities and one snapshot are required, only accepted
enters consume simulated capacity, and unexecuted exits do not release it.
It has no data, model, KIS, Paper, state-reservation, or order surface. Its
focused tests and authority suite passed; Claude's architecture check timed out
as `review_unavailable`, not agreement or a hold.

## Ready / Owned / Due

| Work | Owner | Resource | Current fact and next action |
| --- | --- | --- | --- |
| Intraday M1 head collection | Data | Existing `thericher-kis-paper-intraday-head` task | Exact 2026-08-07 02:28 KST result is `recovery/collection_exit_nonzero` with Scheduler result `1`; QQQ session and validation were `not_applicable`. The task is `Ready` for its owned 04:24 KST invocation; no manual run or duplicate collector. |
| QQQ observed/provisional route | Data / Execution | Existing downstream profile service | It consumes only a fresh local retained input after a successful collection and can emit a scoped no-intent. The latest collection recovery created no QQQ session, Paper lifecycle, fill, PnL, alpha, or model result. |
| SPY D1 stability observation | Data | Existing virtual-Paper task | The first exact receipt is `stable`, which is not provider finality or consumer qualification. Its next owned observation is 2026-08-07 23:15 KST. |
| Quote-session lifecycle canary | Execution | Existing virtual-Paper task | The exact 2026-08-05 session reattaches as `cancelled/clean` and attribution-ineligible. It is execution evidence only; its next owned opportunity is 2026-08-07 23:35 KST. |
| Existing scoped Data workers | Data | Installed forward, prefix, and D1 workers | Cursor, pagination, and forward observations remain worker-owned and non-promoting. A categorical recovery or source limit closes only its named cache or cursor; do not dispatch a duplicate manual route. |
| GPU allocation | Research Steward / Engine Research | RTX 4090 | No frozen input-qualified predictive campaign is ready. CPU preparation can proceed, but GPU work requires the declared dataset, target, split, timeframe/window matrix, costs, baseline, artifact root, and stop rule. |
| Same-cycle target allocation | Engine Research | Pure in-process model helper | Completed with caller-order, shared-snapshot, no-exit-release, no-I/O contract tests. It remains plumbing only, not opportunity selection, alpha, a model result, or a Paper/broker path. |
| Daily operating review automation | Codex | Existing desktop automation | Prompt-only alignment completed: it now uses current stateboards and the clean-root parallel authority helper. Its daily 08:10 schedule and all non-prompt fields remain unchanged; it is not a new worker or approval gate. |

## Current Bottleneck

Fresh causal KIS-reconstructible input coverage is the product bottleneck. The
exact QQQ/NAS and SPY/AMS M1 cursor scopes contain only 21 shared complete
regular-session windows, and provider decision-time availability remains
`not_observed`. That is sufficient only for source-local non-promoting
mechanics/feature preflights, not a frozen predictive campaign, GPU allocation,
model promotion, or Paper input. The GPU being idle is therefore correct rather
than a dispatch failure.

## Current Reversible Improvement

Keep this file as a concise projection of `ready / owned / due` facts. Put
history in Git and immutable external receipts, and keep lane-specific detail
in the owning stateboard. This shortens safe handoffs across Data, Engine
Research, Execution, and temporary Validation without creating an approval
gate, a second goal, or a new worker.

## Current Recovery Action

Data owns the existing intraday-head task's 04:24 KST invocation. If it yields
another categorical recovery, reattach only its exact source-safe receipt and
continue every non-conflicting ready package; do not manually invoke KIS or
reinterpret the result as an account, fill, PnL, alpha, or model fact. The
next company-goal boundary should reassess the stale daily operating-review
automation and other ready work from this projection.
