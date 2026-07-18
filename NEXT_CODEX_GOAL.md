# Next Codex Goal

## Objective

Build one immutable, hash-attested Tiingo IEX 5-minute archive snapshot for the
fixed `SPY`/`QQQ`/`IWM` period before r1: `2017-08-01` through `2026-01-12`.

This advances historical intraday data collection. It must remain a Data-owned
descriptive archive, not a provider registration, `CatalogedBars` input,
campaign, model, paper path, or profitability claim. Keep r1 immutable and
separate.

## Required First Reads

Run `./scripts/start_next_codex_task.ps1`, then read `HANDOFF.md`, `VISION.md`,
`ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`, `RUNBOOK.md`, `agents/README.md`,
and the Data, Engine Research, and Review stateboards. Assign Data ownership
and ask a temporary Review Agent to simplify-check the chunked lineage before
network retrieval. Ask Claude for a short drift-check before the material
loader/manifest change; if it is unavailable, record that fact and use Review
without treating either as approval.

## Fixed Retrieval Plan

Use the same Tiingo IEX HTTPS endpoint and query policy as r1, with exactly
these 21 inclusive windows for each of the three fixed symbols:

1. `2017-08-01` to `2017-12-31`
2. `2018-01-01` to `2018-05-31`
3. `2018-06-01` to `2018-10-31`
4. `2018-11-01` to `2019-03-31`
5. `2019-04-01` to `2019-08-31`
6. `2019-09-01` to `2020-01-31`
7. `2020-02-01` to `2020-06-30`
8. `2020-07-01` to `2020-11-30`
9. `2020-12-01` to `2021-04-30`
10. `2021-05-01` to `2021-09-30`
11. `2021-10-01` to `2022-02-28`
12. `2022-03-01` to `2022-07-31`
13. `2022-08-01` to `2022-12-31`
14. `2023-01-01` to `2023-05-31`
15. `2023-06-01` to `2023-10-31`
16. `2023-11-01` to `2024-03-31`
17. `2024-04-01` to `2024-08-31`
18. `2024-09-01` to `2025-01-31`
19. `2025-02-01` to `2025-06-30`
20. `2025-07-01` to `2025-11-30`
21. `2025-12-01` to `2026-01-12`

This is 63 exact requests: three chronological batches of seven windows
(`21` requests each), separated by at least 61 minutes from the start of the
previous batch. The measured r1 footprint makes `90 MiB` a conservative
external storage ceiling. Verify D: free space before each batch.

## Boundaries

- Read only `TIINGO_API_TOKEN` through the existing safe reader. Never print,
  log, commit, artifact, or send it to Claude.
- Use exactly the fixed endpoint, symbols, windows, `resampleFreq=5min`,
  explicit `open/high/low/close/volume`, `afterHours=false`, and
  `forceFill=false`. Do not add a provider, query another source, or widen
  symbols.
- Every chunk must be nonempty, strictly ordered, weekday/regular-session
  aligned, wholly inside its requested window, and contain fewer than 10,000
  rows. Preserve genuine missing 5-minute bars; do not fill them.
- Retain raw chunk bytes, canonical aggregate bytes, exact query metadata,
  hashes, coverage, and overlap facts only in the one external r2 snapshot
  under `D:\market_data`. No data/artifact belongs in Git.
- If any chunk reaches 10,000 rows, fails validation, hits rate/access failure,
  exceeds the storage ceiling, or a batch cannot safely continue, abort the
  archive without publishing a partial snapshot. Record only non-secret failure
  facts and do not retry more than twice for the same cause.
- Do not call KIS, read other credentials, submit/simulate orders, use GPU,
  train, create a candidate/campaign, or claim performance.
- Do not pay, log in, bypass access controls, or use a manual source.

## Required Work

1. Extend the existing r1 Data module with a versioned chunked archive contract
   that preserves r1 loading behavior. The r2 loader must offline-reattest all
   raw chunks, aggregate canonical bytes, manifest, ordering, no duplicates,
   fixed queries, r1 disjointness, and source limitations.
2. Add focused tests for chunk manifest/attestation, sub-cap enforcement,
   duplicate/overlap rejection, offline/no-credential replay, r1 compatibility,
   external-storage boundary, and no campaign/paper/provider integration.
3. Run the three predeclared batches only after code/tests and Review pass.
   Keep incomplete data in memory or removable external staging; publish the
   final snapshot atomically only after all 63 responses validate.
4. Reattest the finished external r2 snapshot offline and record its exact
   coverage, hashes, request count, storage size, and limits. Do not infer that
   r1/r2 are independent validation sets.
5. Update Data and Engine Research stateboards, `HANDOFF.md`, `DECISIONS.md`,
   and this file before ending the task.

## Verification

Run `uv run --extra dev pytest -q`, `uv run --extra dev ruff check .`, and
`docker compose --env-file .env.example config --quiet`.

## Suggested Commit Message

`Add chunked intraday archive`
