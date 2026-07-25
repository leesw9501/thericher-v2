# Execution Agent Stateboard

`AGENTS.md` owns policy and `NEXT_CODEX_GOAL.md` owns the company objective.
This is the current Execution projection, not a broker-event ledger. Detailed
private evidence remains under `D:\thericher-v2\model-artifacts\execution`.

## Ownership

Own deterministic order, fill, position, cash, reconciliation, accounting PnL,
risk controls, emergency controls, and KIS adapters. Treat model output as
untrusted input. Never introduce strategy logic or load arbitrary model code.

## Current Objective

Consume scheduled daily SPY outcomes only through their exact receipt-derived
identity and categorical observer/terminal facts. Under the current objective,
do not manually create an intent, submit a Paper order, or infer a fill, cancel,
or PnL from incomplete evidence.

## Current Runtime Facts

- The daily SPY head, quote-session, daily-session, and intraday-head tasks are
  installed and `Ready`; their 2026-07-25 prior runs have result `0` and no
  missed-run anomaly. The daily tasks own their normal 22:15, 23:35, and 23:50
  KST runs; intraday-head owns 00:35, 02:35, 04:35, and 06:20 KST.
- The latest completed daily session (2026-07-25) is `paper_only` /
  `no_intent` / `session_closed`. Its receipt reference did not yield an exact
  receipt-derived run identity, so its receipt observer and terminal-field probe
  were `not_attempted`. It is not evidence of a broker fill, cancellation,
  position change, or PnL.
- The current price route uses `AMS` for price endpoints and `AMEX` for the
  virtual order venue. The scheduled daily lifecycle does not auto-cancel a
  valid order; the standalone canary remains cancellation-oriented.
- The local operations console is credential-free and sees only sanitized
  projections. Its directional pauses are reversible operating controls, not
  approval or model-promotion gates.
- The intraday collector's legacy-candidate and orphan-recovery hardening is
  Data-only. It creates no Paper intent, account call, order, or lifecycle fact.
- Paper quote and daily-session tasks now have explicit battery and 90-minute
  non-overlap settings, but intentionally keep missed-run catch-up disabled.
  A late restored machine therefore cannot create an off-cadence Paper session.

## Binding Contracts

- `local_simulation`, `kis_paper`, and `kis_live` are separate routes.
  Simulated fills remain `source: local_paper`. `KIS_LIVE_*` is never
  readable or callable.
- Persist an exact durable intent before a broker side effect. Keep its stable
  receipt identity and side; reconcile an unknown exact submission outcome
  before retrying that same intent.
- A KIS Paper decision needs the existing deterministic route, fresh account and
  price proof, and the one-share target transition. Model evidence never bypasses
  these execution checks.
- Observer and terminal-probe outputs are categorical. Without authoritative
  completion evidence, terminal support remains unqualified and
  `pnl_status: not_observed`.
- A missing receipt state is `unavailable`, never proof that no submission
  occurred. The terminal probe must match the requested run, client-order, and
  decision identity before it makes its read-only history request.
- Keep credentials, account identifiers, private intents, raw broker payloads,
  and price values out of Git, logs, and public surfaces.

## Ready Queue

1. After the next scheduled daily result, consume only its exact receipt/run
   identity and categorical observer/terminal result. Do not scan for a latest
   run or infer terminal state from a missing record.
2. Keep scheduled sessions on their existing Paper-only route, deterministic
   intent/reconciliation rules, and directional console controls. The current
   goal does not authorize a manual duplicate invocation.
3. Keep stale-order automation closed. A legacy unknown exact intent remains
   `reconcile` evidence in private state and may not be regenerated, retried,
   or used to infer a terminal/PnL result.

## Operator Help

None. Private KIS Paper work is standing-authorized; escalate only a live route,
live capital, paid or unclear-rights dependency, public exposure, or unresolved
actual account-safety risk.

## Recovery

Current class: `resume`. A missing receipt identity or no-intent session is a
scoped ordinary result. An unknown exact order outcome requires reconciliation
before replacement of that same intent, but does not pause independent lanes or
create a manual approval step.

## Evidence

- The scheduled daily service owns its exact receipt observer and terminal-field
  probe handoff; both remain read-only after its own identity check.
- The local operations console reads sanitized projections only and carries no
  KIS credential, broker client, private intent state, or market-data mount.

## Next Handoff

Reattest the next daily task outcomes after they occur. Preserve a categorical
no-intent result as such; consume a receipt-linked result only through its exact
durable identity, without making fill or PnL claims beyond source evidence.
