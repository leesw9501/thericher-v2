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
- Docker research profile mounts market data read-only at `/app/market_data`.
- Host artifact root is `D:\thericher-v2\model-artifacts` by default.

## Active Queue

1. Keep base engine tests free of heavy research dependencies.
2. Keep PyTorch CUDA confined to the Docker `research` target.
3. Improve Docker research build caching; source edits currently trigger a
   costly PyTorch reinstall layer.

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
- Bounded `candidate_evaluation` job executed inside Docker `research` with
  PyTorch CUDA and wrote metrics to
  `/app/model_artifacts/candidate-evaluation/bounded-candidate-evaluation-smoke`.
- Bounded `candidate_replay` job executed inside Docker `research` with
  PyTorch CUDA, read `/app/market_data` read-only, and wrote replay metrics to
  `/app/model_artifacts/candidate-replay/bounded-candidate-replay-smoke`.
- Bounded `candidate_replay_comparison` job consumed the existing replay
  artifact and wrote comparison metrics to
  `D:\thericher-v2\model-artifacts\candidate-replay-comparison\bounded-candidate-replay-comparison-smoke`.
- Bounded `candidate_threshold_sweep` job ran in Docker `research` with PyTorch
  CUDA, wrote one probability trace, and replayed threshold variants under
  `D:\thericher-v2\model-artifacts\candidate-threshold-sweep\bounded-candidate-threshold-sweep-smoke`.
- Bounded `candidate_threshold_robustness` job ran in Docker `research` with
  PyTorch CUDA, wrote per-slice probability traces for CVS, FCX, and KO, and
  wrote the aggregate robustness artifact under
  `D:\thericher-v2\model-artifacts\candidate-threshold-robustness\bounded-candidate-threshold-robustness-smoke`.
- Bounded multi-slice candidate training and evaluation ran in Docker
  `research` with PyTorch CUDA, wrote artifacts under
  `D:\thericher-v2\model-artifacts\candidate-training\bounded-candidate-multislice-training-smoke`
  and
  `D:\thericher-v2\model-artifacts\candidate-evaluation\bounded-candidate-multislice-evaluation-smoke`,
  then replayed robustness under
  `D:\thericher-v2\model-artifacts\candidate-threshold-robustness\bounded-candidate-multislice-robustness-smoke`.
- Bounded multi-slice probability calibration ran in Docker `research` with
  PyTorch CUDA, read `/app/market_data` read-only, and wrote calibration plus
  robustness artifacts under `/app/model_artifacts`.
- Bounded calibration holdout replay ran in Docker `research` with PyTorch
  CUDA, read `/app/market_data` read-only, and wrote holdout plus robustness
  artifacts under `/app/model_artifacts`.
- Bounded candidate breadth queue ran in Docker `research` with PyTorch CUDA,
  read `/app/market_data` read-only, and wrote queue, training, evaluation, and
  model artifacts under `/app/model_artifacts`.
- Bounded breadth holdout bridge ran in Docker `research` with PyTorch CUDA,
  consumed `/app/model_artifacts/candidate-breadth-queue/.../metrics.json`,
  read `/app/market_data` read-only, and wrote breadth holdout, calibration,
  holdout, robustness, and research job artifacts under `/app/model_artifacts`.
- Bounded depth target ran in Docker `research` with PyTorch CUDA, consumed
  `/app/model_artifacts/candidate-breadth-holdout/.../metrics.json`, read
  `/app/market_data` read-only, and wrote depth target, candidate, training,
  evaluation, calibration, holdout, robustness, model, and research job
  artifacts under `/app/model_artifacts`.

## Next Handoff

- Keep `engine` and `web` on the light base image while GPU training uses the
  Docker `research` target and external artifact mount. A future infra slice
  should restructure Docker layers so source edits do not reinstall PyTorch.
