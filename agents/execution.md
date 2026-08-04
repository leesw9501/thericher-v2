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

The existing `thericher-kis-paper-quote-session` Windows task owned one current
virtual-Paper canary at 2026-08-04 23:35 KST and exited with Task Scheduler
result `0`. Its 23:48 KST monitor found no matching direct lifecycle receipt or
current runtime projection. This is neither a broker, lifecycle, no-intent,
fill, nor PnL result. Do not manually invoke the task, infer an outcome, or
create a second runner; the next task-owned opportunity is 2026-08-05 23:35 KST.

At 21:38 KST, the task's `IgnoreNew` concurrency and local Docker action were
reattested. Its `kis-paper-session` image was rebuilt from current source and
passed a network-disabled module-import check. The source-safe preflight also
passed 135 focused canary, quote, intent, lifecycle-projector, and dashboard
tests. These are local-contract facts, not a broker result or a reason to run
the task early.

The schedule installer now explicitly retains `RestartCount = 0` alongside
`IgnoreNew`. The current registered task already has that setting; this removes
reinstallation drift without restarting or changing tonight's task.

The host lifecycle projector and the independent
`validate_kis_paper_canary_lifecycle_evidence.py` validator now share a direct,
non-link receipt-path check and require the recorded `run_id` to match the
requested run. They emit only a sanitized lifecycle fact or categorical
`unavailable`; they never call KIS or load credentials. The focused reattestation
passed 82 tests. The accompanying Claude design challenge ended without a
verdict (`review_unavailable`), so source/test evidence preserves the existing
one-attempt contract rather than changing execution authority.

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
- the generic offline lifecycle validator accepts only a direct, non-link
  `paper_only` receipt whose recorded `run_id` matches the requested run and
  emits a sanitized categorical fact; terminally cancelled, cleanly reconciled,
  freshness-valid evidence remains the stricter downstream completion case.

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
- The local replay now derives FIFO realized-after-fee PnL only from closed
  `source: local_paper` lots. It deliberately excludes open-lot valuation and
  all KIS account/broker facts, so it is descriptive simulator accounting, not
  a fill-quality, profitability, model, or execution-risk input. The associated
  Claude request returned unrelated stale task text rather than its requested
  verdict; record `review_unavailable` and rely only on the local contract tests.
- The current source-free Claude falsification check returned
  `supported-with-limits`: virtual-host pinning, pre-submit durable intent,
  fresh account/quote reconciliation, exact-intent unknown-outcome recovery,
  and dashboard route isolation remain intact. A single canary may retain
  sanitized filled/remaining quantity or position state, but maps no price,
  cost, valuation, or model outcome. It is execution evidence only, never a
  fill-quality, PnL, profitability, or model result.
- The resumed 2026-08-04 offline reattestation passed 137 canary, intent,
  quote, receipt, lifecycle-projection, dashboard, and schedule tests. This
  verifies deterministic local contracts only; it is not a current broker
  outcome or a substitute for the task-owned lifecycle receipt.
- The host lifecycle projector additionally has explicit valid-evidence and
  missing-evidence CLI contracts; 97 focused canary/quote/lifecycle tests pass
  without broker or credential access.
- The Compose isolation test now scopes `kis-paper-session` to its immediate
  `kis-paper-daily-backfill` boundary and requires exactly one `--execute`.
  Later profile services can no longer mask a canary preview-path regression.
- Fresh `ResearchDecisionReceipt` objects now carry opaque commitments to the
  proposal's normalized instrument, market, and decision class; local Paper
  also commits its exact target exposure. Each route recomputes the commitment
  it needs before preparation, so a matching lineage reference alone cannot
  redirect a receipt to another symbol or target. Old receipts remain readable
  for replay evidence but return a scoped no-intent on both Paper routes.
- `daily-spy-head` and `daily-spy-session` use explicit Monday--Friday KST
  schedules. This aligns same-date Eastern sessions without changing route,
  sizing, cancellation, or service behavior.
- The prospective SPY cycle remains a data-dependent no-intent path until its
  own fresh completed-bar receipt exists. Timing observations are not Paper
  permissions.
- The same task-owned intraday-head dispatcher now invokes the pre-existing
  QQQ observed/provisional receipt route immediately after successful
  collection, before slower observers consume its two-minute input-freshness
  budget. The route creates no new adapter, task, or authority: it reuses the
  local replay, fresh account/open-order and quote checks, virtual-host-pinned
  canary, exact-intent recovery, cancellation, and network-disabled validator.
  Its source-safe outcome remains execution evidence only, never a model,
  fill-quality, PnL, or profitability claim.

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
