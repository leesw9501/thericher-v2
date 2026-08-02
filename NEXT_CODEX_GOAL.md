# Next Codex Goal

Read `HANDOFF.md`, `VISION.md`, `ARCHITECTURE.md`, `AGENTS.md`,
`DECISIONS.md`, `RUNBOOK.md`, `agents/README.md`, `agents/data.md`,
`agents/engine-research.md`, `agents/research-steward.md`,
`agents/execution.md`, and `agents/orchestration.md` first. Then continue from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build `kis-nas-d1-intraday-regime-hmm-persistence-v1`.

Run exactly one date-disjoint, source-local persistence check of the frozen NAS
D1 HMM fit. It must reuse the fixed family semantics without selecting a
window, state count, threshold, initialization, or cost after seeing the first
screen or the later labels. It is not an independent replication of the fit.

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

1. Preserve the completed Claude `uncertain` review: call this a persistence
   check, not a replication. A failed later review is `review_unavailable`,
   never agreement or a hold.
2. Commit the fixed implementation before the local-cache runner materializes
   any later labels. Its runner must first write an immutable source-safe
   precommit containing the exact config/code hash, then load data.
3. Freeze one exact contract before later labels:
   - re-fit only the existing two-state diagonal Gaussian HMM on `0..599` and
     derive each long-state map from fit labels `0..598` only;
   - build an input that retains only train bars `0..599` and tail bars
     `1000..1509`; it must expose neither original screen bars nor labels
     `600..999` to any model/evaluation helper;
   - use completed source bars `1000..1019` solely to warm the already-frozen
     forward filter, then make decisions `t=1020..1508` for target bar `t+1`;
   - retain the existing same-session ratio features, 10/15/20bp cost band,
     15bp primary all-long comparator, 1,000 joint ten-session-block label
     null, 15 percent extreme control, and source-safe artifact policy;
   - fail unless the one pooled 15bp statistic clears all-long and null P95 by
     the fixed margin and every symbol has the fixed availability count with
     no negative 15bp candidate-versus-all-long relation.
4. Add only the minimal offline leaf/runner extension needed. Make the
   original preflight receipt an immutable lineage input; do not persist bars,
   dates, labels, probabilities, fitted parameters, weights, or numeric
   performance values.
5. Add focused tests for precommit-before-load ordering, no original-screen
   bar/label access, tail boundary
   geometry, `t -> t+1` causality, frozen state mapping, joint-null alignment,
   extreme/multiplier/prefix controls, artifact redaction, and no
   network/credential/broker/GPU path.
6. Run one local-cache CPU persistence smoke only after the precommit code is
   committed and pushed. The terminal category is `input_unavailable`,
   `persistence_falsified`, or
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
