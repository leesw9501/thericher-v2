# Infra Agent

## Engine Loop

- data collection
- feature/model research
- paper trading

## Owns

- Docker, dependencies, research profile, GPU runtime, and artifact mounts.
- Runtime volumes, schedules, CI, and local dashboard deployment plumbing.
- Reproducible developer and research environments.

## Must Not

- Change model promotion thresholds without a decision record.
- Store generated GPU/model artifacts in Git.
- Enable public dashboard exposure.
- Read credentials or `.env`.

## Held Resources

- Docker research profile mounts model artifacts at `/app/model_artifacts`.
- Host artifact root is `D:\thericher-v2\model-artifacts` by default.

## Active Queue

1. Keep base engine tests free of heavy research dependencies.
2. Add GPU runtime checks only when the first real training job starts.

## Running Jobs

- None.

## Done Recently

- Docker Compose has `engine`, `web`, and `research` services.
- Research profile preserves external model artifact mount policy.
- Experiment queue prepared GPU candidate smoke metadata using the external
  artifact root only; no heavy training dependency was added.

## Next Handoff

- Before GPU research begins, verify the single-card path without adding heavy
  dependencies to the base engine.
