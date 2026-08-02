# Next Codex Goal

Read `HANDOFF.md`, `VISION.md`, `ARCHITECTURE.md`, `AGENTS.md`,
`DECISIONS.md`, `RUNBOOK.md`, `agents/README.md`, `agents/data.md`,
`agents/engine-research.md`, `agents/research-steward.md`,
`agents/execution.md`, and `agents/orchestration.md` first. Then continue from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build `kis-nas-d1-intraday-regime-hmm-replication-v1`.

Run exactly one date-disjoint, source-local replication of the frozen NAS D1
HMM preflight. It must reuse the fixed family semantics without selecting a
window, state count, threshold, initialization, or cost after seeing the first
screen or the replication labels.

## Boundaries

- Do not call a provider, KIS, Norgate, Tiingo, or a broker. Do not read
  `.env`, credentials, account data, or `KIS_LIVE_*`.
- Reattest only the existing six-symbol NAS D1 panel. Never open its existing
  647-session validation phase. Generated source-safe receipts belong only
  under `D:\thericher-v2\model-artifacts`.
- No Paper/local-paper action, model selection, ensemble, checkpoint,
  GPU/CUDA appointment, PnL/profitability, or live claim is allowed.
- Preserve the current-listing, non-PIT, unadjusted/MODP=0,
  corporate-action, and session-finality limitations. A passing replication
  remains source-local and non-promoting.

## Required Work

1. Ask Claude for a concise falsification-first review before opening the
   date-disjoint labels. Treat a failed review as `review_unavailable`, never
   as agreement or a hold.
2. Freeze one exact contract before replication labels:
   - re-fit only the existing two-state diagonal Gaussian HMM on `0..599` and
     derive each long-state map from fit labels `0..598` only;
   - never reopen or use the original `622..998` screen labels for a decision;
   - use completed source bars `1000..1019` solely to warm the already-frozen
     forward filter, then make decisions `t=1020..1508` for target bar `t+1`;
   - retain the existing same-session ratio features, 10/15/20bp cost band,
     15bp primary all-long comparator, 1,000 joint ten-session-block label
     null, 15 percent extreme control, and source-safe artifact policy.
3. Add only the minimal offline leaf/runner extension needed. Make the
   original preflight receipt an immutable lineage input; do not persist bars,
   dates, labels, probabilities, fitted parameters, weights, or numeric
   performance values.
4. Add focused tests for no original-screen-label access, tail boundary
   geometry, `t -> t+1` causality, frozen state mapping, joint-null alignment,
   extreme/multiplier/prefix controls, artifact redaction, and no
   network/credential/broker/GPU path.
5. Run one local-cache CPU replication smoke if the frozen input is ready. The
   terminal category is `input_unavailable`, `replication_falsified`, or
   `source_local_non_promoting`; only the final category clears the fixed
   all-long and null relations. Update the Data, Engine, Steward,
   orchestration, handoff, and decision stateboards with the Claude verdict,
   exact lineage, and why no promotion follows.

## Verification

Run focused tests and the CPU smoke, then:

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example --profile research config --quiet
```

If the clean-root helper is blocked only by known interrupted roots, preserve
that fact and run its fresh-root mode plus the remaining commands.

Commit and push the completion evidence, replace this file with exactly one
next objective, and continue without waiting for a market session.
