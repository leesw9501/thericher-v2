# Next Codex Goal

Read `HANDOFF.md`, `VISION.md`, `ARCHITECTURE.md`, `AGENTS.md`,
`DECISIONS.md`, `RUNBOOK.md`, and the active stateboards in `agents/` first.
Then continue from `C:\Users\Public\Documents\thericher-v2`.

## Objective

Build `profiled-mtf-flattened-control-v1`: add one small, pure deterministic
flattened control view over an existing `NormalizedCompletedBarProjection`.
It must publish the exact `1m`, `5m`, `10m`, `1h`, and `3h` block order,
offset, length, and normalization-anchor policy for a later MLP-style control.
The existing projection already exposes immutable per-timeframe sequences, so
do not wrap or align them for LSTM, causal-TCN, or attention work yet. This
advances feature/model research while forward data accumulates; it is not a
model selection, training, PnL, Paper, or GPU-utilization objective.

## Boundaries

- Before architecture-changing edits, ask Claude for a concise
  falsification-first drift check on whether the adapter duplicates an existing
  projection/window contract or weakens its causal identity.
- Use injected or deterministic in-memory projections only. Do not read KIS,
  credentials, `.env`, caches, or network state; do not create a market-data
  artifact or a fresh forward observation.
- Do not train a model, load public weights, create a checkpoint, score a
  target, choose a window profile or model family, claim performance, touch
  `local_paper`, or call a broker.
- Preserve `NormalizedCompletedBarProjection` as the source of causal-window,
  source-contract, profile, cutoff, and projection identity. Do not add a
  second resampler or a generic feature platform.

## Required Work

1. Inventory the existing projection, causal window, and sequence-architecture
   APIs. Add only the smallest typed flattened view and published block layout;
   do not re-export per-timeframe sequences the projection already exposes.
2. Bind the view to one explicit profile, source identity, cutoff, feature
   timestamp, per-timeframe window ends, projection digest, and canonical
   `(timeframe, offset, length, anchor policy)` layout. It must reject a wrong
   type, identity/geometry mismatch, reordered layout, or a projection that is
   not already causal and structurally valid.
3. State the precise boundary: this view validates inherited projection identity
   and geometry, not independent value provenance. Keep PyTorch optional and
   out of module import. Do not add a trainer, model registry, artifact writer,
   CUDA appointment, or cross-timeframe sequence alignment.
4. Add focused tests for deterministic identity, flattened/per-timeframe
   geometry, mutation sensitivity, causal rejection, and import/no-I/O
   isolation. Update the Engine and orchestration stateboards with the exact
   next research dependency rather than a new queue.

## Completion Evidence

- a pure flattened control view composes with the existing causal projection;
- no data, credential, broker, Paper, model-weight, or GPU side effect occurs;
- focused tests demonstrate causal and identity containment;
- commit and push, then replace this file with exactly one next objective.

## Verification

```powershell
uv run --extra dev pytest -q <changed focused tests>
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example --profile research config --quiet
```
