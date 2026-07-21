# Next Codex Goal

## Objective

Expose the existing Norgate trial broad D1 panel through one reusable,
read-only, hash-attested public `Bar`-series loader.

This is a Data foundation objective. It makes the already stored external panel
usable by future engineering without duplicating its feature artifact or
turning a static trial dataset into a trading, model, or GPU claim.

## Required First Reads

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `AGENTS.md`, `ARCHITECTURE.md`, `DECISIONS.md`, and the
   active stateboards under `agents/`.
3. Read the existing implementation and tests before editing:
   - `src/thericher_v2/data/norgate_trial_development_panel.py`
   - `src/thericher_v2/data/norgate_broad_development_artifact.py`
   - `tests/test_norgate_trial_development_panel.py`
   - `tests/test_norgate_broad_development_artifact.py`
4. Read only the manifest and required local snapshot files under the frozen
   path below. Do not recursively scan `D:` or parse the Norgate database.

## Frozen Source Contract

- Snapshot:
  `D:\market_data\us_equities\norgate_trial_broad_development_panel\canonical\ohlcv_1d\snapshot=2026-07-18-norgate-trial-broad-d1-panel-r1`
- Dataset ID:
  `us_equities.norgate_trial_broad_development_panel.1d.snapshot=2026-07-18-norgate-trial-broad-d1-panel-r1`
- Panel SHA-256:
  `sha256:3d0841b90ddfd8d861f2432e404617ec0fc6e1afb8c902a81972df518720402d`
- 523 symbols, 483 common sessions, 252,609 D1 OHLCV rows,
  `2024-07-18` through `2026-06-22`.
- `development_training_eligible=true`; `model_eligible=false`,
  `gpu_eligible=false`, `paper_trading_eligible=false`, `pnl_eligible=false`,
  `ranking_eligible=false`, and `point_in_time_eligible=false`.
- The source is static/survivorship/availability selected and adjustment
  semantics are unverified. Those are source facts, not reasons to re-download
  or silently repair data.

## Required Work

### Data Agent

1. Reuse the existing Norgate snapshot verifier and CSV parser to add one
   public immutable catalog/series loader. It must return candidate rank,
   hash-attestation identity, common sessions, source limitations, scope flags,
   and symbol-keyed canonical `Bar` series.
2. Keep all input bytes at `D:\market_data`; the loader writes no market data,
   model artifact, or cache inside Git.
3. Reject manifest, panel hash, schema, symbol/rank, duplicate, ordering, or
   common-session drift before exposing any series.
4. Preserve the negative source scope in the returned object. Do not modify the
   Norgate database, download data, construct a PIT universe, infer adjustment
   semantics, or treat dropped symbols as membership evidence.

### Engine Research Agent

- Review the new loader only as an engineering input contract. Do not build or
  run a selector, model, ensemble, PnL analysis, GPU job, CUDA mode, paper
  order, KIS call, or promotion workflow from this panel.
- Record the previous Norgate engineering-only validation as historical context
  if useful, but do not reproduce its feature artifact or make a new result
  claim.

### Validation

- Add focused offline tests proving no credential, network, Norgate SDK, KIS,
  GPU, or artifact-root access is required.
- Cover the frozen external manifest/panel smoke when available and hermetic
  fixtures for each rejection path.
- Verify the public object cannot misreport the source as model/GPU/PnL/paper
  eligible.

## Boundaries

- No KIS call, credential read, broker action, data download, paid service,
  Norgate database parsing, public service, model training, GPU work, or live
  behavior is needed for this objective.
- Do not introduce a second Norgate feature pipeline, a scheduler, report
  family, or per-agent workflow.
- The prior Claude check was `uncertain` because its environment could not
  verify the local D: snapshot; local manifest attestation resolved that factual
  question. Retain its valid limits: static-survivorship data is development
  plumbing only, and unverified adjustment semantics prohibit strategy claims.
- Ask Claude for a fresh short falsification check only if implementation needs
  to widen this source contract or introduce a new reusable runtime beyond this
  bounded read-only loader.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Expose Norgate trial broad panel loader`
