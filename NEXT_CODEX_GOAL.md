# Next Codex Goal

## Objective

Build `same-cycle-target-allocation-v1`: add a pure caller-owned, deterministic
same-cycle allocation helper for an ordered set of already-proposed
multi-symbol `TargetExposureProposal`s. It advances the target-position layer
of the engine while keeping opportunity selection, trade policy, model choice,
and deterministic execution separate. It must consume no market data, call no
provider or broker, load no model, reserve no capacity, and create no order.

The completed prior objective updated only the existing daily operating-review
automation prompt. Its ID, daily recurrence, active status, model, project
target, and workspace were read back unchanged; no secret-like value appeared.

## Hard Boundaries

- Do not call KIS, submit or modify Paper orders, manually invoke a task, or
  alter a broker route, order behavior, credential path, dashboard,
  Docker/runtime, capital rule, or live behavior.
- Do not create an opportunity rank, a strategy score, a learned allocation,
  an ensemble, a reserve, or a broker-facing order path.
- Do not read or expose `KIS_LIVE_*`, secrets, account facts, private intents,
  order identifiers, or raw market data.

## Required Work

1. Ask Claude CLI for a short falsification-first architecture drift-check
   before implementation. Treat an unavailable response as
   `review_unavailable`, not assent.
2. Extend the existing single-proposal allocator with a separate pure cycle
   helper. It must use only caller-provided order and one consistent portfolio
   snapshot, reject duplicate symbols or inconsistent snapshot facts, and apply
   the existing scale-then-cap rule serially without treating an unexecuted
   reduction or exit as released capacity.
3. Keep every output a model-side `TargetExposureProposal`; do not select,
   reorder, score, mutate, persist, or execute a proposal. Document the
   ownership boundary in `ARCHITECTURE.md` and the Engine stateboard.
4. Add focused tests for deterministic caller order, shared-cap exhaustion,
   duplicate or mismatched snapshots, stale/unqualified inputs, and the
   no-capacity-release-on-unexecuted-exit rule. Include a no-I/O guard.

## Verification

Run focused allocation tests, then:

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Add same-cycle target allocation`
