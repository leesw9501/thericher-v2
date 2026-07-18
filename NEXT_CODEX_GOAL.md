# Next Codex Goal

## Objective

Establish a bounded, host-only Norgate historical-universe capability contract.

Determine whether the existing Norgate US Stocks Platinum trial can enumerate a
date-specific US equity universe for a later data contract, without creating a
dataset or inferring point-in-time semantics from a convenient API shape.

This advances data collection toward a survivorship-aware development source.
It is not bulk extraction, a data snapshot, a campaign, model training, GPU
work, paper trading, or a live step.

## Ownership

- **Data Agent:** owns public API evidence, a bounded local capability probe,
  and the resulting limits.
- **Review/Claude:** perform a falsification-first data-contract drift-check
  before any local query. Do not receive rows, credentials, or trial data.
- **Engine Research Agent:** remains an observer; it must not consume the
  result as a model or campaign input.

## Boundaries

- Use only the existing Windows Norgate trial and its official Python package.
  Do not read `.env`, credentials, KIS data, or secret-like files.
- Do not change an NDU, Python-package, global, or user configuration. Do not
  install a permanent project dependency; an ephemeral official package overlay
  is allowed only for the bounded host probe.
- Keep all trial output in process: no export, cache, artifact, manifest,
  dataset, Git data, Docker mount/query path, or raw rows/symbol lists in
  logs or Markdown.
- Use at most two bounded local data-plane calls after public documentation and
  runtime function-signature inspection identify the most direct candidate.
- Report only function identity, parameter shape, requested as-of dates,
  result shape/count, and validation outcome. Do not claim source publication
  time, historical constituent completeness, delisting coverage, exact
  membership semantics, or model eligibility unless the source itself binds it.
- Do not create `CatalogedBars`, a provider for a dynamic universe, a campaign,
  GPU job, model, paper order, execution path, or public service. Preserve the
  retained C: copy and keep `THERICHER_MODE=off`.

## Required Work

1. Ask Claude for a concise falsification-first drift-check before editing or
   running a data-plane probe. State the target claim, strongest kill test,
   survivorship/PIT risks, two-call cap, and no-persistence rule.
2. Consult official Norgate public package documentation and inspect the local
   package's callable surface/signatures without printing data. Identify the
   single most direct documented route, if any, to enumerate an index universe
   at an explicit historical date.
3. Run no more than two tight, in-memory host queries. Validate that returned
   results honor the requested as-of boundary and distinguish a historical
   universe enumeration from a current-symbol list or per-symbol boolean.
4. Record the result as `supported-with-limits`, `uncertain`, or `unsupported`.
   If a historical list cannot be proven, stop the branch rather than add a
   workaround, scraper, export, or inferred universe.
5. Refresh `agents/data.md`, `HANDOFF.md`, and `DECISIONS.md` only with durable
   capability facts, then replace this goal.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
```

Report the Claude verdict, public source used, focused probe summary, and any
operator data help actually required.

## Suggested Commit Message

`Audit Norgate historical universe capability`
