# Next Codex Goal

## Objective

Build one bounded, external-only Norgate membership-matrix snapshot for the
fixed `S&P 500 Current & Past` candidate union.

The snapshot must preserve the two documented source facts separately: a
date-less candidate union and per-symbol/date membership series. It may support
a later survivorship-aware data contract, but it is not a direct historical
universe list, publication-time proof, campaign input, or model-training input.

## Ownership

- **Data Agent:** owns the host-only builder, external snapshot, provenance,
  storage checks, and data-contract limits.
- **Review/Claude:** challenge the source construction before implementation:
  candidate completeness, membership timestamp use, date bounds, leakage,
  retention, and failure behavior.
- **Engine Research Agent:** remains an observer. It must not consume the
  matrix as `CatalogedBars`, a model input, a campaign universe, or GPU work.

## Boundaries

- Use only the already observed `S&P 500 Current & Past` union (expected count
  541) and official `norgatedata` membership calls on the Windows host. Do not
  use Docker, KIS, `.env`, credentials, or secret-like files.
- Use the exact fixed candidate union once, deterministic candidate ordering,
  `PaddingType.NONE`, and one explicitly recorded actual trial window. If the
  candidate count changes, a response is malformed/unordered, or a requested
  membership series is missing, stop without publishing a partial snapshot.
- Store data and its manifest only under `D:\market_data`; never Git, C:,
  Docker, or `D:\thericher-v2\model-artifacts`. Preserve the retained C: NDU
  copy. Confirm D: remains above the 20% warning and 15% hard floor first.
- Persist only the minimum membership matrix and its external manifest/hash
  lineage. Do not store price, volume, corporate-action, account, or raw
  package logs. The manifest must include a deletion/retention scope for the
  Norgate EULA and must not contain raw symbols or rows in Git documentation.
- Do not create `CatalogedBars`, a general provider, a campaign, strategy,
  model, GPU job, paper order, execution path, dashboard, or public service.
- Do not call the result a direct historical-universe list or infer membership
  publication time, constituent completeness beyond the fixed union, delisting
  coverage, or model eligibility.

## Required Work

1. Ask Claude for a concise falsification-first drift-check before edits or
   data acquisition. State the target source contract, candidate-count stop
   rule, malformed-response stop rule, membership-date limitations, retention
   obligation, and the fact that a union plus matrix is not a direct list.
2. Implement the smallest host-only builder and mock-based tests. It must make
   a deterministic one-time union query and bounded per-symbol membership
   queries, write only atomically outside Git after all validation succeeds,
   and leave no partial publication on failure.
3. Run the builder once against the existing trial only if the preflight and
   tests pass. Report just snapshot path, candidate count, actual date window,
   membership row count, hashes, validation outcome, package version, and disk
   state. Do not print symbols or raw membership rows.
4. Add a small external deletion instruction/marker with the snapshot so that
   Norgate-origin data can be removed if the trial/subscription ends. Do not
   add a recurring report or retention service.
5. Refresh `agents/data.md`, `HANDOFF.md`, and `DECISIONS.md`, replace this
   goal, then continue only if no true approval boundary remains.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
```

Report the Claude verdict, focused builder test, external snapshot summary, and
any genuine operator data help required.

## Suggested Commit Message

`Add Norgate membership matrix snapshot`
