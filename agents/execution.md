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
phase. Historical `outcome_unknown` records remain recoverable only through
their own reconciliation paths and do not block this distinct due attempt.

The canary contract is fixed:

- virtual host only: `openapivts.koreainvestment.com:29443`, HTTPS, no
  redirects, approved quote/account/order/cancel routes only;
- one fresh quote-derived SPY limit and one share, with quote age bounded and
  rechecked immediately before broker I/O;
- durable `intent_recorded` state before side effects and a shared lock across
  sibling runs;
- fresh account/open-order reconciliation before submit; a matching open order
  blocks a new submission, including partial fills or a different limit price;
- accepted flow uses `cancel_after_submit`; an exact unknown may resume only
  its acknowledged cancellation after proven-open reconciliation; and
- the offline validator accepts only `paper_only`, terminally cancelled,
  cleanly reconciled, freshness-valid evidence.

## Current Supporting Surfaces

- The loopback dashboard is read-only, credential-free, and has no broker
  action. Its schema-v3 account projection omits prices and order identifiers.
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
do not submit a replacement based on missing evidence. An unrelated historical
unknown never creates a global Paper hold.

## Handoff

After the task runs, reattach its source-safe runtime projection and matching
offline validator before interpreting the lifecycle. Record only result
category, reconciliation class, route isolation, evidence pointer, and next
recovery action. Historic execution evidence remains in Git and
`D:\thericher-v2\model-artifacts\execution`; the latest pre-current canary
session receipt is
`kis-paper-canary-session\paper-session-20260801T143501387961Z\evidence.json`.
