# Next Codex Goal

Read `HANDOFF.md`, `VISION.md`, `ARCHITECTURE.md`, `AGENTS.md`,
`DECISIONS.md`, `RUNBOOK.md`, `agents/README.md`, `agents/data.md`,
`agents/engine-research.md`, `agents/research-steward.md`,
`agents/execution.md`, and `agents/orchestration.md` first. Then continue from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build and run `norgate-broad-d1-active-build-conformance-taxonomy-v1`.

This Data-owned objective measures whether the immutable static Norgate broad
D1 development panel can be compared meaningfully with the active local
Windows Norgate build. Its only consumer is a later, separately frozen,
non-promoting broad engineering campaign. It must not turn a present-build
comparison into proof of point-in-time availability, adjustment semantics,
corporate-action correctness, membership continuity, a model input, or a
GPU/Paper/PnL decision.

## Frozen Scope

- Use only the existing hash-attested Norgate broad D1 panel: 523 selected
  symbols, 483 common sessions, and 252,609 retained rows. Read the matching
  range twice per symbol through one Windows-local `norgatedata` client.
  Do not update/download Norgate data, call KIS, read `.env` or credentials,
  access accounts, submit/cancel orders, enable live behavior, expose a public
  endpoint, or use a paid service.
- Retain raw bars only in the existing `D:\market_data` snapshot. Write a
  single immutable source-safe receipt under
  `D:\thericher-v2\model-artifacts`, never Git. Do not persist or print raw
  bars, dates, prices, row-level values, source paths, credentials, or error
  text.
- Run one serial local client; do not add artificial sleeps, an uncontrolled
  parallel reader flood, a scheduler, a model, a feature artifact, a GPU job,
  public weights, a sealed holdout, an ensemble, PnL, ranking, or Paper input.
  A failed symbol is evidence about this probe only and cannot pause other
  ready lanes.
- Keep the fixed-trio momentum and GBT families closed. Do not use this task to
  retune, promote, or reinterpret either outcome.

## Required Taxonomy

1. Reattach and validate the immutable broad panel before the active client is
   constructed. Freeze its dataset/manifest identity, selected-symbol count,
   common-session count, and complete D1 bar geometry.
2. For each fixed symbol, compare two active reads for repeatability and then
   compare the reference and active series by timestamp. Persist only the
   symbol, stable-reader category, reference/active/shared counts, missing and
   surplus session counts, and value-mismatch count on shared sessions.
3. Classify outcomes before the run:
   - `matching`: every symbol has repeatable exact session coverage and zero
     shared-session value mismatches;
   - `revision_detected`: all symbols are repeatable with exact coverage, but
     one or more shared-session OHLCV values differ;
   - `input_unavailable`: any active reader/client failure, nonrepeatability,
     absent symbol, or session-coverage mismatch. Preserve aggregate and
     per-symbol categorical counts without attributing it to data revision.
4. A matching receipt is only a current-build reproducibility fact for this
   frozen scope. A `revision_detected` receipt closes only a later consumer that
   requires exact values. An `input_unavailable` receipt closes only its own
   source-conformance attempt. None is a general Research, Paper, GPU, or
   operator gate.
5. Canonicalize Decimal representations before response hashing so equal
   numeric reads have one stable source-safe hash. Make every receipt
   provider-free reattachable and no-clobber/idempotent.

## Required Work

1. Data: implement the smallest Windows-host-only conformance module and
   runner. Reuse the existing broad-panel verifier and active-reader pattern,
   but do not generalize either into a new framework.
2. Tests: prove taxonomy classification for exact, value-mismatch,
   absent-symbol, missing/surplus-session, and nonrepeatable-reader cases;
   Decimal-hash stability; provider-free receipt reattachment; external-root
   containment; idempotence/no-clobber; and no network/credential/KIS/broker
   access or raw leakage.
3. Run the actual bounded local conformance once. Report only the safe
   categorical result, counts, hashes, artifact location, elapsed-time bucket,
   and source limitations. Do not lower or relitigate the taxonomy after the
   result.
4. Update Data, Engine Research, Research Steward, orchestration, handoff, and
   decision stateboards with the outcome and exact next readiness. Engine may
   prepare no more than the later consumer contract; it may not start a model
   from this panel in this objective.

## Claude Review

Claude returned `supported-with-limits` for this objective after rejecting the
naive one-count broad revision probe. Its required pre-registered boundary is
the value-mismatch versus symbol-absent/session-coverage taxonomy above.
Re-invoke Claude only if implementation broadens the taxonomy, a result is
interpreted as source-quality promotion, or a later consumer seeks model/GPU/
Paper consequences.

## Verification

Run focused tests, then:

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example --profile research config --quiet
```

If the clean-root helper precondition is still blocked by its known interrupted
run roots, do not delete, rename, or bypass them. Record that scoped recovery
fact and run the helper's independent fresh-root mode plus the remaining
verification commands.

## Completion

Report the taxonomy outcome, focused and full verification, artifact
location/hash, Claude result, elapsed-time bucket, commit hash, intentionally
omitted model/GPU/Paper/PnL work, and the next recommended objective. Commit
and push completion evidence before replacing this file with exactly one next
objective and continuing.
