# Next Codex Goal

## Objective

Falsify or narrowly support the retained six-symbol KIS Paper D1 cache's
`MODP=0` declared-unadjusted semantics using only an offline split-signature
audit.

This is an input-integrity check for future retrospective KIS labels. It is not
a corporate-action feed, source transfer, data repair, feature, model,
backtest, ranking, PnL, or Paper-trading task. It cannot make the Norgate/KIS
conformance receipt model-eligible.

## Start

1. Run `./scripts/start_next_codex_task.ps1` and read `HANDOFF.md`, `AGENTS.md`,
   `ARCHITECTURE.md`, `DECISIONS.md`, `RUNBOOK.md`, and active stateboards.
2. Inspect the installed broad-D1 task only for its source-safe state. Do not
   start, stop, duplicate, alter, or wait on the collector.
3. Reattest the exact frozen six-symbol KIS D1 history panel through its
   existing offline loader. Do not invoke a provider, credential, or mutable
   cache path.
4. Use the already-completed Claude challenge recorded in `DECISIONS.md`: a
   Tiingo sidecar expansion is not the next action; the offline split-signature
   kill test is.

## Fixed Audit Contract

- Audit only AAPL, AMZN, GOOGL, and NVDA against the following predeclared
  public split-session pairs, all checked in memory against the named source
  stream: `2020-08-28 -> 2020-08-31`, `2022-06-03 -> 2022-06-06`,
  `2022-07-15 -> 2022-07-18`, `2021-07-19 -> 2021-07-20`, and
  `2024-06-07 -> 2024-06-10` respectively, with both NVDA pairs required.
- For every available pair, use the fixed signature
  `abs(log(close_after / close_before)) >= log(3)`. There is no threshold
  sweep, event-date search, parameter tuning, or use of a provider/event feed.
- Return only one immutable external source-safe receipt with per-symbol
  categorical results and one aggregate status:
  `consistent_with_declared_unadjusted`, `declared_unadjusted_falsified`, or
  `inconclusive`. A missing/incomplete/invalid required pair is
  `inconclusive`, never a pass or falsification.
- A positive result means only that these retained rows exhibit the expected
  large split signature. It does not verify all adjustment behavior, qualify
  corporate actions, resolve Norgate semantics, remove survivorship, or permit
  a model, rank, replay, PnL claim, local-paper intent, KIS Paper action, or
  GPU job.

## Authority And Boundaries

- Use only existing local cache bytes and offline code. Docker research remains
  network-disabled with read-only data mounts and external artifacts under
  `/app/model_artifacts` mapped to `D:\thericher-v2\model-artifacts`.
- Do not read `.env`, credentials, tokens, account data, or KIS responses. Do
  not call KIS, Tiingo, another provider, broker, or live route. Do not mutate
  any cache, scheduler, task, cursor, or raw data.
- Persist no raw rows, prices, volumes, returns, timestamps, event dates,
  labels, predictions, model artifacts, account facts, broker bodies, or
  secrets. The receipt may retain only source hashes, fixed-contract identity,
  symbol names, categorical per-symbol results, aggregate counts/categories,
  and scope limitations.
- Do not introduce a dependency, public model/weight, runtime, worker, or
  scheduler. Do not create a corporate-action sidecar or change the existing
  dual-source conformance receipt.

## Parallel Work Packages

1. **Data:** implement the deterministic in-memory KIS D1 split-signature
   audit and immutable external receipt. It must reattest the frozen source
   identity and fail closed to `inconclusive` when a required event pair is not
   available or valid.
2. **Engine Research:** define the exact interpretation boundary: all three
   audit outcomes remain non-model and non-Paper; only a later independently
   designed input contract may consume a narrow source-semantics fact.
3. **Temporary Validation:** add focused tests for the three aggregate
   outcomes, fixed threshold/event contract, no-network/no-credential route,
   no raw value/date persistence, immutable receipt reattachment, and external
   artifact-root enforcement.
4. **Data / temporary Validation:** reattach any automatic broad postrun only
   through its existing receipt-bound path. Its absence or scoped retry does
   not delay this audit.

## Completion

- The audit reattests one frozen KIS D1 source and produces only the allowed
  categorical external receipt.
- The result neither changes the existing Norgate/KIS conformance receipt nor
  makes any research, model, ranking, PnL, local-paper, KIS Paper, or live
  action eligible.
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

`Add D1 source conformance contract`
