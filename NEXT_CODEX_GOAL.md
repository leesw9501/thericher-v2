# Next Codex Goal

## Objective

Build and run exactly one deterministic, disjoint 30-symbol Tiingo
standard-EOD raw-daily follow-up shard from the external Norgate `S&P 500
Current & Past` candidate union.

The shard extends only private-use source coverage. It must re-attest the
completed first pilot, exclude every first-pilot rank, and preserve the finding
that this date-less union is not a historical tradable universe. It must not
claim point-in-time availability, common-panel completeness, model quality, or
profitability.

## Ownership

- **Data Agent:** owns predecessor attestation, deterministic disjoint-rank
  selection, approved-token isolation, request pacing, raw-response provenance,
  canonical local validation, and external storage.
- **Review/Claude:** provides one concise falsification-first drift-check before
  changing the selection/retention contract or running the live shard.
- **Engine Research Agent:** remains an observer. The first pilot's 18 common
  sessions do not open model, ensemble, GPU, or campaign work.

## Boundaries

- Read only `TIINGO_API_TOKEN` through the existing narrow helper. Never read,
  log, expose, or send any other `.env` value to Claude.
- Re-attest the first pilot's exact dataset and manifest hashes before any
  selection. Use exactly 30 candidates selected from the same external union,
  excluding all predecessor ranks. Preserve raw symbols and request identifiers
  only in external source evidence. Do not print or commit symbols, raw rows,
  prices, volumes, response bodies, or token.
- Do not substitute a missing, empty, malformed, or rejected candidate. Record
  it as a gap and stop on auth, rate, malformed, storage, or contract failure.
- Limit the live pass to 30 requests, no retries, and no automatic follow-up.
  Use the fixed 2024-07-18 through 2026-07-17 daily window. Keep the pass at
  least one hour after the predecessor retrieval time.
- Persist exact raw responses, a hash-attested canonical raw-field subset, a
  Tiingo rights marker, and a manifest only under `D:\market_data`, using an
  external staging directory and atomic publication. Keep all output private
  and non-redistributable under Tiingo's current terms.
- Keep the shard `pit=false`, `ranking=false`, `holdout=false`,
  `campaign=false`, `model=false`, `gpu=false`, and `paper=false`. Do not add a
  provider/catalog, feature, strategy, model, GPU job, Docker work, broker call,
  KIS use, dashboard, report family, scheduler, or public service.
- Check D: immediately before the live pass. Warn below 20 percent free and
  stop below 15 percent. Do not create data or model artifacts in Git.

## Required Work

1. Read the current first-pilot manifest through an offline verifier and the
   external candidate union. Ask Claude for a short drift-check that challenges
   predecessor binding, rank exclusion, symbol semantics, retention, recovery,
   and the non-PIT boundary. Do not send raw rows, candidate symbols, or secrets.
2. Extend the smallest existing pilot helper and CLI to derive a deterministic
   30-rank selection from candidates not used by the predecessor. Add focused
   tests proving no rank overlap, hash-bound predecessor recovery, no retry or
   substitution, external-only atomic output, tamper detection, and no
   broker/Docker/credential access beyond the approved token.
3. Run focused tests and a fresh D: preflight, then run this one live shard once.
   Report aggregate counts and external hashes/paths only. If it stops, retain
   partial external evidence and do not rerun it.
4. Refresh `agents/data.md`, `HANDOFF.md`, and `DECISIONS.md`, replace this
   goal, then continue while no real operator approval boundary remains.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
```

Report the Claude verdict, predecessor binding, aggregate result, storage
result, external snapshot/manifest hashes, and any genuine operator data action
required.

## Suggested Commit Message

`Add Tiingo daily acquisition pilot`
