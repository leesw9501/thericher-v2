# Next Codex Goal

## Objective

Turn the already-installed Norgate US Stocks Platinum trial into one bounded,
date-indexed daily research input contract for a fresh future engine family.

The objective is Data-led: establish exactly what the local Windows Norgate
trial can provide for date-specific US membership/listing and unadjusted daily
OHLCV over its observed two-year horizon. Engine Research may prepare the
consumer mapping in parallel, but no model, allocation, Paper input, or
profitability claim may use the result until its source limitations are frozen.

## Start

1. Run `./scripts/start_next_codex_task.ps1` and read `HANDOFF.md`,
   `AGENTS.md`, `ARCHITECTURE.md`, `DECISIONS.md`, `RUNBOOK.md`, and the active
   stateboards.
2. Reattach the completed QQQ selection-null and target-exposure allocator as
   closed, independent evidence. Do not reuse the QQQ sessions for a new
   candidate or treat the allocator as a trained model.
3. Ask Claude for a short falsification-first check before relying on any
   point-in-time membership, adjustment, or availability interpretation. A
   timeout is `review_unavailable`, not support or a global hold.

## Work

1. **Data:** use only the locally installed, operator-authorized Norgate trial
   on Windows. Freeze a capability precommit for one complete trial-horizon
   S&P 500 membership union, date-specific membership/listing fields,
   unadjusted D1 OHLCV, and corporate-action marker availability. Make no
   network, credential, KIS, broker, paid, or Docker-provider call.
2. **Data:** construct or reattest one canonical external D: snapshot and
   compact manifest under the market-data root. It must keep raw/source data
   outside Git, bind exact package/database/scope identities, preserve dynamic
   membership separately from price rows, and declare adjustment and
   availability-time limitations rather than guessing them. A failed capability
   may end as `input_unavailable` or `unqualified`; it must not be repaired by
   blending another provider.
3. **Engine Research:** in parallel, define only the KIS-shaped consumer
   mapping for completed daily OHLCV, a causal decision timestamp, temporal
   split, costs, naive baseline, and strongest leakage kill test. Do not train,
   score, rank, tune, allocate GPU, create an ensemble, or form a Paper intent.
4. Add focused host-safe tests with fake Norgate loaders or immutable local
   fixtures. Prove no credential/network/broker path, D:/Git storage isolation,
   date-indexed membership handling, source-limit propagation, and that an
   unqualified source cannot become a model or Paper input.
5. Record only the source contract, consumer mapping, and next recovery fact in
   the Data/Engine stateboards. Do not create a report family, approval gate, or
   durable sub-agent.

## Completion

- One external source contract/snapshot is `qualified_for_offline_research`,
  `unqualified`, or `input_unavailable`, with its exact limitations explicit.
- No raw Norgate rows, credentials, model artifacts, KIS calls, broker orders,
  GPU job, model result, or Paper behavior enters Git or this goal's result.
- Engine Research has only a frozen consumer outline if the Data contract is
  usable; any later candidate is a new objective with its own precommit.
- Refresh this file with exactly one next objective, verify, commit, push, and
  continue. Scheduler-owned KIS work remains independent.

## Verification

```powershell
uv run --extra dev pytest -q <changed paths>
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Add target exposure allocation foundation`
