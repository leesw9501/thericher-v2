# Next Codex Goal

## Objective

Turn `kis-paper-private-daily-backfill-v1` into the first usable KIS-native
daily research input for `QQQ`, `SPY`, and `IWM`.

The lane has begun with retained, hash-verified two-page chunks for
`QQQ/NAS`, `SPY/AMS`, and `IWM/AMS`. Continue the bounded private backfill and
build the smallest deterministic daily local-paper baseline that consumes only
the resulting KIS cache once the three symbols share enough completed sessions.

`KIS_PAPER_*` market/account/order calls, paper submission, and goal-owned
scheduling are standing-authorized. `KIS_LIVE_*` and real-money routes remain
unavailable.

## Required Reads

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `AGENTS.md`, `DECISIONS.md`, `RUNBOOK.md`,
   `agents/data.md`, `agents/engine-research.md`, and `agents/execution.md`.
3. Inspect the private daily backfill index and recent manifests without
   printing raw rows, credentials, or account values.
4. Ask Claude for a concise falsification-first review before freezing a daily
   research split, opening any holdout, or claiming a result beyond the naive
   baseline. Do not send credentials, raw rows, or holdout labels.

## Work Packages

### Data Agent

- Continue `scripts/backfill_kis_paper_private_daily.py --execute` as bounded
  worker invocations. Each invocation owns at most one two-page chunk; obey its
  persisted shared retry timestamp rather than bypassing a KIS token rejection.
- Keep raw snapshots, manifests, logical index, venue-attempt evidence, and
  cursors only under `D:\market_data`. Do not create a daemon or generic
  scheduler platform.
- Reconcile orphan snapshots before new KIS calls. Preserve the established
  `QQQ/NAS`, `SPY/AMS`, and `IWM/AMS` mappings; an accepted empty response is
  venue evidence only, not usable history.
- Add a strict cache loader that re-attests hashes, merges only exact overlap
  rows, rejects conflicting values, preserves `MODP=0_unadjusted`, and exposes
  the common completed-session intersection without mixing Tiingo, Norgate,
  Yahoo, or synthetic bars.
- Continue until the three symbols have at least 756 common completed sessions
  or the endpoint reaches a documented source exhaustion. Report a real source
  limitation, not a guessed rate-limit cause.

### Engine Research Agent

- Define the daily admission contract: at least 756 shared KIS sessions,
  explicit raw-price/corporate-action limitation, chronological 60/20/20 split,
  two-session purge and embargo, and a sealed holdout left unopened.
- Once the Data contract is met, implement and run the CPU-only
  `daily-three-etf-relative-strength-v0` baseline: 20-session raw return,
  choose one positive-strength ETF or abstain, `t+1` entry and `t+2` exit,
  existing local-paper costs and replayable `source: local_paper` fills.
- Maintain breadth and depth queues, but do not start CUDA training merely to
  occupy the GPU. A GPU candidate needs the frozen dataset, baseline result,
  campaign contract, and a distinct falsifiable hypothesis.

### Execution Agent

- Keep the daily baseline broker-free by default and translate eligible
  deterministic decisions to local-paper intents/fills.
- In parallel, prepare the smallest KIS Paper order-transport contract and
  paper-host-only route test. Paper submit/modify/cancel is authorized; do not
  issue a KIS order solely to satisfy this data objective.
- Preserve local-paper replay, event provenance, and PnL attribution so KIS
  Paper execution can reuse deterministic evidence when its adapter is ready.

### Validation

- Test cache/hash re-attestation, cursor continuation, cross-chunk exact
  deduplication, conflict rejection, source exhaustion, shared token pacing,
  and no Git/secret/live access.
- Independently validate the daily research split and local-paper replay before
  any model or GPU promotion claim.

## Operating Boundaries

- There is no paper-capital, profitability, dashboard, report, trade-count, or
  per-call approval gate.
- Private KIS raw-data retention on `D:` and goal-owned KIS Paper schedules are
  authorized. Retention metadata must state the actual result, never act as a
  permission switch.
- Do not read `KIS_LIVE_*`, call a live route, expose secrets, publish KIS
  data, or store raw market data/model artifacts in Git.
- Keep model artifacts under `D:\thericher-v2\model-artifacts` or
  `/app/model_artifacts` in Docker.
- Keep raw-minute collection separate. Daily data may support the daily
  baseline, but it does not validate intraday `1m`/`5m`/`10m`/`1h`/`3h` inputs.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
```

## Suggested Commit Message

`Build KIS daily research input`
