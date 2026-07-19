# Next Codex Goal

## Objective

Build one offline, hash-attested Tiingo r2 cross-source validation cohort for
the existing Norgate static development panel. The cohort must make it possible
to falsify Norgate-only engineering findings later without mixing sources,
opening model training, or making a point-in-time, ranking, paper, or
profitability claim.

## Ownership

- **Data Agent:** owns the smallest local reattestation, cohort manifest, and
  conservative corporate-action exclusion evidence.
- **Engine Research Agent:** owns the read-only intake boundary that prevents
  the cohort from becoming a training, model, ensemble, or paper input in this
  objective.
- **Validation Agent:** independently reattests the completed cohort and
  verifies that no credential, network, broker, or model boundary was crossed.
- **Review/Claude:** gives a concise falsification-first review before the
  cross-source cohort is relied on by a later research contract.

## Fixed Inputs And Boundaries

- Reuse only the existing Tiingo Standard EOD r2 snapshot at
  `D:\market_data\us_equities\tiingo_standard_eod_pilot\canonical\snapshot=2026-07-18-tiingo-standard-eod-pilot-r2`.
  Its source data hash is
  `sha256:6decf91002aa0029d7cda1cb0b5131d1f440129624c84db2cca0d98579e4ccc1`
  and manifest hash is
  `sha256:76234da1951bccb54d74ab0f07358d138e861331914405cae6b91538f25ddb9e`.
- Reattest the existing Norgate broad panel at
  `D:\market_data\us_equities\norgate_trial_broad_development_panel\canonical\ohlcv_1d\snapshot=2026-07-18-norgate-trial-broad-d1-panel-r1`.
  Its data and manifest hashes remain
  `sha256:3d0841b90ddfd8d861f2432e404617ec0fc6e1afb8c902a81972df518720402d`
  and `sha256:a7ff3e700e3f53f48851982e1431b8a6647dda0bbfab8129faf32962604cfb2e`.
- The intended cohort is the 29 available Tiingo r2 symbols, its 501 common
  returned sessions, and the 483-session overlapping Norgate slice. The later
  18 Tiingo sessions are forward-only evidence, not a selection or training
  slice. Verify all counts from bytes rather than trusting this description.
- Use raw `open`, `high`, `low`, `close`, `volume`, `div_cash`, `split_factor`,
  date, rank, and lineage only. Do not use adjusted fields, repair/fill data,
  infer corporate-action timing, or mix price fields from the two providers.
- Do not read `.env`, credentials, or tokens. Do not make a network, Tiingo,
  Norgate, KIS, broker, or order call. Keep `THERICHER_MODE=off`.
- Do not train models, launch GPU work, open a sealed holdout, rank/select a
  candidate, build an ensemble, calculate PnL, submit local-paper orders, or
  expose a service.
- Store only a compact derived manifest/exclusion artifact under `D:\market_data`
  or `D:\thericher-v2\model-artifacts`, never in Git. Avoid duplicating raw
  rows; cap derived bytes below 1 MiB and preserve the D: 20/15 percent
  warning/hard floors.

## Required Work

1. Ask Claude for a short falsification-first review of the proposed overlap,
   rank-exclusion linkage, event mask, survivor/PIT limitations, and the fact
   that keeps the cohort out of model work. Do not send rows, symbols, raw
   labels, tokens, or account information.
2. Data Agent builds the smallest offline verifier/materializer that rehashes
   the exact Tiingo r2 and Norgate parents. It must retain the Tiingo rank
   linkage, the exact 29-symbol/501-session facts, the 483-session overlap, the
   later 18-session forward-only boundary, and a conservative mask for every
   event date plus any feature/label window touching it.
3. Data Agent writes one immutable compact external cohort manifest and tests
   tamper rejection, row/session/rank mismatch rejection, event-mask bounds,
   path containment, and absence of credential/network access.
4. Engine Research adds only the read-only intake guard needed to ensure the
   cross-source cohort cannot be silently mixed into Norgate training or reused
   as a ranking, ensemble, paper, PnL, or profitability input. Do not add a new
   campaign, model class, scheduler, or general data platform.
5. Validation independently reattests both parents and the derived cohort,
   checks the no-model/no-broker/no-network boundary, and labels the result
   cross-source engineering evidence only.
6. Refresh `HANDOFF.md`, the Data and Engine stateboards, `DECISIONS.md`, and
   this goal before continuing. Keep the static-panel CUDA run recorded as two
   completed MLP jobs and two compute-rejected, untested TCN jobs; do not retry
   it within this objective.

## Stop Rules

- Stop before writing if either parent hash, session ordering, rank linkage,
  raw field schema, event mask, overlap count, artifact root, or free-space
  check fails.
- Stop and keep the existing inputs unchanged on a source-rights ambiguity,
  missing raw fields, a mismatch that would require a provider call, or any
  path that would read credentials or cross a broker boundary.
- The cohort remains non-PIT and survivor-conditioned even if all checks pass.
  A later model contract needs a new Claude review and independent temporal or
  source-separated validation before it can open a breadth queue.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
```

Report the exact external parent and derived paths/hashes, validation verdict,
tests, data still needed from the operator, and every stop condition triggered.

## Suggested Commit Message

`Add Tiingo cross-source validation cohort`
