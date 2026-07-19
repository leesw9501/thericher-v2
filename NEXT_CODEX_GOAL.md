# Next Codex Goal

## Objective

Complete two strictly separated, metadata-only KIS paper market-data
observations without creating a market-data archive:

1. **Now:** run one bounded historical-data capability probe for `QQQ` and
   `SPY`, limited to a single paper token, at most three daily pages and three
   raw-`1m` pages in total.
2. **2026-07-20 only:** retain the existing one-shot `QQQ` raw-`1m`
   regular-session observation. It remains an `observed`/`rejected` result,
   never a capability promotion.

Both probes improve the data-collection and paper-readiness loops by recording
only whether KIS can provide the declared narrow inputs. They do not build a
training corpus, model input, cache, or trading feature.

## Current Authority

- `THERICHER_MODE=off` stays unchanged.
- The operator authorizes `KIS_PAPER_*` only for the two named read-only
  market-data probes. The approved symbols are `QQQ` and `SPY`; all requests
  use `NAS`.
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
- `execution.kis_historical_probe` owns the immediate fixed request sequence:
  one token; `QQQ` daily first page plus an optional `F` continuation; `SPY`
  daily first page; then the equivalent raw-`1m` sequence. It retains raw rows
  only in process memory while computing typed metadata.
- The historical probe writes one sanitized result below
  `D:\thericher-v2\model-artifacts\data-agent\kis-paper-historical-data-probe`
  and keeps an external `reserved -> network_started -> summary_written`
  lifecycle. A reservation blocks every retry.
- Its authorized invocation and current safe preflight stopped at the
  secret-safe configuration preflight with `config_missing`; no token, KIS
  request, reservation, or summary resulted. The two paper app values must be
  nonempty and appear in the approved `.env` prefix before any Tiingo, account,
  or live key before this still-unreserved call is retried.
- The date-limited raw-`1m` runner is separately offline-tested. Before it can
  read config, it requires an explicit `--confirm-no-exception` flag after an
  independent official Nasdaq calendar check. Its first result stays `observed`
  or `rejected`.
- `research.kis_paper_baseline` remains fail-closed: the current KIS raw-`1m`
  capability is not qualified, and a direct caller-created `QUALIFIED` state
  also lacks the empty Data-owned contract-SHA qualification binding. No model
  proposal or paper order can result. Local replay remains offline with fill
  source `local_paper`.

## Required First Reads

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `VISION.md`, `ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`,
   `RUNBOOK.md`, `agents/data.md`, `agents/engine-research.md`, and
   `agents/execution.md`.
3. Before any later promotion from `observed` to `qualified`, obtain the
   required short Claude falsification-first review. This goal has no promotion.

## Work Packages

### Execution: Immediate Historical Capability Probe

1. Confirm no existing reservation under the external control root, then run
   exactly once:

   ```powershell
   uv run python scripts\probe_kis_paper_historical_data.py --execute
   ```

2. Inspect only the sanitized terminal result, lifecycle marker, and
   `summary.json`. Do not inspect a raw response or retry after any reservation.
3. Record only technical support and limitations: response acceptance, daily
   OHLCV field presence, per-page bounds, `F` daily continuation availability,
   raw-`1m` continuation availability, timestamp bounds, overlap, and boundary
   continuity. Do not infer retention, rate limits, adjustment semantics,
   corporate actions, storage rights, point-in-time coverage, or model fitness.

### Data: Interpretation

1. Review the historical summary as metadata-only evidence. It can support or
   reject a future KIS-compatible input investigation, but cannot be copied to
   `D:\market_data`, a dataset manifest, a campaign, or a model queue.
2. Keep raw-`1m` capability state `observed` after either probe. Open-versus-
   close timestamp labels and persistent storage rights remain unresolved.

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
- Do not make a historical-data, model, retention, storage-rights, or
  profitability claim from these bounded samples.

## Completion

After each permitted run, inspect only sanitized external evidence, update the
Data and Execution stateboards plus `HANDOFF.md` and `DECISIONS.md`, then run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
```

Commit and push completed bounded work. Keep this goal active until the
date-limited raw-`1m` observation is either recorded, rejected, or has a
durable unrecoverable reservation state; then refresh it to one next objective.
