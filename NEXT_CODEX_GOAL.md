# Next Codex Goal

## Objective

Build `kis-intraday-observed-provisional-session-v1-followup`: reattach one
current, existing-worker QQQ observed/provisional outcome after the installed
intraday-head task's 2026-08-07 00:29 KST invocation. Preserve its exact
source-safe categorical result and offline validation; it may be a scoped
no-intent or recovery result and must never become an alpha, fill-quality,
PnL, or model-promotion claim.

The preceding 2026-08-06 06:20 KST invocation is fully reattached as exact
runtime `intraday-head-20260805T2120061382131Z`,
`recovery/collection_exit_nonzero` with Scheduler result `1`. It produced no
session outcome claim. Use the existing task and route only. Do not manually
invoke KIS, add a scheduler, or create a broker path. Keep all credentials,
account facts, order identifiers, raw prices, and `KIS_LIVE_*` unavailable.
The task-owned next due time is 2026-08-07 00:29 KST; do not foreground-wait
for it.
