# Next Codex Goal

Read `HANDOFF.md`, `AGENTS.md`, `ARCHITECTURE.md`, `DECISIONS.md`,
`agents/data.md`, `agents/engine-research.md`, `agents/research-steward.md`,
and `agents/orchestration.md` first. Then continue from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Unblock one reproducible long-horizon local D1 research source by connecting
the installed Norgate trial to the host-only research extra and materializing a
small verified `SPY/QQQ/IWM` daily source snapshot under `D:\market_data`.

This is Data foundation plus Engine Research preparation. It is not a model
promotion, Paper input, order, account operation, or live route.

## Frozen Scope

- Use only the official `norgatedata==1.0.77` Python client, as the dedicated
  Windows-host-only `norgate-host` extra. It must not become a Docker runtime or a
  general provider replacement. Its official package documentation lists
  Windows, the Norgate Data Updater, and a local writable `.norgatedata`
  directory as requirements.
- Reuse the installed local trial database. Do not buy data, make a new Norgate
  account, accept new paid terms, or download raw data into Git.
- Probe exactly `SPY`, `QQQ`, and `IWM` at D1 from an explicit earliest
  requested date through the latest completed local session. Capture only
  source-safe coverage/field/adjustment/capital-event facts in Git or model
  artifacts; retain raw bars only in the new immutable `D:\market_data`
  snapshot.
- The snapshot must preserve explicit limits: local-NDU availability time,
  source restatement risk, unadjusted-request semantics, corporate-action
  coverage, point-in-time status, and its non-Paper/non-promotion status.
- A successful three-ETF probe is not evidence for a broad universe, ranking,
  model selection, or profitability. It only makes a later source-local daily
  research contract possible.

## Boundaries

- Do not call KIS, read `.env` or credentials, access accounts, submit/modify/
  cancel orders, use local-paper, or enable live behavior.
- Do not expose raw OHLCV, dates, values, Norgate local paths, tokens, or
  identifiers in Git, logs, test fixtures, or model artifacts.
- Keep generated data below `D:\market_data` and generated artifacts below
  `D:\thericher-v2\model-artifacts`; preserve the 20% warning / 15% hard free
  space policy.
- No GPU job, model training, threshold tuning, ensemble, or execution route
  belongs to this objective. Engine Research may only prepare the next daily
  hypothesis from the verified source contract.

## Required Work

1. Add and lock the exact official Norgate Python client as a host-only
   `norgate-host` optional dependency without changing the base or Docker runtime.
2. Make the existing Norgate D1 provider distinguish missing client, unavailable
   local updater, malformed local response, and valid bounded response without
   reading environment credentials or `.env`.
3. Add one small immutable source-snapshot/receipt path for the fixed ETF trio.
   It must be idempotent, content-hash verified, external to Git, and reject
   storage under the repository.
4. Run one real host-only local capability/materialization attempt. If the
   official client or updater is unavailable, write only a categorical
   source-safe receipt and close the exact attempt `input_unavailable`; do not
   invent a retry hold or block another lane.
5. Add focused tests for Windows host isolation, optional-client failure,
   bounded date/order validation, source-safe receipts, immutable artifact/data
   roots, and absence of KIS/broker/credential/GPU paths.
6. Have Engine Research record one concise next-campaign readiness fact only if
   the resulting source scope is adequate; do not train or evaluate a model in
   this objective.

## Claude Context

A short pre-goal falsification request exhausted its two-turn limit and is
`review_unavailable`, not agreement or a hold. Re-run a concise challenge only
if this work expands to broad-universe training, changes source eligibility, or
creates a promotion/Paper boundary.

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

Report the installed client version, categorical source result, retained D:
snapshot path if any, source limits, tests, commit hash, intentional omissions,
and the next recommended objective. Replace this file with exactly one next
objective only after completion evidence is committed and pushed.
