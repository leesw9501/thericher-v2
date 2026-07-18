# Next Codex Goal

## Objective

Perform one bounded, falsification-first Norgate trial field probe to determine
whether the existing `Dividend` response can add conservative exclusion metadata
to the fixed `SPY`/`QQQ`/`IWM` raw-D1 r2 source snapshot. This improves data
quality only; it does not open a model campaign or GPU work.

## Ownership

- **Data Agent:** owns the Windows-host-only local probe, response-shape check,
  source/provenance evidence, and any external immutable revision.
- **Engine Research Agent:** remains an observer and may not train, rank,
  ensemble, or reserve GPU capacity from this result.
- **Review/Claude:** gives one concise falsification-first verdict before a
  revised source contract is relied on.

## Boundaries

- Use only the already-installed local Norgate trial on Windows. Do not read
  `.env`, credentials, tokens, or broker state; do not call KIS, submit orders,
  use a network data API, query Norgate from Docker, change Norgate settings,
  renew, purchase, or delete either local Norgate copy.
- Fix symbols to `SPY`, `QQQ`, and `IWM`, and fix the requested window to the
  r2 contract: 2024-07-18 through 2026-06-22. Do not enumerate a universe or
  widen dates or symbols.
- Run exactly one nonpersistent response-shape probe first. Retain no raw price
  rows, dividend amounts, or new data snapshot unless the response is ordered,
  explicitly clipped, session-aligned, and the source contract can describe it
  without inferring event timing, ex-date, payment date, adjustment semantics,
  point-in-time availability, or absence of unmarked events.
- A source-returned nonzero marker is exclusion evidence only. It must exclude
  the marker session plus adjacent observed sessions conservatively. Do not
  describe it as a dividend date or a tradeable event.
- If the field is absent, padded/ambiguous, uneven across the fixed symbols, or
  cannot be validated without a semantic inference, close this branch with no
  revised snapshot and no further automatic Norgate semantic probing.
- Keep retained data under `D:\market_data` and generated metadata under
  `D:\thericher-v2\model-artifacts`; never write either to Git. Preserve trial
  deletion/rights markers. The current r2 and superseded r1 remain immutable.
- No CPU/GPU training, model loading, campaign, data merge, model selection,
  sealed holdout, paper activity, or profitability claim is allowed.

## Required Work

1. Ask Claude for a concise falsification-first review before relying on a
   revision: state the narrow exclusion-only claim, the strongest kill test,
   padded-response and event-timing risks, the naive alternative of retaining
   r2 unchanged, and the fact that closes the branch. Do not send raw rows,
   values, secrets, or account data.
2. Reuse the r2 host-only primitives where possible. Add only the smallest
   mock-tested reader/builder revision needed to validate a `Dividend` marker
   response and, only on a passed contract, retain immutable external r3
   metadata with hashes and a clear non-eligibility scope.
3. Run the one local probe and report only aggregate response/window counts,
   hashes, conservative exclusion counts, and the resulting narrow data
   verdict. If it fails, preserve safe recovery evidence outside Git and stop
   the Norgate semantic branch.
4. Keep Engine Research state explicit that r2/r3 does not create breadth,
   depth, ensemble, or GPU eligibility. Refresh `HANDOFF.md`, stateboards,
   `DECISIONS.md`, and this goal before continuing.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
```

Report the Claude verdict, probe/revision result, external paths and hashes,
rights/deletion evidence, genuine operator action if any, and GPU eligibility.

## Suggested Commit Message

`Add Norgate trial raw-D1 snapshot`
