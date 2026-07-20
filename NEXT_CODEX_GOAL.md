# Next Codex Goal

## Objective

Complete the remaining 2026-07-20-only, metadata-only KIS paper raw-`1m`
regular-session observation for `QQQ`/`NAS`. Its only valid outcomes are
`observed` or `rejected`; neither is a capability promotion or a market-data
archive.

The separate QQQ/SPY historical capability probe is terminally `rejected`
(`daily_response_rejected`) at
`D:\thericher-v2\model-artifacts\data-agent\kis-paper-historical-data-probe\20260720T001125Z\summary.json`
(SHA-256 `3883d32289bd06196ca28823cc041d0780172add4848661d185c24e07cde0c8f`).
It consumed one token and two daily attempts, never made a raw-`1m` request,
and must not be retried.

## Current Authority

- `THERICHER_MODE=off` stays unchanged.
- The operator authorizes `KIS_PAPER_*` only for the remaining named read-only
  raw-`1m` probe. The approved symbol is `QQQ` on `NAS`.
- Do **not** call order, cancel, account, position, buying-power, open-order,
  or any `KIS_LIVE_*` endpoint. Do not submit a paper or live order.
- Do not print or persist a token, credential, account identifier, raw quote,
  price, volume, response body, cursor, or market-data row. The external
  summaries may contain only fixed scope, call counts, date/timestamp bounds,
  field-presence, paging, and data-fitness facts.

## Current Foundation

- `execution.kis_market_data` accepts only paper OAuth, overseas daily, and
  overseas raw-`1m` requests through a direct-only, redirect-rejecting
  transport. It blocks account, order, cancel, and live paths before opening a
  connection, and enforces the current `QQQ`/`SPY`, `NAS`, fixed-query, and
  three-pages-per-kind scope below its CLI scripts.
- `execution.kis_historical_probe` completed terminally as `rejected` with
  `daily_response_rejected`: one token, two daily attempts, zero raw-`1m`
  attempts, no account/order/live endpoint, and no retained raw market data.
  Its external lifecycle is `reserved -> network_started -> summary_written`,
  so the historical objective cannot be retried or widened.
- The date-limited raw-`1m` runner is separately offline-tested. Before it can
  read config, it requires an explicit `--confirm-no-exception` flag after an
  independent official Nasdaq calendar check. Its first result stays `observed`
  or `rejected`.
- `research.kis_paper_baseline` remains fail-closed: the current KIS raw-`1m`
  capability is not qualified, and a direct caller-created `QUALIFIED` state
  also lacks the empty Data-owned contract-SHA qualification binding. No model
  proposal or paper order can result. Local replay remains offline with fill
  source `local_paper`.
- Its pure proposal contract now records immutable evaluation `as_of`
  separately from the completed feature-window end. Even a later relaxed
  freshness setting cannot emit a ready proposal at or after that window's
  next `10m` boundary; it returns an explicit expired abstention instead.
- Data now has a pure explicit-UTC-session resampling primitive that surfaces
  skipped buckets. It infers no calendar and is not connected to this baseline,
  a KIS adapter, `1h`/`3h`, a model, or paper execution in this objective.

## Required First Reads

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `VISION.md`, `ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`,
   `RUNBOOK.md`, `agents/data.md`, `agents/engine-research.md`, and
   `agents/execution.md`.
3. Before any later promotion from `observed` to `qualified`, obtain the
   required short Claude falsification-first review. This goal has no promotion.

## Work Packages

### Historical Outcome

The historical summary has been interpreted as a bounded daily rejection only.
It does not alter raw-`1m`'s `observed` state or support a dataset, cache,
feature activation, qualification, retention, storage-rights, timestamp,
paging, data-quality, point-in-time, or model claim.

### Execution: Scheduled Raw-`1m` Observation

1. During the fixed 2026-07-20 Nasdaq window only, independently confirm there
   is no official Nasdaq session exception. Then run exactly once:

   ```powershell
   uv run python scripts\probe_kis_paper_raw_minute.py --execute --confirm-no-exception
   ```

2. It may issue one paper token, one `QQQ`/`NAS` first page, and at most one
   documented continuation. It cannot call any account/order/live endpoint or
   promote the capability.

### Engine Research

Keep the 90-`1m` / 18-`5m` / 9-`10m` baseline unchanged and abstaining. Do not
start GPU work, learned models, ensembles, `1h`, `3h`, adjusted prices,
corporate actions, news, order-book inputs, external universe work, or KIS
paper submission from either capability probe.

## Boundaries

- No raw KIS bytes or caches in Git, `D:\market_data`, or artifacts.
- No broker account, position, open-order, orderable-funds, cancel, submit, or
  live call; no capital envelope is implied.
- No credential, token, account value, account identifier, raw price, volume,
  cursor, response body, or raw row in console output, logs, artifacts, Git,
  or Claude prompts.
- A reserved, `network_started`, or completed lifecycle state is never retried.
- The completed historical lifecycle blocks all retries. Do not make a
  historical-data, model, retention, storage-rights, or profitability claim
  from either bounded sample.

## Completion

After the remaining permitted run, inspect only sanitized external evidence,
update the Data and Execution stateboards plus `HANDOFF.md` and `DECISIONS.md`,
then run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
```

Commit and push completed bounded work. Keep this goal active until the
date-limited raw-`1m` observation is either recorded, rejected, or has a
durable unrecoverable reservation state; then refresh it to one next objective.
