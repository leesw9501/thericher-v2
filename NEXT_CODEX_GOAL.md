# Next Codex Goal

## Objective

Reattest the frozen Norgate US trial D1 development panel against the updated
local database, then decide whether it has an independent broad
cross-sectional campaign input.

The only outcome is a source-safe readiness result: `ready`, `restated`,
`survivorship_unqualified`, or `input_unavailable`. This is Data-owned
validation of an existing local source, not a new model, ranking, ensemble,
GPU appointment, KIS action, or Paper input.

## Start

1. Run `./scripts/start_next_codex_task.ps1`, then read `HANDOFF.md`,
   `AGENTS.md`, `ARCHITECTURE.md`, `DECISIONS.md`, `RUNBOOK.md`, and the active
   Data, Engine Research, Research Steward, and orchestration stateboards.
2. Reattach the existing frozen panel contract:
   - dataset hash
     `sha256:3d0841b90ddfd8d861f2432e404617ec0fc6e1afb8c902a81972df518720402d`
   - 523 selected symbols, 483 common sessions
   - `2024-07-18` through `2026-06-22`
3. Use only the installed, official local Norgate Python interface and its
   actual active database root. Do not assume that a copied `D:` directory is
   the active root; do not parse `.ngdb` files manually, download data, make
   network calls, read `.env`, use KIS, or submit an order.

## Work

1. **Data:** record a source-safe fingerprint of the active Norgate database
   build using the existing official-interface helper. First measure the
   completed US-session tail strictly after `2026-06-22`; `126` common sessions
   is predeclared as the minimum for a later independent broad campaign's
   holdout allocation. If even the source-local calendar maximum is below 126,
   record `input_unavailable` and do not rebuild the 523-symbol panel merely to
   repeat a known-failing condition. This threshold controls only that
   prospective campaign; it does not block unrelated Data, Research, Execution,
   or Paper work.
2. **Data:** only if the tail passes, rebuild the exact frozen panel contract
   into a new external `D:\market_data` snapshot and compare its canonical
   identity with the frozen dataset hash. A difference is `restated`, not an
   invitation to train on a silently changed history.
3. **Data:** only if the tail passes, independently verify the original
   membership construction against `S&P 500 Current & Past`, reporting both at
   least one source-confirmed former member and the aggregate former-member
   count/share at the original as-of boundary. A current-only reconstruction is
   `survivorship_unqualified`. Report per-symbol tail availability as well as a
   common intersection; do not let a survivor-conditioned intersection hide
   missing symbols.
4. **Engine Research / Research Steward:** prepare no model or GPU job in this
   objective. Attach the readiness result to existing campaign custody and
   state whether a later distinct causal family can be frozen. Do not reuse
   already consumed broad-panel evaluation windows or call a short tail an
   independent validation set.
5. **Validation:** verify the result needs no credentials, network, broker,
   raw-row artifacts, or Git-stored market data. Keep any receipt under the
   external artifact root and update only the Data, Engine Research, Research
   Steward, and orchestration stateboards with aggregate evidence.

## Completion

- The active Norgate build fingerprint and post-`2026-06-22` completed-session
  count are recorded externally. Exact panel comparison, membership result, and
  per-symbol tail availability are required only when the predeclared tail
  minimum passes.
- The result is exactly one of `ready`, `restated`,
  `survivorship_unqualified`, or `input_unavailable` with a concrete recovery
  fact.
- No Norgate download, KIS call, credential read, model training, GPU job,
  ranking, model selection, ensemble, Paper action, or live behavior occurs.
- Refresh this file with exactly one next objective, verify, commit, push, and
  continue. A source-local deficiency remains lane-local and must not create a
  global wait.

## Verification

```powershell
uv run --extra dev pytest -q <changed paths>
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Reattest Norgate broad panel input`
