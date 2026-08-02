# Next Codex Goal

Read `HANDOFF.md`, `AGENTS.md`, `ARCHITECTURE.md`,
`agents/engine-research.md`, `agents/research-steward.md`, `agents/execution.md`,
and `agents/orchestration.md` first. Then continue from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build and run one bounded CPU-only source-local ML baseline:
`spy-intraday-mtf-logistic-10m-v1`.

It is a deterministic regularized logistic breadth baseline over completed
`1m`, `5m`, `10m`, `1h`, and `3h` SPY inputs. It is not a promotion, model
selection, profitability claim, Paper input, order, or live route.

## Frozen Source And Contract

- Source: `kis.paper.private.intraday.spy.ams.m1.v1`, hash
  `sha256:64f149f5ff1c9002107f001a44f78c54c8944e9c030d6153898b1229d9c742e6`.
- Require exactly 21 complete regular sessions in chronological
  `10 development / 1 purge / 10 validation` order.
- Decision slots: every ten minutes from completed 12:30 ET through completed
  15:30 ET inclusive: 19 slots per session, 190 development and 190 validation
  feature rows. Each feature cutoff exposes completed same-session bars only.
- Fixed features: 30-minute 1m return; 30-minute 1m realized range; six-bar
  completed 5m return; three-bar completed 10m return; latest completed 1h
  candle return; latest completed 3h candle return.
- Target: the sign of the next ten-minute M1 open-to-open return. Development
  labels may be read only after target-free feature preflight; validation
  targets remain unread until after model fitting and target-free policy
  decision construction.
- Fit exactly one development-only standardized L2 logistic regression using
  `C=0.1`, no class weights, and no refit after development. The policy is long
  only at probability `>= 0.55`, otherwise flat.
- Preflight requires 150 causal rows in each phase and at least 30 target-free
  validation long decisions. The effective validation unit remains ten session
  blocks, not 190 independent observations.
- Costs are all-in round-trip `5`, `10`, and `20` bps. At 20 bps, reject the
  exact policy unless its validation net total is strictly positive and its net
  mean per executed event strictly exceeds an always-long same-schedule,
  same-cost reference.
- No feature, scaling, regularization, threshold, or cost tuning after any
  validation target access.

## Boundaries

- Do not call KIS, read `.env` or credentials, submit orders, access accounts,
  use local-paper, network, GPU, model weights, or live behavior.
- Use only the verified offline loader, existing cache, and existing pinned
  `scikit-learn` dependency. Do not add or replace a runtime.
- Do not store raw bars, timestamps, prices, row-level labels/predictions,
  model coefficients/checkpoints, credentials, or model artifacts in Git.
  Write aggregate-only receipts below `D:\thericher-v2\model-artifacts`.
- The result stays non-promoting: no Paper candidate, ensemble member, GPU
  appointment, live claim, or model selection.

## Required Work

1. Implement the frozen causal feature/preflight/fit/evaluate/run path and a
   pinned offline runner.
2. Ensure standardization and fitting use development rows only; validation
   target fields may not be read before target-free decisions are fixed.
3. Run one real CPU baseline against the local cache under an idempotent
   external run label.
4. Add focused tests for completed-bar causality across all five timeframes,
   development-only fitting, validation target isolation, minimum rows/long
   decisions, cost/comparator semantics, artifact redaction, and absence of
   network, credential, KIS, broker, account, order, local-paper, GPU, and
   live surfaces.
5. Keep the `review_unavailable`/Claude comparator correction as context only;
   it is not agreement or a dispatch hold.

## Verification

Run:

```powershell
uv run --extra dev pytest -q <focused changed tests>
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
docker compose --profile research config --quiet
```

## Completion

Report source and frozen contract, source-safe CPU outcome, external artifact
path, tests, commit hash, intentional omissions, and the next recommended
objective. Replace this file with exactly one next objective only after
completion evidence is committed and pushed.
