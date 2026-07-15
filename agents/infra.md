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
2. Add the selected GPU compute framework only to the Docker `research` target
   after operator approval.
3. Once approved, verify the training smoke through `docker compose --profile
   research run`.

## Running Jobs

- None.

## Done Recently

- Docker Compose has `engine`, `web`, and `research` services.
- Research profile preserves external model artifact mount policy.
- Experiment queue prepared GPU candidate smoke metadata using the external
  artifact root only; no heavy training dependency was added.
- Walk-forward artifacts were written under the external model artifact root.
- Walk-forward candidate smoke used `nvidia-smi` readiness only and deferred GPU
  compute to the research profile.
- GPU runtime smoke records `nvidia-smi` readiness under the external artifact
  root.
- Docker `research` now requests GPU access and can write compute-smoke
  artifacts to `/app/model_artifacts/gpu-compute`; the smoke currently stops at
  `prepared_not_trained` because no compute backend is installed.
- GPU training smoke CLI exists without adding GPU dependencies; it currently
  writes `prepared_not_trained` under the external artifact root until the
  research backend is approved.

## Next Handoff

- Keep `engine` and `web` on the light base image while GPU training uses the
  Docker `research` target and external artifact mount.
