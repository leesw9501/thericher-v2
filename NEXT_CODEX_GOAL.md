# Next Codex Goal

## Objective

Freeze the first honest KIS-native daily comparative-validation contract from
the available `QQQ`/`SPY`/`IWM` panel and run its CPU baseline without treating
data quantity as a permission gate.

The hash-attested panel has 694 common completed `MODP=0_unadjusted` sessions.
It is the current clean common range. KIS IWM backfill beyond its current lower
bound is source-limited: a page with one internally inconsistent OHLC row made
the strictly parsed page unusable. Do not coerce its other rows into the panel
or repeatedly call the same bad page. This limits historical coverage, not KIS
Paper, local-paper, or research authority.

`KIS_PAPER_*` market/account/order calls, paper submission, and goal-owned
scheduling are standing-authorized. `KIS_LIVE_*` and real-money routes remain
unavailable.

## Required Reads

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `AGENTS.md`, `DECISIONS.md`, `RUNBOOK.md`,
   `agents/data.md`, `agents/engine-research.md`, and `agents/execution.md`.
3. Load the private daily panel offline and record only hashes, session counts,
   date bounds, and limitations; never print raw rows, credentials, or account
   values.
4. Ask Claude for a concise falsification-first review before freezing the
   split or opening/interpreting a holdout. Do not send credentials, raw rows,
   or holdout labels.

## Work Packages

### Data Agent

- Keep `data.kis_paper_daily` as the sole daily KIS consumption boundary.
  Re-attest the index, manifests, raw hashes, cursor seams, and exact overlap
  before exposing bars.
- Treat 694 common sessions as the active frozen-input candidate. Retain its
  raw-price/corporate-action limitation and the IWM historical source-quality
  limit in the dataset contract.
- Do not run another IWM daily backfill from the blocked lower bound until a
  different official KIS endpoint or an evidence-backed row-quality contract
  can retrieve it without silently excluding inconsistent OHLC data.
- Do not substitute Tiingo, Norgate, Yahoo, or synthetic bars into this
  KIS-native validation panel. Other sources may remain separate development
  evidence.

### Engine Research Agent

- After Claude's split review, freeze a chronological 60/20/20 contract with
  a two-session purge/embargo over the available 694-session panel. The final
  holdout stays unopened while thresholds or alternatives are selected.
- Run the deterministic daily relative-strength reference and a naive
  cash/always-invested comparator through replayable local paper on the
  appropriate pre-holdout partitions. Persist each run's `run.json`, event
  hash, data hash, costs, and code revision under `D:\thericher-v2\model-artifacts`.
- State only comparative observations with their limitations. Do not claim
  profitability or start CUDA simply to occupy the GPU.
- Update breadth, depth, ensemble, and replication queues based on the frozen
  baseline. A GPU candidate still needs a distinct falsifiable hypothesis and
  an eligible campaign contract.

### Execution Agent

- Keep daily validation broker-free: decisions become `OrderIntent`s only for
  the local-paper simulator and all fills remain `source: local_paper`.
- Preserve the prepared next order-transport slice: KIS Paper US buy-only,
  fixed paper host, durable idempotent intent, and `inquire-ccnl` recovery.
  The unresolved US sell TR-ID contradiction remains out of scope until an
  official source resolves it.

### Validation

- Independently check temporal split disjointness, purge/embargo, source-only
  panel identity, local-paper replay, and the run-manifest/event-hash link.
- Validate that the source-limited IWM boundary cannot be silently filled or
  converted into a permission/approval gate.

## Operating Boundaries

- There is no paper-capital, profitability, dashboard, report, trade-count,
  756-session, or per-call approval gate. The former 756-session target is a
  data-quality preference; the documented source limit permits validation now.
- Private KIS raw-data retention on `D:` and goal-owned KIS Paper schedules are
  authorized. Retention metadata is factual, never a permission switch.
- Do not read `KIS_LIVE_*`, call a live route, expose secrets, publish KIS
  data, or store raw market data/model artifacts in Git.
- Keep model artifacts under `D:\thericher-v2\model-artifacts` or
  `/app/model_artifacts` in Docker.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Freeze KIS daily validation contract`
