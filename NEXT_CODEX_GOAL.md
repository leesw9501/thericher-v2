# Next Codex Goal

## Objective

Build `iwm-m1-prospective-observation-append-v1`.

Advance the market-data foundation by turning the isolated IWM/AMS current-head
route into an append-safe observation contract. Each successful observation
must retain or reference one immutable external snapshot and create one
explicitly selectable, source-safe v2 receipt. Identical content may reuse its
snapshot; changed content must remain a distinct immutable observation rather
than overwriting or mixing a prior head. This is prospective source-local data
mechanics, not historical M1 backfill, a qualified dataset, model input,
strategy, PnL, Paper order, account route, or generic scheduler platform.

## Hard Boundaries

- `KIS_PAPER_*` may be read only through the existing named IWM Paper
  market-data client, and only for the one bounded final observation attempt.
  Never print or persist credentials; never read or route `KIS_LIVE_*`.
- Keep IWM/AMS current-day, one-page, no-continuation scope. Do not add
  historical paging, an undocumented timestamp seed, parallel flooding, an
  account/order route, or a QQQ/SPY cache, cursor, task, or schedule change.
- Do not create a recurring scheduler, model, dataset qualification, research
  campaign, GPU job, local-Paper intent, broker-order path, public service, or
  mutable latest-observation fallback.
- Keep raw market data under `D:\market_data` and generated receipts under
  `D:\thericher-v2\model-artifacts`; never commit either.
- A failed, unavailable, or rate-limited observation attempt remains a scoped
  source-safe recovery fact. Do not foreground-wait or turn it into a hold on
  another ready lane.

## Required Work

1. Run a concise Throughput Review. Confirm that the completed selector makes
   repeated IWM observations safe to enumerate, while the current generic IWM
   WIP is current-head-only and does not prove historical M1 coverage.
2. Ask Claude CLI for a short falsification-first drift check before changing
   IWM snapshot/receipt/recovery semantics. Send no raw rows, values, paths,
   or credentials; do not wait for the result.
3. Freeze one append contract: observation identity, snapshot identity,
   same-content reuse, changed-head isolation, receipt atomicity, restart
   behavior, source-safe outcome categories, and the strongest corruption or
   conflicting-revision kill test.
4. Implement the smallest append API and opt-in CLI that can persist one
   immutable IWM current-head observation without changing the existing
   QQQ/SPY collector. A repeated identical head must not overwrite data; a
   changed head must not silently merge with a prior observation.
5. Add focused fake/local tests for identical repeated observations, a changed
   head, malformed or interrupted writes, selector replay of every retained
   observation, external-root/link rejection, and no account/order/network
   path before the explicit execute command.
6. Run CPU-only fixture smoke first. Then make at most one standing-authorized
   IWM/AMS KIS Paper market-data observation attempt through the new opt-in
   command. Record only source-safe aggregate/recovery evidence and reattach
   it with the explicit selector. Do not retry in the foreground.
7. Refresh Data and orchestration stateboards with the exact append outcome,
   pace observation, and next recovery fact. Explicitly record that historical
   coverage still needs its own endpoint-reach package.

## Verification

Run focused tests and the CPU smoke, then:

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Add IWM prospective observation append`
