# Codex Orchestration Stateboard (제품개발 총괄)

`AGENTS.md` owns policy and `NEXT_CODEX_GOAL.md` owns the one active company
objective. This file is the current cross-lane projection only. Git,
`HANDOFF.md`, and immutable external receipts retain history.

## Active Company Objective

`kis-paper-d1-prospective-observation-pair-result-v1` must independently
reattach one complete QQQ/SPY D1 two-observation result from the installed
task-owned observer. Its only permitted classifications are
`measurement_only_match`, `input_unavailable`, and `disqualified`. Even a
match is Data-only and cannot qualify a dataset, feature, model, GPU campaign,
Execution input, Paper order, or live behavior.

The validated current pointer is only the completed-session 2026-08-31
first-stage `input_unavailable/first_observation_target_failure` receipt
(`sha256:a630aa9a342553b1162c057f6590a5e5dd493b306c6998ef6cf6aedbef9c87a4`).
It has no first-receipt binding or later receipt, so it is not a pair result.
The reader-owned next due is `2026-09-01T23:15:00Z` (08:15 KST on 2026-09-02).

## Ready / Owned / Due

| Work | Owner | Resource | Current fact and next action |
| --- | --- | --- | --- |
| D1 prospective pairing | Data / Infra Capability | Installed `thericher-kis-paper-d1-prospective-observation-pairing` task | The task owns 08:15 and 23:20 KST Tuesday-Saturday runs. It is `Ready`; Task Scheduler exit is not outcome evidence. Do not invoke it, Docker, KIS, the collector, or a scheduler manually. |
| D1 outcome reattachment | Codex / temporary Validation | Hash-bound pointer, immutable receipts, host-only offline reader | A validated later receipt is required before classification. Then obtain Claude's falsification-first verdict, run goal-boundary verification, commit/push, and replace `NEXT_CODEX_GOAL.md`. |
| D1 safe reader | Data / Infra Capability | `scripts/read_current_kis_paper_d1_prospective_observation_pairing_outcome.py` | Complete and pushed. It accepts the model artifact root or exact pairing subroot, emits only categorical outcome fields, immutable receipt binding, and evidence pointer, and has no task, Docker, KIS, credential, or cache-write path. |
| Intraday coverage monitor | Data | Existing task-owned intraday-head worker | Separate source-safe monitoring remains owned by its task. It does not block or qualify this D1 objective. |
| Virtual-Paper lifecycle | Execution | Existing quote-session task and receipt reader | The 2026-09-01 23:35 KST exact run is `not_submitted / reconciliation_unavailable` with `submit_response_category: not_observed`; it remains separate from D1 pairing and is not a broker-submission, fill, PnL, or model/PnL promotion path. |
| Predictive research / GPU | Engine Research / Research Steward | RTX 4090 | No input-qualified frozen predictive campaign is ready. The GPU remains unallocated; do not manufacture training for utilization. |
| Local Paper dashboard | Execution / Infra Capability | Existing loopback-only web service | Available for sanitized runtime projections. It deliberately has no artifact mount, so D1 receipts stay on the host-only reader path. |

## Resource Conflicts And Current Improvement

There is no active shared-resource conflict. External task due times belong to
their named workers and do not create foreground waits or general Data,
Research, or Execution holds.

The current reversible improvement is the source-safe D1 reader CLI added in
`8a9d6a1` and its pairing-subroot compatibility in `a121ac1`. It replaces ad
hoc reattachment snippets without widening the observer's route, cache, or
credential surface.

## Blocked-Goal Alternatives

The active objective has no remaining compliant foreground package until an
external task-owned observation changes the immutable evidence. This is an
external dependency, not an operator approval or general project hold.

1. **Data, scheduled first observation:** the 08:15 KST task invokes the
   existing read-only D1 observer. Completion evidence is a hash-bound first
   receipt. A missing target, invalid state, or unavailable input stays scoped
   to that session; recovery is the worker's own next due, not a manual retry.
2. **Data, scheduled later observation:** only a valid first binding enables
   the 23:20 KST comparison. Completion evidence is a later receipt bound to
   the same source contract, session, targets, first receipt, and first hashes.
   Any mismatch disqualifies that exact session.
3. **Codex / temporary Validation, offline integration:** a validated later
   receipt triggers the existing offline reader, a concise Claude
   falsification-first review, required full verification, commit/push, and
   one next company objective. The kill test is any failed receipt binding or
   source-contract mismatch.

Claude's block-classification check is `review_unavailable` because its OAuth
session expired. This is not a substantive verdict and does not recreate a
manual approval gate.

## Recovery Rule

Do not foreground-poll or create another D1 scheduler. The existing one-shot
follow-up reattaches the result after the owned later opportunity. A missing or
incomplete receipt remains unknown or session-scoped; it never pauses another
correctly scoped private, non-live lane.
