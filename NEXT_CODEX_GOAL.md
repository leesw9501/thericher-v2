# Next Codex Goal

## Objective

Establish the first offline, dual-source D1 metadata-conformance contract for
future KIS-reconstructible research inputs.

The contract compares the already-local frozen Norgate D1 development panel
with an already-local KIS Paper D1 cache. It answers only whether their source
metadata and available field semantics can support a later source-parameterized
feature interface. It does not claim that the sources are interchangeable or
that a Norgate result transfers to KIS.

## Start

1. Run `./scripts/start_next_codex_task.ps1` and read `HANDOFF.md`, `AGENTS.md`,
   `ARCHITECTURE.md`, `DECISIONS.md`, `RUNBOOK.md`, and active stateboards.
2. Inspect the installed broad-D1 task and source-safe postrun roots. Do not
   start, stop, duplicate, or alter the collector.
3. Reattest the exact frozen Norgate panel and select one existing KIS Paper D1
   cache through an offline loader. Do not invoke a provider, credential, or
   mutable cache path.
4. Start from Claude's `supported-with-limits` challenge: static Norgate alone
   cannot prove KIS reconstruction; its adjustment semantics and survivorship
   remain limitations; full-panel target-free weights cannot be reused by a
   future held-out label campaign.

## Authority And Boundaries

- The broad collector remains the sole owner of KIS Paper credentials, network,
  cursor, pacing, raw cache, and postprocess invocation. This goal makes no
  manual KIS call and reads no credentials.
- Use only existing local sources and offline paths. Docker research remains
  network-disabled with read-only data mounts and external artifacts under
  `/app/model_artifacts` mapped to `D:\thericher-v2\model-artifacts`.
- Inspect source metadata in memory only. Persist only source-safe identities,
  field-presence/absence, declared semantics, aggregate session/timezone/gap
  categories, and conformance result categories. Do not persist raw rows,
  prices, volumes, returns, timestamps, labels, predictions, account facts,
  broker bodies, or credentials.
- Do not pool, join, normalize, or substitute row values across providers. Do
  not construct labels, features, costs, a rule, a model, an encoder probe,
  a rank, an ensemble, a replay, PnL, a local-paper intent, or a KIS Paper
  action.
- An unknown or unqualified adjustment/corporate-action, symbol-identity,
  timezone/session, or gap/halts semantic must remain `unknown` or
  `semantics_conflict`; it cannot become a positive transfer or model-eligibility
  claim.
- Do not load a public model/weight or introduce a runtime/dependency. A future
  causal campaign must refit any representation inside its own training fold.

## Parallel Work Packages

1. **Data:** implement an offline source-parameterized D1 metadata attestation
   for the named Norgate and KIS inputs. It must reattest both source identities,
   report only allowed aggregate metadata, and write an immutable external
   conformance receipt. It may return `metadata_conforming_with_limits`,
   `semantics_conflict`, or `input_unavailable`; none enables a model.
2. **Engine Research:** define the smallest shared D1 interface map from the
   attestation: source field availability, completed-session timing, and each
   source's declared/unknown semantics. It must make no causal-label, training,
   or GPU dispatch decision. Preserve static-survivorship and adjustment limits
   as interface facts rather than a kill-test or a score.
3. **Temporary Validation:** add focused tests that prove the attestation needs
   no network, KIS, broker, credential, source row persistence, cross-source
   pooling, label, model, or PnL path. Test positive metadata-only conformance,
   an unqualified semantic conflict, and external-artifact-root enforcement.
4. **Data / temporary Validation:** when the automatic broad postrun receipt
   appears, reattach it only through the existing offline receipt-bound path.
   Its absence or scoped retry does not delay the conformance work.

## Completion

- The dual-source receipt pins both local source identities and records only
  allowed aggregate metadata plus a categorical result.
- The shared interface map makes no transfer, adjustment, PIT, survivorship,
  model, profitability, ranking, Paper, or live claim.
- A mismatch is immutable useful evidence with a scoped next recovery action;
  it is not a company-wide pause.
- Any broad postrun receipt available during the objective is handled through
  its existing offline path only.
- Refresh Data/Research/orchestration stateboards, replace this file with one
  next objective, verify, commit, push, and continue.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Add D1 source conformance contract`
