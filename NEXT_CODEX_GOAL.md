# Next Codex Goal

## Objective

Accumulate prospective KIS-native SPY/QQQ regular-session minute coverage, then
freeze and run the first multi-session chronological intraday CPU validation
campaign with naive baselines. Keep the existing KIS Paper execution-learning
loop and the intraday head collector independent and active.

This advances data-to-model evidence. It is not a profitability claim and does
not require a GPU job until the campaign contract is genuinely ready.

## Standing Authority And Boundaries

- All private `KIS_PAPER_*` data, account, order, modify, cancel,
  reconciliation, raw-retention, and goal-owned schedule work is authorized.
- Retain raw market data only under `D:\\market_data`; keep generated artifacts
  under `D:\\thericher-v2\\model-artifacts` or `/app/model_artifacts`; never
  put either in Git.
- Do not output or commit credentials, account identifiers, raw quote/broker
  bodies, raw order IDs, or private intent state.
- Do not read `KIS_LIVE_*`, call a live host/route, use real capital, buy data,
  accept unclear rights, or expose a public service.
- An old marker, partial data run, or unresolved distinct Paper intent never
  pauses fresh correctly scoped Paper data, schedule, account, or order work.

## Required First Reads

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`, and
   `RUNBOOK.md`.
3. Read `agents/data.md`, `agents/engine-research.md`, and
   `agents/execution.md`.
4. Inspect current intraday backfill/head indexes and active external artifacts
   before any network call or campaign decision.
5. Ask Claude for a concise falsification-first check before freezing the first
   chronological intraday campaign, interpreting an unexpectedly strong result,
   or changing the KIS execution surface. Never send secrets, raw rows, or
   broker output.

## Role-Owned Work

### Data Agent

1. Maintain the cursor-resuming cache and separate head cache for `QQQ/NAS` and
   `SPY/AMS`. Continue bounded Paper-only collection during useful US sessions;
   record safe session coverage and gaps without provider mixing or gap filling.
2. Reattest candidate complete sessions using the explicit 2026 exchange
   calendar window. Preserve that KIS bar open/close semantics remain an input
   limitation unless source evidence resolves them.
3. Once the cache has enough distinct complete regular sessions for the first
   fixed chronological split, produce a compact dataset manifest and exact
   input identity for Engine Research. If it does not yet, keep collection
   running and state the exact count/coverage still missing.

### Engine Research Agent

1. Draft the first frozen intraday campaign contract from only the supplied
   KIS cache: sessions, split, target timing, fees/slippage, naive comparators,
   metrics, stop rules, and external artifact root.
2. Run CPU `flat`, `always_long`, and `previous_bar_direction` local-paper
   baselines when the contract's multi-session input is ready. Preserve
   replayable fills and PnL attribution outside Git.
3. Keep breadth, depth, ensemble, and replication queues current. Do not launch
   CUDA training until the frozen multi-session CPU campaign has completed and
   the evidence supports an eligible next hypothesis.

### Execution Agent

1. Keep the quote-derived KIS Paper session active, reconcile each durable
   intent on its own identity, and integrate the next sanitized outcome.
2. Fix only concrete virtual-route, safe-projection, pacing, or reconciliation
   defects. A distinct Paper action remains routine and need not wait for an
   unrelated older intent.

## Completion Evidence

- Safe coverage and recovery evidence for independent backfill/head caches.
- A frozen multi-session KIS intraday campaign contract, or a precise remaining
  coverage count while collection continues.
- CPU naive local-paper validation and replayable external artifacts when the
  data is ready; otherwise no fabricated labels or performance claims.
- No live route, secrets, raw data, or generated artifact committed to Git.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Add prospective KIS intraday validation loop`
