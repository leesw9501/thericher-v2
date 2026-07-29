# Next Codex Goal

## Objective

Build one offline, source-local unexplained-discontinuity census for the frozen
six-symbol KIS Paper D1 history panel.

The census stress-tests the narrow five-pair split-signature observation by
checking every retained adjacent D1 pair across AAPL, AMZN, GOOGL, META, MSFT,
and NVDA. It records only categorical counts of very large moves outside the
same five fixed split pairs. An unexplained result is a data-semantic signal,
not proof of a provider error, adjustment behavior, corporate action, or model
eligibility.

## Start

1. Run `./scripts/start_next_codex_task.ps1` and read `HANDOFF.md`, `AGENTS.md`,
   `ARCHITECTURE.md`, `DECISIONS.md`, `RUNBOOK.md`, and active stateboards.
2. Inspect the installed broad-D1 task only for its source-safe state. Do not
   start, stop, duplicate, alter, or wait on the collector.
3. Reattest the exact frozen six-symbol KIS D1 history panel through its
   existing offline loader. Do not invoke a provider, credential, or mutable
   cache path.
4. Use the completed Claude challenge recorded in `DECISIONS.md`: the prior
   five-pair check remains narrow; do not build a label adapter from it.

## Fixed Census Contract

- Examine every ordered adjacent pair of completed retained D1 bars within each
  source stream. Use the unchanged signature
  `abs(log(close_later / close_earlier)) >= log(3)`, implemented with exact
  positive Decimal ratio comparisons. There is no threshold sweep, event-date
  discovery, parameter tuning, or provider/event feed.
- Categorize a signature only as `known_fixed_split` when its later session is
  one of the five predeclared pairs already committed in the prior audit.
  Every other signature is `unexplained_large_discontinuity`.
- Return one immutable external source-safe receipt with per-symbol aggregate
  pair counts and categorical status plus one overall status:
  `no_unexplained_large_discontinuity`,
  `unexplained_large_discontinuity_observed`, or `inconclusive`.
  Invalid or incomplete pair handling must be fail-closed to `inconclusive`.
- Never persist source rows, prices, returns, timestamps, session/event dates,
  per-pair records, or any location of an observed discontinuity. The fixed
  event contract may be represented only by a checksum.
- A zero unexplained count does not verify adjustment semantics, corporate
  actions, source identity, sessions, gaps, survivorship, PIT eligibility, or
  source transfer. A nonzero count does not identify a cause.

## Authority And Boundaries

- Use only existing local cache bytes and offline code. Docker research remains
  network-disabled with read-only data mounts and external artifacts under
  `/app/model_artifacts` mapped to `D:\thericher-v2\model-artifacts`.
- Do not read `.env`, credentials, tokens, account data, or KIS responses. Do
  not call KIS, Tiingo, another provider, broker, or live route. Do not mutate
  any cache, scheduler, task, cursor, or raw data.
- Do not construct labels, features, a rule, a model, an encoder probe, a
  rank, an ensemble, a replay, PnL, a local-paper intent, or a KIS Paper action.
  Do not create a corporate-action sidecar or change an earlier conformance or
  split-signature receipt.
- Do not introduce a dependency, public model/weight, runtime, worker, or
  scheduler.

## Parallel Work Packages

1. **Data:** implement the deterministic in-memory all-six-symbol census and
   immutable external categorical receipt. It must reattest source identity and
   avoid retaining any event-level observation.
2. **Engine Research:** define the interpretation boundary: every census result
   remains non-model, non-ranking, non-PnL, and non-Paper evidence; the result
   cannot become a label adapter or causal campaign input.
3. **Temporary Validation:** add focused tests for zero, nonzero, and
   inconclusive outcomes; fixed pair exclusion; no-network/no-credential route;
   no value/date/per-pair persistence; immutable receipt reattachment; and
   external artifact-root enforcement.
4. **Data / temporary Validation:** reattach any automatic broad postrun only
   through its existing receipt-bound path. Its absence or scoped retry does
   not delay this census.

## Completion

- The census reattests one frozen KIS D1 source and produces only the allowed
  categorical external receipt.
- The result changes no source conformance, corporate-action qualification,
  label eligibility, research, model, ranking, PnL, local-paper, KIS Paper, or
  live action.
- Refresh Data/Research/orchestration stateboards, replace this file with one
  next objective, verify, commit, push, and continue.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Audit KIS D1 split signatures`
