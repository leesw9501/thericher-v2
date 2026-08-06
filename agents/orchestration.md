# Codex Orchestration Stateboard (제품개발 총괄)

`AGENTS.md` owns policy and `NEXT_CODEX_GOAL.md` owns the company objective.
This is a current cross-lane projection, not a role queue or history ledger.
Git and external artifacts retain historic receipts and implementation evidence.

## Company Objective

`intraday-head-capture-receipt-binding-v1` will make the existing
intraday-head terminal receipt bind only its same-run source-safe
session-capture cumulative-coverage receipt. This advances the data collection
loop by letting offline reattachment report a categorical coverage fact without
reading raw bars or choosing a newest artifact.

The completed 04:24 KST receipt has collection `exit_zero`, QQQ `no_intent`,
and offline validation `unavailable`; it ends
`recovery/prospective_validation_payload_unavailable` with Scheduler result
`20`. It has no broker, fill, PnL, alpha, or model result. Claude's fresh
falsification check is `supported-with-limits`: bind run identity, preserve
legacy receipts as unbound, and prevent stale pointer rollback. It grants no
data qualification or execution authority.

## Ready / Owned / Due

| Work | Owner | Resource | Current fact and next action |
| --- | --- | --- | --- |
| Intraday M1 head collection | Data | Existing `thericher-kis-paper-intraday-head` task | Exact 2026-08-07 04:24 KST terminal receipt is `recovery/prospective_validation_payload_unavailable` with Scheduler result `20`: collection `exit_zero`, QQQ `no_intent`, validation `unavailable`. The task owns 06:20 KST; no manual run or duplicate collector. |
| QQQ observed/provisional route | Data / Execution | Existing downstream profile service | It consumed fresh local input and emitted its exact `no_intent`; no Paper lifecycle, fill, PnL, alpha, or model result follows. |
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
`not_observed`. The current terminal contract also cannot prove that a
cumulative-coverage receipt belongs to the same run. The next objective fixes
that provenance seam; neither fact supports a frozen predictive campaign, GPU
allocation, model promotion, or Paper input. The GPU being idle is therefore
correct rather than a dispatch failure.

## Current Reversible Improvement

Keep this file as a concise projection of `ready / owned / due` facts. Put
history in Git and immutable external receipts, and keep lane-specific detail
in the owning stateboard. This shortens safe handoffs across Data, Engine
Research, Execution, and temporary Validation without creating an approval
gate, a second goal, or a new worker.

## Current Recovery Action

Data owns the existing intraday-head task's 06:20 KST invocation. The next
objective may add only the source-safe receipt-binding chain, including
run-identity, legacy-unbound, and pointer-rollback controls; it must not
manually invoke KIS or reinterpret any result as an account, fill, PnL, alpha,
or model fact. If the task runs while that work is active, reattach only its
exact bound terminal evidence and continue every non-conflicting ready package.
