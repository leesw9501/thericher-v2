# Daily Operator Summary

When 08:00 KST automation is enabled, keep one human-facing file:

```text
YYYY-MM-DD-summary.md
```

It links to `NEXT_CODEX_GOAL.md` and external machine-readable evidence rather
than copying either one. Include outcomes, mode, key PnL/data metrics, running
role work, recovery anomalies, exact operator data requests, and every
prioritized decision that genuinely requires operator authority. Consolidate
duplicates, but do not impose a count limit.

The generator reads the optional authoritative snapshot at
`runtime/operator_status.json` (or `THERICHER_RUNTIME_STATUS`). Missing or
invalid evidence, timestamps more than five minutes in the future, and
snapshots older than 15 minutes are reported as `unknown`; absence or staleness
must never be reported as zero broker, KIS, paper, or live activity.

Historical multi-file bundles remain as prior evidence. Do not create new daily
next-goal copies or additional status-report families.
