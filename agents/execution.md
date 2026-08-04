# Execution Agent Stateboard (페이퍼 실행 담당)

`AGENTS.md` owns policy and `NEXT_CODEX_GOAL.md` owns the company objective.
This is the current virtual-Paper execution projection, not an order log.

## Ownership And Hard Boundary

Execution owns deterministic sizing/risk, intent persistence, broker routes,
fills, positions, reconciliation, accounting, and emergency controls. It treats
model output as untrusted input. `local_paper`, `kis_paper`, and `kis_live` are
separate routes; local replay fills remain `source: local_paper`. Never read or
route `KIS_LIVE_*`.

## Current Objective: Virtual-Paper Lifecycle Canary

The existing `thericher-kis-paper-quote-session` Windows task owns one current
virtual-Paper canary at 2026-08-04 23:35 KST. It is `Ready` with one
Monday--Friday trigger. As of the latest safe inspection, no Aug. 4 canary,
canary-session, or validator receipt exists. Do not manually invoke or create a
second task.

The latest safe private-state inventory has no `submitted` or `cancel_started`
phase. Before a fresh quote, the session reattests only a prior matching
`SPY`/`AMEX`/buy/one-share canary in this private root. It resumes that exact
state's reconciliation or cancellation path; if ambiguity remains, only the
new matching quote session records `recovery_required` without a fresh quote or
order. Historical unknowns outside that exact scope do not create a global
Paper hold.

The canary contract is fixed:

- virtual host only: `openapivts.koreainvestment.com:29443`, HTTPS, no
  redirects, approved quote/account/order/cancel routes only;
- one fresh quote-derived SPY limit and one share, with quote age bounded and
  rechecked immediately before broker I/O;
- durable `intent_recorded` state before side effects and a shared lock across
  sibling runs;
- a prior matching pending canary is recovered before any new quote; recovery
  cannot create a fresh order and a remaining ambiguity is session-scoped;
- fresh account/open-order reconciliation before submit; a matching open order
  blocks a new submission, including partial fills or a different limit price;
- accepted flow uses `cancel_after_submit`; an exact unknown may resume only
  its acknowledged cancellation after proven-open reconciliation; and
- the offline validator accepts only `paper_only`, terminally cancelled,
  cleanly reconciled, freshness-valid evidence.

The at-most-one-intent statement is scoped to the existing single host-owned
state root and its one scheduled Docker runner. A copied/restored private
state directory, second state root, second machine, or out-of-band runner is
outside this canary contract; none is installed. This is a scope fact for this
task, not a general Paper hold.

## Current Supporting Surfaces

- The credential-free loopback dashboard cannot call a broker or submit an
  order. Authenticated local emergency and pause controls may change only their
  local control state; its schema-v3 account projection omits prices and order
  identifiers.
- The resumed 2026-08-04 offline reattestation passed 137 canary, intent,
  quote, receipt, lifecycle-projection, dashboard, and schedule tests. This
  verifies deterministic local contracts only; it is not a current broker
  outcome or a substitute for the task-owned lifecycle receipt.
- The host lifecycle projector additionally has explicit valid-evidence and
  missing-evidence CLI contracts; 97 focused canary/quote/lifecycle tests pass
  without broker or credential access.
- `daily-spy-head` and `daily-spy-session` use explicit Monday--Friday KST
  schedules. This aligns same-date Eastern sessions without changing route,
  sizing, cancellation, or service behavior.
- The prospective SPY cycle remains a data-dependent no-intent path until its
  own fresh completed-bar receipt exists. Timing observations are not Paper
  permissions.

## Recovery

An absent result before the worker runs is expected. A stale/missing account or
quote, live-host mismatch, duplicate order, or unresolved exact-intent outcome
rejects only that canary attempt. Preserve the source-safe categorical state;
do not submit a replacement based on missing evidence. An unresolved matching
prior canary is recovered before the next matching session; an unrelated
historical unknown never creates a global Paper hold.

## Handoff

After the task runs, reattach its source-safe runtime projection and matching
offline validator before interpreting the lifecycle. Record only result
category, reconciliation class, route isolation, evidence pointer, and next
recovery action. Historic execution evidence remains in Git and
`D:\thericher-v2\model-artifacts\execution`; the latest pre-current canary
session receipt is
`kis-paper-canary-session\paper-session-20260801T143501387961Z\evidence.json`.
