# Next Codex Goal

## Objective

Qualify the MIM-30 SPY long-only derivative one-minute input contract from the
existing local KIS cache and the KIS Paper market-data route.

The source paper's MIM rule is directional: use the previous regular-session
close through 10:00 ET as a direction fact, then go long when positive and
short otherwise from 15:30 to 16:00 ET. This project starts only its explicit
long-only derivative: positive signal means long and all other cases are flat.
It is not a paper replication. This objective is about reconstructible data and
causal timing only; it does not train, tune, select, ensemble, or route a model.

## Start

1. Run `./scripts/start_next_codex_task.ps1`, then read `HANDOFF.md`,
   `AGENTS.md`, `ARCHITECTURE.md`, `DECISIONS.md`, `RUNBOOK.md`, and the active
   Data, Engine Research, Research Steward, Execution, and orchestration
   stateboards.
2. Engine Research reattaches the independently retrieved original MIM-30
   source as a source-safe external
   receipt: retrievable identifier, stated sample/scope, stated time boundaries,
   source license/copyright facts, and the long-only derivative reconstruction
   outline.
3. Ask Claude for a short falsification-first check before freezing any
   source-data/campaign contract. Include no credentials, raw rows, prices,
   account facts, fills, or sealed labels.

## Boundaries

- `KIS_PAPER_*` may be used only by the Data-owned SPY/AMS market-data client.
  Account, position, open-order, quote, broker order, submit, modify, cancel,
  and every `KIS_LIVE_*` path are out of scope.
- Keep raw data and collector state under `D:\market_data`; keep only
  source-safe receipts under `D:\thericher-v2\model-artifacts`. Never put raw
  rows, tokens, headers, account values, or model artifacts in Git or Claude.
- Keep one reusable in-memory KIS client/token for an active collector. Measure
  one pacing variable at a time and retain the durable cursor; do not use a
  parallel request flood or an unbounded retry loop.
- Do not start a model, GPU job, parameter sweep, backtest, Paper action, or
  public service in this objective. A useful dataset contract may prepare a
  later CPU-first campaign only.
- Preserve at least 20 percent free space as a warning and never start new
  large collection work that would cross the 15 percent floor.

## Work

1. **Engine Research:** persist the original MIM source receipt and freeze the
   explicit derivative hypothesis without adding filters: SPY/AMS, prior regular
   close to 10:00 ET direction, long-only final-thirty-minute interval when
   positive and flat otherwise, no short, no QQQ expansion, no
   volume/volatility filter. Do not describe this as a source replication.
   Predeclare the
   future campaign's 60/20/20 chronological split, fixed `1.0x/1.5x/2.0x`
   Execution-attested cost band, flat and same-window always-long comparators,
   and strongest kill test: no positive after-cost sealed result at 1.5x costs
   or no improvement over always-long rejects the family without retuning.
2. **Data:** inventory the useful SPY/AMS one-minute local-cache subset from
   manifests/indexes before reading raw files. Count complete regular sessions
   with a reconstructible prior close, 10:00 ET boundary, and 15:30-16:00 ET
   segment. The existing read-only inventory has 20 such sessions; record
   source-safe span/count/completeness categories only.
3. **Data:** if the cache is short, run a bounded capability probe on the exact
   KIS Paper minute route using one reusable client. Establish temporal reach,
   page yield, continuation semantics, and measured accepted/error categories
   across a few widely separated dates. Do not claim source limitation from one
   empty page or infer a rate limit from a local sleep.
4. **Data:** when the probe establishes useful continuation, create or resume
   one durable SPY/AMS serial collector under `D:`. It must retain the source
   contract, cursor, accepted/categorical-failure page counts, tested pace,
   remaining-page estimate or `unknown`, ETA bucket or `unknown`, and recovery
   class. Continue this owned collector in the background; it must not hold
   Engine, Execution, or the foreground orchestrator.
5. **Validation:** reject any session with ambiguous ET/DST conversion, missing
   prior regular close, missing 10:00 boundary, early close, incomplete required
   minute bar, or source-contract mismatch. Confirm the probe/collector has no
   account/order/live path and retains no secrets in receipts. A 252-complete-
   session threshold controls only this MIM campaign; it is not a company hold.

## Completion

- A source-safe MIM receipt records the independently retrieved source facts,
  KIS route capability, local-cache/session coverage, and one of: `qualified`,
  `collection_in_progress`, or `input_unavailable`.
- If fewer than 252 qualifying sessions are presently available, retain the
  exact coverage/recovery fact and continue any useful owned collector; do not
  lower the threshold, synthesize a proxy, train a model, or turn the outcome
  into a Paper input.
- The next objective may use only a `qualified` MIM contract for a CPU-first
  frozen campaign. It may not reuse this objective to tune time boundaries,
  filters, or costs after observing data.
- Refresh this file with exactly one next objective, verify, commit, push, and
  continue. A Data-route limitation is lane-local; other ready work continues.

## Verification

```powershell
uv run --extra dev pytest -q <changed paths>
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
docker compose --profile research config --quiet
```

## Suggested Commit Message

`Qualify MIM-30 minute input`
