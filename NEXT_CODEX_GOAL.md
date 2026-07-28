# Next Codex Goal

## Objective

Establish and start a resumable, source-separated KIS Paper D1 broad-backfill
cache from the already hash-attested KIS current-directory source.

This produces current-listing, non-PIT daily OHLCV coverage for later
field-compatible research. It is not a historical-universe, ranking,
corporate-action, profitability, or Paper-trading claim.

## Start

1. Run `./scripts/start_next_codex_task.ps1` and read `HANDOFF.md`, `AGENTS.md`,
   `ARCHITECTURE.md`, `DECISIONS.md`, `RUNBOOK.md`, and active stateboards.
2. Reattach the existing KIS current-directory manifest/listing identity and
   the fixed daily collector/backfill contracts without printing raw symbols,
   rows, prices, volumes, tokens, or account identifiers.
3. Ask Claude for a concise falsification-first drift check before generalizing
   the collector or adding a scheduling/lease mechanism. Include current-listing
   survivorship, exchange mapping, fresh-head priority, recovery, and storage
   kill tests; do not send secrets or raw provider data.

## Authority And Boundaries

- `KIS_PAPER_*` is standing-authorized for this **market-data-only** work.
  Use no account, position, open-order, quote, submit, modify, cancel, or live
  endpoint. Never read or route `KIS_LIVE_*`.
- Read credentials only inside the existing credentialed market-data client;
  never print, log, persist, send to Claude, or commit them.
- Create a **new** D:-resident cache root and durable index. Do not widen or
  mutate terminal QQQ/SPY/IWM or NAS cache contracts.
- Build targets only from the hash-attested KIS current-directory source.
  Do not seed targets from the static Norgate survivor panel, infer an exchange,
  claim point-in-time membership, or join rows across providers.
- Use one active collector/client/token for this cache, the measured one-second
  request-start gate, and the existing categorical recovery behavior. A valid
  in-memory client must not wait for the five-minute cross-process token-start
  guard. Do not request-flood or foreground-sleep.
- Fresh-session head collection retains priority. The new collector must use an
  explicit owned lease or non-overlapping schedule before it can run recurring
  catch-up work; a categorical cooldown blocks only its owned worker.
- Raw market data and registry bytes remain on `D:\market_data`; receipts and
  generated artifacts remain under `D:\thericher-v2\model-artifacts`; neither
  belongs in Git. Respect the 20% warning and 15% free-space floor.

## Work

1. **Data:** create an external, hash-attested current-listing registry with
   typed `non_pit` and `non_ranking` scope. Preserve per-target symbol/exchange,
   initial cursor, state, and recovery fields only outside Git.
2. **Data:** generalize the existing private daily collector/backfill contract
   so a validated registry injects the exact symbol/exchange allowlist. It must
   validate registry-parent drift before constructing a client, retain each
   target's cursor and source-safe progress, and use existing failure taxonomy.
3. **Validation:** add focused tests for registry drift before any client call,
   target-specific exchange allowlists, external-only cache/index paths,
   target-local failure/recovery, non-PIT scope propagation, and absence of
   broker/account/live/credential access.
4. **Data:** run one deterministic eight-target bootstrap, with at most one
   bounded daily chunk per target. Record only source-safe accepted-page,
   categorical-error, cursor, range, storage, and recovery facts. If a target
   fails, scope the result to that target and continue ready targets.
5. If the bootstrap has usable accepted data, install or start one bounded,
   observable continuation worker for this exact cache. It may yield on lease,
   cooldown, or next due; Codex continues unrelated ready work rather than
   sleeping.

## Completion

- A new external registry and cache index prove their parent identity and
  non-PIT/non-ranking scope.
- The first eight-target bootstrap has a source-safe external receipt with
  accepted or precisely scoped source-limited/deferred outcomes.
- A continuation/recovery path is owned and observable without duplicate
  collectors or interference with fresh-head collection.
- Tests prove no account/order/live route, provider-source blend, raw Git data,
  credential output, or model/paper promotion was introduced.
- Refresh affected stateboards, replace this file with exactly one next
  objective, then continue.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Start KIS broad D1 backfill`
