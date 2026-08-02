# Next Codex Goal

Read `HANDOFF.md`, `VISION.md`, `ARCHITECTURE.md`, `AGENTS.md`,
`DECISIONS.md`, `RUNBOOK.md`, `agents/README.md`, `agents/data.md`,
`agents/engine-research.md`, `agents/research-steward.md`,
`agents/execution.md`, and `agents/orchestration.md` first. Then continue from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build and verify `norgate-active-build-revision-probe-v1`.

Determine whether the current local Norgate Platinum build reproduces the
immutable fixed `SPY/QQQ/IWM` D1 development source used by prior offline
research. This is a Data foundation fact needed before the first new
source-local model campaign. It is not a model, PnL, ranking, Paper, or GPU
objective.

## Frozen Scope

- Use only the existing Windows `norgate-host` reader and local
  `D:\market_data` source. Do not update/download Norgate data, call KIS, read
  `.env` or credentials, access accounts, submit/cancel an order, enable live
  behavior, use a paid service, or expose a public endpoint.
- Compare the active build and immutable materialization on their exact shared
  daily-bar contract. Write only an aggregate source-safe receipt under the
  external artifact root: hashes, counts, categorical outcome, and safe
  divergence metadata. Never emit raw bars, dates, source paths, or secrets.
- One bar-level divergence is a categorical `revision_detected` outcome. Do
  not normalize, conceal, tune around, or treat the old static materialization
  as stable under the active build after that result.
- Existing target-free trio diagnostic protections are already present in
  current `main`: one-shot execution, US/UTC panel checks, typed
  result/arithmetical validation, and no public plan injection surface. Repair
  only the remaining receipt-boundary gap: canonicalize and revalidate the
  exact typed result immediately before receipt write, instead of trusting an
  overridable `safe_payload` from a subclass or test injection. Do not refactor
  the diagnostic or create a new strategy template.
- PIT availability, historical revision policy, entity identity, adjustment
  semantics, and corporate-action completeness remain declared limitations.
  Do not dispatch LightGBM, PatchTST, Chronos, LSTM, TCN, Transformer, or GPU
  work until the next distinct model campaign contract is frozen.

## Required Work

1. Data: inspect the existing host reader and immutable snapshot contract, then
   implement the smallest active-build revision probe and source-safe external
   receipt. Prove data access stays on `D:` and receipt output is redacted.
2. Engine/Validation: add the smallest runner-boundary proof that a mutated
   typed/subclass result, invalid arithmetic, or invalid status/count pairing
   fails before a receipt is written. Re-run the existing trio diagnostic
   focused tests to reattest the unchanged target-free-plan boundary.
3. Validation: add deterministic fake-provider tests for exact agreement,
   divergence, unavailable/malformed source, artifact-root containment, and
   raw-data redaction.
4. Update the Data, Engine, Research Steward, orchestration, handoff, and
   decision stateboards with the exact source-safe outcome and next readiness.
5. Claude already challenged the broader package as `supported-with-limits`:
   retain the active-build divergence falsifier and defer strategy-template
   work. Ask again only if implementation widens source access or proposes a
   model campaign.

## Verification

Run focused tests, then:

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example --profile research config --quiet
```

## Completion

Report the revision-probe outcome, focused diagnostic reattestation, tests,
commit hash, intentionally omitted model/GPU work, and the next recommended
objective. Commit and push completion evidence before replacing this file with
exactly one next objective and continuing.
