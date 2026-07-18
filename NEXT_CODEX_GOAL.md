# Next Codex Goal

## Objective

Establish the smallest bounded Data contract for the already-installed Norgate
US Stocks Platinum trial to determine whether a fixed `SPY`/`QQQ`/`IWM` raw-D1
snapshot can become a reproducible **development-only** source that is separate
from the unresolved Tiingo factor-sensitive evidence.

This advances the data-collection and future model-validation loop. It does
not authorize a broad historical universe, a model campaign, or GPU training.

## Ownership

- **Data Agent:** owns the Windows-host-only, read-only trial probe, exact
  source/provenance contract, external data/artifact layout, and the narrow
  eligibility verdict.
- **Engine Research Agent:** is an observer. It may state the minimum
  completed-session and event-mask requirements the Data contract must expose,
  but must not train, rank, ensemble, or schedule CPU/GPU work.
- **Review/Claude:** provides one falsification-first drift check before a new
  load-bearing source contract is relied on.

## Boundaries

- Use only the already-installed Norgate trial on Windows through its local
  client. Do not read `.env`, credentials, tokens, or broker state; do not call
  KIS, submit orders, or use a network data API.
- Do not renew, purchase, change trial settings, delete either Norgate copy, or
  query Norgate from Docker. Stop and report if local use requires a new login,
  acceptance, payment, or manual operator action.
- Keep any retained Norgate-derived data under `D:\market_data` and generated
  metadata under `D:\thericher-v2\model-artifacts`; never write either to Git.
  Preserve a deletion/rights marker suitable for the trial terms.
- Fix symbols to `SPY`, `QQQ`, and `IWM`; use explicit bounded dates and the
  official query-local no-adjustment setting. Do not infer adjustment semantics,
  repair bars, fill gaps, transform prices, or combine rows with Tiingo.
- Treat the source's capital-event dates as conservative exclusion evidence
  only. Do not claim an event timestamp, same-session actionability, point-in-
  time universe correctness, ranking, holdout, campaign, model, GPU, paper, or
  profitability eligibility.
- Do not acquire another Tiingo shard. The completed aggregate audit already
  proved that R1 binds the 18-session combined floor; the 56-group R2 coverage
  filter remains descriptive only.

## Required Work

1. Ask Claude for a concise falsification-first review of the proposed fixed
   ETF contract. Include the claim, raw/no-adjustment assumption, event-date
   uncertainty, source independence limits, strongest kill test, and the fact
   that would make the source unusable. Do not send Norgate rows, symbols beyond
   the fixed three, or secrets.
2. Reuse the existing host-only Norgate primitives where possible. Add the
   smallest mock-tested builder/verifier and CLI needed to retain one immutable
   external raw-D1 snapshot with raw OHLCV, query settings, returned session
   coverage, conservative event exclusion metadata, hashes, rights/deletion
   marker, and explicit non-eligibility scope. The verifier must fail closed on
   raw/canonical/marker tampering and must not need network, token, broker, or
   Docker access.
3. Run one bounded local build against the installed trial. Report only source
   coverage, hashes, aggregate counts, event-mask bounds, and the narrow
   development-data verdict. If the local client cannot meet the contract,
   preserve only safe external recovery evidence and close the path rather than
   changing settings or retrying broadly.
4. Keep the Engine stateboard clear that no CPU/GPU breadth, depth, or ensemble
   work opens unless the resulting Data verdict explicitly says so. Refresh
   `HANDOFF.md`, `DECISIONS.md`, and this goal before continuing.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
```

Report the Claude verdict, local-source result, external paths/hashes, retained
rights/deletion evidence, any genuine operator action required, and whether the
result changes GPU eligibility.

## Suggested Commit Message

`Add Tiingo coverage audit`
