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
2. Keep PyTorch CUDA confined to the Docker `research` target.
3. Support candidate evaluation and future bounded training through the small
   research job runner without adding a general agent platform.

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
- PyTorch CUDA is installed only in Docker `research`; the tiny training smoke
  completed on the RTX 4090 and wrote to `/app/model_artifacts/gpu-training`.
- Research job runner executed inside Docker `research` and wrote wrapper job
  artifacts to `/app/model_artifacts/research-jobs`.
- Bounded `candidate_training` job executed inside Docker `research` with
  PyTorch CUDA and wrote metrics/model artifacts to
  `/app/model_artifacts/candidate-training/bounded-candidate-training-smoke`.

## Next Handoff

- Keep `engine` and `web` on the light base image while GPU training uses the
  Docker `research` target and external artifact mount. Candidate model
  evaluation should avoid adding PyTorch to base/runtime images unless a future
  decision explicitly approves an inference dependency.
