# Next Codex Goal

Read `HANDOFF.md`, `VISION.md`, `ARCHITECTURE.md`, `AGENTS.md`,
`DECISIONS.md`, `RUNBOOK.md`, `agents/README.md`, `agents/data.md`,
`agents/engine-research.md`, `agents/research-steward.md`,
`agents/execution.md`, and `agents/orchestration.md` first. Then continue from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build `causal-mtf-consensus-replay-input-integration-v1`.

Connect the existing fixed offline multi-timeframe consensus replay to the
new direct causal-window momentum adapter and the existing optional policy
window binding. The replay must use one reconstructed 1m/5m/10m/1h/3h causal
window for its ready expert evidence and target-policy input, while preserving
the frozen replay's typed results and exact regression digest.

This is a no-behavior-change input-integrity integration. It is not a new
strategy, replay rerun for research, model result, or Paper action.

## Hard Boundaries

- Do not call KIS, Tiingo, Norgate, or another provider. Do not read `.env`,
  credentials, account data, or `KIS_LIVE_*`.
- Do not manually run, add, submit, modify, cancel, or reconcile any Paper or
  broker order. Existing test-only local-paper fixtures may run only as an
  unchanged regression dependency of the frozen offline suite.
- Do not change campaign data, dates, targets, returns, costs, thresholds,
  sizing, order behavior, artifact formats, replay digest contract, or source
  provenance. Do not write an artifact outside pytest temporary state.
- Do not train/tune/load weights, use CUDA/GPU, allocate Research Steward GPU
  custody, create a model family, ensemble, feature framework, or new source
  wrapper.
- Do not silently fall back from a ready causal window to a separate raw model
  input path. A structural input mismatch must stay categorical and fail closed
  before a target proposal; do not invent a tolerance or re-bucket rule.

## Required Work

1. Ask Claude for a concise falsification-first drift check before changing
   the frozen replay's causal-input/policy boundary. A timeout or malformed
   response is `review_unavailable`, never agreement or a hold.
2. Inventory the replay's current raw 1m evidence construction, decision
   cutoff, resampling, and policy call. Choose the smallest internal helper or
   direct use that derives one causal window from the same completed source
   prefix and frozen momentum config, then uses
   `build_multitimeframe_momentum_evidence_from_causal_window` for ready
   evidence and passes that exact window to `propose_target_exposure`.
3. Preserve existing categorical unready behavior. If the raw path reports an
   unready input, do not construct or pass a partial causal window. If it is
   ready but the causal reconstruction/direct adapter disagrees, fail closed
   with a local implementation error or existing categorical status; never
   continue with unbound predictions.
4. Add focused tests proving the ready replay path calls the direct adapter and
   binds the same causal window to policy, without network, credentials, or
   filesystem reads. Prove future raw bars do not alter the resulting bound
   decision and a malformed source input produces no bound target proposal.
5. Run the existing frozen replay fixture only as a regression assertion and
   prove its aggregate replay digest and typed outcome are unchanged. Do not
   interpret it as a new PnL, selection, or Paper result.
6. Refresh Engine Research, Execution, orchestration, handoff, and decision
   stateboards with the exact integration and review result. State explicitly
   that no new provider, account, order, local-paper action, GPU, training,
   target, return, PnL, artifact, or live behavior was created, and that the
   QQQ/SPY observer remains an independent 0-record Data schedule rather than
   a foreground wait.

## Verification

Run focused tests and a CPU-only no-network integration smoke, then:

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example --profile research config --quiet
```

If the clean-root helper remains blocked by known interrupted roots, preserve
that fact and run its fresh-root mode plus the remaining verification commands.

## Completion

Report the integration point, Claude result, causal-window/policy call proof,
frozen digest result, tests, and why no new model/GPU/training/PnL/Paper/live
claim was created. Commit and push completion evidence before replacing this
file with exactly one next objective and continuing.
