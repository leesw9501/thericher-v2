# Next Codex Goal

## Objective

Materialize and attest one reusable, source-local historical NAS D1 Research
input from the already terminal private KIS Paper daily-history cache.

The goal is a data-contract improvement: turn verified local cache bytes into
an immutable, hash-attested D1 input with honest per-symbol coverage and
provenance. It is not a new collection job, point-in-time universe, ranking,
strategy, model campaign, GPU job, KIS Paper action, or profitability claim.

## Start

1. Run `./scripts/start_next_codex_task.ps1` and read `HANDOFF.md`, `AGENTS.md`,
   `DECISIONS.md`, and the active Data, Engine Research, Execution, and
   orchestration stateboards.
2. Inspect the existing terminal
   `D:\market_data\us_equities\kis_paper_private\daily-nas-history\v1`
   index and its immutable chunks before designing a consumer. Do not print raw
   rows or manually repair source bytes.
3. Ask Claude for a short falsification-first drift check only if the work
   changes source authority, blends providers, establishes a point-in-time
   universe/ranking claim, opens a sealed holdout, widens a broker route, or
   changes a major runtime. Normal offline materialization does not wait on the
   expired local Claude OAuth session.

## Frozen Scope

- Use only the terminal KIS Paper NAS daily-history cache and its fixed current
  registry: `AAPL`, `AMZN`, `GOOGL`, `META`, `MSFT`, and `NVDA` on `NAS`.
- Reuse the existing canonical daily-bar parser and preserve its
  `MODP=0_unadjusted` and corporate-action limitations.
- Retain each symbol's verified coverage and source-limited/complete status.
  Form a common multi-symbol intersection only when the exact aligned-session
  contract verifies; otherwise expose source-local streams without fabricating
  alignment.
- Store canonical data/manifests only under `D:\market_data`; store source-safe
  provenance receipts only under `D:\thericher-v2\model-artifacts`.

## Work

1. **Data:** implement a narrow loader/materializer that reattests the terminal
   index, validates chunk and bar lineage, deduplicates only through the
   existing canonical rules, and returns immutable `CatalogedBars`-style D1
   streams plus a content hash. Make malformed, conflicting, missing, or
   unverified source evidence fail closed for the affected symbol.
2. **Data:** write a compact D:-resident panel manifest and an external
   source-safe completion receipt. The receipt may contain source/cache/index
   hashes, symbol identifiers, categorical status, counts, date buckets, and
   limitations; it must not contain raw bars, prices, volumes, provider rows,
   credentials, account facts, orders, or model outputs.
3. **Validation:** add focused offline tests for lineage reattestation,
   complete/source-limited propagation, cross-symbol alignment rejection,
   immutable output paths, raw-field exclusion, and no network/credential/KIS
   access. Add one CLI or small script only when it makes the bounded materializer
   reproducible.
4. **Engine Research:** consume no strategy output in this goal. Record only
   whether the resulting input is eligible for a future source-local frozen
   campaign; do not run a model, replay, parameter sweep, GPU job, ensemble, or
   Paper action.

## Boundaries

- No KIS calls, credentials, `.env` reads, paid data/model, provider download,
  public service, order, account, quote, or live route.
- No provider blending, historical membership inference, liquidity/ranking
  claim, corporate-action repair, or raw-data disclosure.
- No model training/checkpoint, strategy selection, backtest/PnL result, GPU
  dispatch, or KIS Paper order.
- Keep data under `D:\market_data` and artifacts under
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`; never commit
  either.

## Completion

- A reattestable, source-local historical NAS D1 input exists with immutable
  local manifest and source-safe external receipt.
- Each symbol's coverage and limitations are explicit, and any common
  intersection is proven rather than assumed.
- Tests prove the materializer is offline, credential-free, immutable, and
  cannot become a ranking/model/Paper surface.
- Refresh the stateboards and replace this file with exactly one next company
  objective before ending.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Materialize NAS daily history panel`
