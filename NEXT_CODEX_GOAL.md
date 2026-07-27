# Next Codex Goal

## Objective

Build the first source-scoped liquid-universe manifest for TheRicher's
opportunity-selection foundation. It must state exactly which current local
instruments can be exposed to an offline engine, their data provenance, and
their limitations without claiming point-in-time membership, stock ranking,
model selection, Paper eligibility, or profitability.

## Start

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `AGENTS.md`, `ARCHITECTURE.md`, `DECISIONS.md`, `RUNBOOK.md`,
   and all active stateboards.
3. Inventory the useful existing local QQQ/SPY/IWM and fixed NAS-panel inputs
   without a broad raw-data scan. Reattach their existing manifests, catalog
   identities, and source-safe qualification evidence before reading bars.
4. Ask Claude for a short falsification-first universe-construction challenge.
   Do not send raw rows, credentials, account data, or sealed labels. An OAuth
   failure is `review_unavailable`, not a hold on unranked private work.

## Work

1. **Data:** define a small deterministic liquid-universe manifest from only
   existing locally attested inputs. It must include a stable instrument identity,
   source/dataset identity, supported timeframes, current availability scope,
   and explicit non-PIT/non-ranking limitations. Store generated manifest data
   outside Git under `D:\market_data` or the external artifact root as appropriate.
2. **Data:** provide a narrow pure loader that rejects an unverified source,
   duplicate instrument identity, mismatched catalog provenance, missing
   timeframe, or an attempt to reinterpret the manifest as historical membership.
3. **Engine Research:** add one offline consumer contract that receives the
   manifest's eligible instruments as an unranked opportunity-selection input.
   It must not score, rank, choose a trade, fit a model, read credentials, use
   the GPU, call a provider, or reach a broker.
4. **Validation:** add focused tests for deterministic construction, provenance
   binding, source-safe external artifacts, pure import/loading, no network or
   credential access, and rejection of PIT/ranking/Paper misuse.
5. **Execution:** leave the installed prospective QQQ scheduler lane-owned.
   Reattach any naturally arriving terminal receipt, but do not manually invoke
   it and do not make it a completion condition.

## Boundaries

- Do not call KIS, read `.env` or credentials, submit/modify/cancel an order,
  enable live behavior, expose a public service, or download data for this goal.
- `KIS_LIVE_*` remains unreadable and unavailable.
- Keep market data under `D:\market_data`, generated artifacts under
  `D:\thericher-v2\model-artifacts`, and never commit either.
- The universe is current-source scoped only. It is not a point-in-time
  historical universe, a corporate-action qualification, a stock ranking, a
  model/Paper input, or a future data-acquisition authorization.
- Do not retune, revive, ensemble, or route the falsified CACC-D1, tree,
  linear, or sequence candidates.

## Completion

- One deterministic source-scoped manifest and pure loader are test-backed,
  externally stored, and reattestable from existing local evidence.
- An offline unranked consumer contract proves the manifest can feed the future
  opportunity-selection layer without crossing into strategy or execution.
- Every limitation remains explicit and source-safe; no raw rows, credentials,
  account data, order data, weights, or model artifacts are persisted.
- Any scheduled QQQ evidence remains lane-owned and does not delay this goal.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

Before ending, verify, commit, push, and replace this file with exactly one
next company objective.

## Suggested Commit Message

`Simplify QQQ Paper route and falsify CACC`
