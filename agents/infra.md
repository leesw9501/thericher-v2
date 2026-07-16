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
- Bounded depth-vs-breadth comparison ran in Docker `research`, consumed
  existing `/app/model_artifacts` artifacts only, and wrote comparison plus
  research job artifacts under `/app/model_artifacts`.
- Bounded fill-aware threshold rerun ran in Docker `research`, reused existing
  `/app/model_artifacts` probability traces and `/app/market_data` holdout
  slices, and wrote rerun, holdout, robustness, and research job artifacts
  under `/app/model_artifacts`.
- Bounded zero-fill threshold attribution ran in Docker `research`, consumed
  existing `/app/model_artifacts` rerun, robustness, calibration, and trace
  artifacts only, and wrote attribution plus research job artifacts under
  `/app/model_artifacts`.
- Bounded attribution-informed threshold band rerun ran in Docker `research`,
  reused existing `/app/model_artifacts` traces and `/app/market_data` holdout
  slices, and wrote band rerun, holdout, robustness, and research job artifacts
  under `/app/model_artifacts`.
- Bounded feature/model branch ran in Docker `research` with PyTorch CUDA,
  consumed the external threshold band rerun artifact, read `/app/market_data`
  read-only, and wrote feature branch, training, evaluation, model, and
  research job artifacts under `/app/model_artifacts`.
- Bounded feature-branch replay attribution ran in Docker `research` with
  PyTorch CUDA, consumed external feature branch artifacts, read
  `/app/market_data` read-only, and wrote replay, robustness, probability trace,
  event, and research job artifacts under `/app/model_artifacts`.
- Longer bounded feature/model validation ran in Docker `research` with
  PyTorch CUDA on the RTX 4090, reused existing job kinds, read
  `/app/market_data` read-only, and wrote feature-branch, training,
  evaluation, replay, robustness, and research job artifacts under
  `/app/model_artifacts`.
- Data-quality-visible bounded validation ran in Docker `research` with
  PyTorch CUDA on the RTX 4090, mounted the current `src` read-only for the new
  artifact metadata, read `/app/market_data` read-only, and wrote training,
  evaluation, replay, model, event, SQLite, and research job artifacts under
  `/app/model_artifacts`.
- Calibration runtime probing ran in Docker `research` with PyTorch CUDA,
  confirmed the uncapped 80-bar, 3-slice path can exceed the operator window,
  then completed the same shape with `--threshold-pair-cap 2` and wrote
  calibration, robustness, model, and research job artifacts under
  `/app/model_artifacts`.
- Cap-limited calibration holdout ran in Docker `research` with PyTorch CUDA,
  read `/app/market_data` read-only, and wrote holdout, robustness,
  probability trace, event, SQLite, and research job artifacts under
  `/app/model_artifacts`.
- Bar-pressure feature branch and cap-2 replay ran in Docker `research` with
  PyTorch CUDA on the RTX 4090, mounted the current `src` read-only, read
  `/app/market_data` read-only, and wrote feature branch, training,
  evaluation, model, replay, robustness, event, SQLite, and research job
  artifacts under `/app/model_artifacts`.
- Hidden-units model-axis branch ran in Docker `research` with PyTorch CUDA on
  the RTX 4090, mounted the current `src` read-only, read `/app/market_data`
  read-only, and wrote training, evaluation, model, replay, robustness, and
  research job artifacts under `/app/model_artifacts`.
- Hidden-units contrast branch reused Docker `research` with PyTorch CUDA on
  the RTX 4090, read `/app/market_data` read-only, and wrote training,
  evaluation, model, replay, robustness, and research job artifacts under
  `/app/model_artifacts`.
- Feature-branch derivation-guard replay ran in Docker `research` after the
  Windows restart, mounted the current `src` read-only, read `/app/market_data`
  read-only, and wrote replay, robustness, and research job artifacts under
  `/app/model_artifacts`.
- Feature-branch replay opportunity attribution ran locally as an artifact-only
  smoke, consumed existing `/app/model_artifacts`-style paths resolved to
  `D:\thericher-v2\model-artifacts`, and wrote one attribution artifact under
  the external model artifact root.
- Regularization model-axis feature branch and cap-2 replay ran in Docker
  `research` with PyTorch CUDA on the RTX 4090, mounted the current `src`
  read-only, read `/app/market_data` read-only, and wrote feature-branch,
  training, evaluation, model, replay, robustness, and research job artifacts
  under `/app/model_artifacts`. The follow-up opportunity attribution ran
  locally as artifact-only work and wrote under the external model artifact
  root.
- Feature-normalization feature branch and cap-2 replay ran in Docker
  `research` with PyTorch CUDA on the RTX 4090, mounted the current `src`
  read-only, read `/app/market_data` read-only, and wrote feature-branch,
  training, evaluation, model, replay, robustness, and research job artifacts
  under `/app/model_artifacts`. The follow-up opportunity attribution ran
  locally as artifact-only work and wrote under the external model artifact
  root.
- Source-vs-holdout probability alignment ran locally as artifact-only work,
  consumed existing standardized `/app/model_artifacts` lineage resolved to
  `D:\thericher-v2\model-artifacts`, and wrote one updated attribution artifact
  under the external model artifact root.
- Disjoint-evaluation feature-branch smoke and cap-2 replay ran in Docker
  `research` with PyTorch CUDA on the RTX 4090, mounted current `src`
  read-only, read `/app/market_data` read-only, and wrote feature-branch,
  training, evaluation, model, replay, robustness, event, and research-job
  artifacts under `/app/model_artifacts`. The follow-up opportunity
  attribution ran locally as artifact-only work under the external model
  artifact root.
- Out-of-symbol disjoint-evaluation replay ran in Docker `research` after the
  reboot, mounted current `src` read-only, read `/app/market_data` read-only,
  confirmed RTX 4090 visibility, and wrote replay, robustness, event, and
  research-job artifacts under `/app/model_artifacts`. The follow-up
  opportunity attribution and compact summary ran locally as artifact-only
  work under `D:\thericher-v2\model-artifacts`.
- Out-of-symbol loss attribution ran locally as artifact-only work, consumed
  existing external replay/robustness/opportunity artifacts, reran no Docker
  job, and wrote one compact artifact under
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution`.
- Out-of-symbol fill-lifecycle attribution ran locally as artifact-only work,
  read selected `D:\market_data` Yahoo rows plus existing external event files,
  reran no Docker job, and wrote one compact artifact under
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution`.
- Out-of-symbol post-entry exit-signal attribution ran locally as artifact-only
  work, consumed existing external traces and lifecycle evidence, reran no
  Docker job, and wrote one compact artifact under
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution`.
- Out-of-symbol exit-horizon diagnostic overlay ran locally as artifact-only
  work, read selected `D:\market_data` rows, reran no Docker job, and wrote one
  compact artifact under
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution`.
- Longer-window out-of-symbol replay ran in Docker `research` with PyTorch CUDA
  environment and RTX 4090 visible, mounted current `src` read-only, read
  `/app/market_data` read-only, and wrote replay, robustness, event, and
  research-job artifacts under `/app/model_artifacts`. Follow-up attribution
  ran locally as artifact-only work.
- Longer-window trade-path attribution ran locally as artifact-only work,
  consumed existing external replay/robustness/event/trace artifacts plus
  selected `D:\market_data` rows, and wrote one compact artifact under
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution`.
- Trade-path attribution helper added no runtime dependencies, no PyTorch to
  local/base paths, no Docker service changes, and no artifact writer; focused
  tests and a local real-artifact smoke ran through `uv`.
- Out-of-symbol evaluation feature-branch training/evaluation and cap-2 replay
  ran in Docker `research` with PyTorch CUDA and RTX 4090 visible, mounted
  current `src` read-only, read `/app/market_data` read-only, and wrote
  feature-branch, training, evaluation, model, replay, robustness, event, and
  research-job artifacts under `/app/model_artifacts`. Opportunity attribution
  and trade-path attribution ran locally as artifact-only work under
  `D:\thericher-v2\model-artifacts`.
- Entry-quality diagnostic added a pure local helper and focused tests, with no
  new runtime dependency, Docker service, research job kind, CLI, or artifact
  writer. The one-off diagnostic artifact was written locally under
  `D:\thericher-v2\model-artifacts`.
- Entry-adverse feature-branch training/evaluation and cap-2 replay ran in
  Docker `research` with PyTorch CUDA and RTX 4090 visible, mounted current
  `src` read-only, read `/app/market_data` read-only, and wrote
  feature-branch, training, evaluation, model, replay, robustness, event, and
  research-job artifacts under `/app/model_artifacts`. Follow-up attribution
  ran locally as artifact-only work under `D:\thericher-v2\model-artifacts`.
- Feature-branch comparison ran locally as artifact-only work, consumed
  existing external artifacts, reran no Docker research job, used no GPU, and
  wrote one compact artifact under `D:\thericher-v2\model-artifacts`.
- Entry-adverse segment contrast ran locally as artifact-only work, consumed
  existing external artifacts plus selected local Yahoo rows, reran no Docker
  research job, used no GPU, and wrote one compact artifact under
  `D:\thericher-v2\model-artifacts`.
- Wider entry-adverse replay ran in Docker `research` with PyTorch CUDA and RTX
  4090 visible, reused the current `src` mount and read `/app/market_data`
  read-only, then wrote replay, robustness, opportunity, trade-path, research
  job, and summary artifacts under `/app/model_artifacts`.
- Wider entry-adverse signal-quality diagnostic ran locally as artifact-only
  work, consumed existing external artifacts plus selected local Yahoo rows,
  reran no Docker job, used no GPU, and wrote one compact artifact under
  `D:\thericher-v2\model-artifacts`.
- Entry-adverse hidden-units contrast ran in Docker `research` with PyTorch
  CUDA and RTX 4090 visible, reused the current `src` mount, read
  `/app/market_data` read-only, and wrote feature-branch, training,
  evaluation, replay, robustness, opportunity, trade-path, research-job, and
  contrast artifacts under `/app/model_artifacts`.
- Hidden8 loss attribution ran locally as artifact-only work, consumed
  existing external artifacts plus selected local Yahoo rows, reran no Docker
  job, used no GPU, and wrote one compact artifact under
  `D:\thericher-v2\model-artifacts`.
- Entry-adverse weight-decay feature-branch training/evaluation and cap-2
  replay ran in Docker `research` with PyTorch CUDA and RTX 4090 visible,
  mounted current `src` read-only, read `/app/market_data` read-only, and wrote
  feature-branch, training, evaluation, model, replay, robustness, and
  research-job artifacts under `/app/model_artifacts`. Opportunity, trade-path,
  and contrast attribution ran locally as artifact-only work under
  `D:\thericher-v2\model-artifacts`.
- Weight-decay wider-sample batch2 replay ran in Docker `research` with
  PyTorch CUDA and RTX 4090 visible, reused the existing feature-branch
  artifact, read `/app/market_data` read-only, and wrote replay, robustness,
  research-job, opportunity, and summary artifacts under the external model
  artifact root.
- Lighter weight-decay feature-branch training/evaluation and first-six replay
  ran in Docker `research` with PyTorch CUDA and RTX 4090 visible, reused the
  current `src` mount, read `/app/market_data` read-only, and wrote
  feature-branch, training, evaluation, model, replay, robustness, opportunity,
  trade-path, and summary artifacts under the external model artifact root.
- Lighter weight-decay batch2 replay also ran in Docker `research`, reused the
  existing `weight_decay=0.001` feature-branch artifact, produced zero
  additional fills, and wrote external replay/opportunity evidence without
  changing Docker services or adding PyTorch to local/base paths.
- Regularization trace-collapse diagnostic ran locally as artifact-only work,
  consumed existing external JSON artifacts, reran no Docker job, used no GPU,
  and wrote one compact diagnostic under
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution`.
- Feature-input concentration diagnostic ran locally as artifact-only work,
  imported existing light research/data helpers only, reran no Docker job, used
  no GPU, and wrote one compact diagnostic under the external model artifact
  root.
- Source-breadth feature-branch training/evaluation and cap-2 replay ran in
  Docker `research` with PyTorch CUDA and RTX 4090 visible, reused current
  `src` read-only, read `/app/market_data` read-only, and wrote feature-branch,
  training, evaluation, model, replay, robustness, event, research-job,
  opportunity, trade-path, and summary artifacts under the external model
  artifact root. Follow-up attribution ran locally as artifact-only work.
- Source-breadth AMGN loss attribution ran locally as artifact-only work,
  consumed existing external JSON artifacts plus selected AMGN local Yahoo rows,
  reran no Docker job, used no GPU, and wrote one compact artifact under
  `D:\thericher-v2\model-artifacts`.
- Signal-hygiene diagnostic ran locally as artifact-only work, consumed
  existing external JSON artifacts only, reran no Docker job, used no GPU, and
  wrote one compact artifact under `D:\thericher-v2\model-artifacts`.
- Sell-latency attribution ran locally as artifact-only work, consumed existing
  external JSON artifacts only, reran no Docker job, used no GPU, and wrote one
  compact artifact under `D:\thericher-v2\model-artifacts`.
- Exit-timing diagnostic overlay ran locally as artifact-only work, consumed
  existing external JSON artifacts plus selected local Yahoo rows, reran no
  Docker job, used no GPU, and wrote one compact artifact under
  `D:\thericher-v2\model-artifacts`.
- Exit-policy sketch ran locally as artifact-only work, consumed existing
  external JSON artifacts only, reran no Docker job, used no GPU, and wrote one
  compact artifact under `D:\thericher-v2\model-artifacts`.
- Diagnostic exit-overlay helper added no Docker dependency, service, GPU
  requirement, artifact writer, or PyTorch dependency in local/base paths.
- Diagnostic exit-overlay helper smoke ran locally as artifact-only work, used
  no GPU or Docker research job, and wrote one compact artifact under
  `D:\thericher-v2\model-artifacts`.
- Conditional exit-overlay contrast ran locally as artifact-only work, used no
  GPU or Docker research job, and wrote one compact artifact under
  `D:\thericher-v2\model-artifacts`.
- Exit-latency composite diagnostic ran locally as artifact-only work, used no
  GPU or Docker research job, and wrote one compact artifact under
  `D:\thericher-v2\model-artifacts`.
- Diagnostic exit-composite helper added no Docker dependency, service, GPU
  requirement, artifact writer, or PyTorch dependency in local/base paths.
- Diagnostic exit-composite helper smoke ran locally as artifact-only work,
  used no GPU or Docker research job, and wrote one compact artifact under
  `D:\thericher-v2\model-artifacts`.
- Research-only exit-latency sandbox helper added no Docker dependency,
  service, GPU requirement, artifact writer, or PyTorch dependency in
  local/base paths.
- Exit-latency sandbox helper smoke ran locally as artifact-only work, used no
  GPU or Docker research job, and wrote one compact artifact under
  `D:\thericher-v2\model-artifacts`.
- Fixed entry-adverse validation ran in Docker `research` with PyTorch CUDA and
  RTX 4090 visible, read `/app/market_data` read-only, and wrote feature
  branch, training, evaluation, model, replay, robustness, event, research job,
  and trade-path artifacts under `/app/model_artifacts`.
- Longer-depth entry-adverse contrast ran in Docker `research` with PyTorch
  CUDA and RTX 4090 visible, mounted current `src` read-only, read
  `/app/market_data` read-only, wrote feature-branch, training, evaluation,
  model, replay, robustness, event, and research-job artifacts under
  `/app/model_artifacts`, then wrote local artifact-only trade-path and
  depth-vs-short comparison artifacts under
  `D:\thericher-v2\model-artifacts`.
- Short-vs-depth APH signal/path attribution ran locally as artifact-only work,
  used no GPU or Docker job, consumed existing external JSON/event artifacts
  plus selected APH bars, and wrote one compact artifact under
  `D:\thericher-v2\model-artifacts`.
- Second-holdout replay contrast ran two existing Docker `research`
  feature-branch replay jobs after confirming PyTorch CUDA `2.7.0+cu128` and
  RTX 4090 visibility. It mounted current `src` read-only, read
  `/app/market_data` read-only, wrote replay/robustness/research-job artifacts
  under `/app/model_artifacts`, then wrote one compact attribution artifact
  under `D:\thericher-v2\model-artifacts`.
- First-evaluation source-context contrast attempted the planned 12-source
  command, observed the existing `data_slices <= 6` cap, did not rebuild or
  change code, then ran the cap-compliant six-source Docker `research`
  feature-branch and replay jobs with RTX 4090 visible. Artifacts were written
  under `/app/model_artifacts` plus one compact attribution under
  `D:\thericher-v2\model-artifacts`.
- AMD segment-quality diagnostic ran locally as artifact-only work, used no GPU
  or Docker job, consumed existing external JSON/event artifacts plus selected
  AMD Yahoo rows, and wrote one compact artifact under
  `D:\thericher-v2\model-artifacts`.
- AMD entry feature-input diagnostic ran locally as artifact-only work, used no
  GPU or Docker job, imported the existing light feature builder for formula
  parity, and wrote one compact artifact under
  `D:\thericher-v2\model-artifacts`.
- AMD entry-filter diagnostic overlay ran locally as artifact-only work, used
  no GPU or Docker job, reused existing `D:\market_data` rows, and wrote one
  compact artifact under `D:\thericher-v2\model-artifacts`.
- Cross-sample entry-filter overlay ran locally as artifact-only work, used no
  GPU or Docker job, reused existing `D:\market_data` rows, and wrote one
  compact artifact under `D:\thericher-v2\model-artifacts`.
- First-evaluation source-context depth feature-branch and replay jobs ran in
  Docker `research` with PyTorch CUDA and RTX 4090 visible after Docker was
  restarted. They read `/app/market_data` read-only, wrote feature-branch,
  training, evaluation, model, replay, robustness, event, and research-job
  artifacts under `/app/model_artifacts`, then local artifact-only opportunity,
  trade-path, and depth-vs-short comparison artifacts were written under
  `D:\thericher-v2\model-artifacts`.
- First-evaluation wider-holdout contrast ran four existing Docker `research`
  replay jobs with PyTorch CUDA and RTX 4090 visible, mounted current `src`
  read-only, read `/app/market_data` read-only, and wrote replay, robustness,
  event, probability-trace, and research-job artifacts under
  `/app/model_artifacts`. Follow-up opportunity, trade-path, and comparison
  artifacts ran locally as artifact-only work under
  `D:\thericher-v2\model-artifacts`.
- Wider-holdout depth behavior attribution ran locally as artifact-only work,
  used no GPU or Docker job, consumed existing external JSON artifacts plus
  selected `D:\market_data` rows, and wrote one compact diagnostic under the
  external model artifact root.
- Engine Research Agent runner added one local CLI entrypoint while keeping
  GPU execution in Docker `research`. The first smoke attempt was claimed and
  recorded as failed because the sanitized subprocess environment hid Docker
  Compose plugin discovery; the allowlist now preserves required Windows
  profile/appdata paths while filtering secret-like env keys. The second smoke
  `engine-research-agent-gpu-training-smoke-20260717-r2` completed with
  PyTorch CUDA on the RTX 4090 and wrote artifacts under `/app/model_artifacts`
  mounted to `D:\thericher-v2\model-artifacts`.
- Engine Research Agent enqueue added one explicit subcommand for existing
  research job kinds and keeps `run-once` as the only executor. A first queued
  `candidate_feature_branch_replay` attempt exposed stale Docker image source;
  the runner now mounts current `src` read-only into Docker `research`, and the
  retry completed with RTX 4090 visible while writing all artifacts under
  `/app/model_artifacts`.
- Runner-queued zero-fill attribution ran locally as artifact-only work, used
  no GPU or Docker job, consumed existing external JSON artifacts, and wrote one
  compact artifact under `D:\thericher-v2\model-artifacts`.
- Data Agent runner added one local CLI entrypoint and no Docker/GPU/PyTorch
  requirement. Its first smoke claimed one external queue item, read existing
  `D:\market_data` metadata only, and wrote queue/run-state/inventory artifacts
  under `D:\thericher-v2\model-artifacts\data-agent`.
- Two-worker cadence used disjoint external roots: Data Agent ran locally with
  no Docker/GPU requirement, while Engine Research Agent ran Docker `research`
  with current `src` mounted read-only and RTX 4090 visible. Both queues were
  empty after their single `run-once` invocations.
- Runner-queued longer depth attempt used the same disjoint external roots:
  Data Agent ran locally with no Docker/GPU requirement, while Engine Research
  Agent ran Docker `research` with current `src` mounted read-only and RTX 4090
  visible. The Engine command completed with return code `0`, but the research
  payload stayed `prepared_not_depth_targeted` because source/holdout slices
  were not queued.
- Explicit-slice runner depth target used the same single-shot runner and
  Docker `research` path with current `src` mounted read-only and RTX 4090
  visible. It completed with return code `0` after about `16` minutes, wrote
  all training/model/calibration/holdout/robustness artifacts under
  `/app/model_artifacts`, and cleared the external GPU lock afterward.
- Explicit-slice depth attribution ran locally as artifact-only work, used no
  Docker or GPU job, and wrote one compact artifact under
  `D:\thericher-v2\model-artifacts\candidate-depth-target-attribution`.
- AMAT/AEM trade-path diagnostic ran locally as artifact-only work, used no
  Docker or GPU job, and wrote one compact artifact under
  `D:\thericher-v2\model-artifacts\candidate-depth-target-trade-path-diagnostic`.
- AMAT/AEM replay-shape overlay ran locally as artifact-only work, used no
  Docker or GPU job, and wrote one compact artifact under
  `D:\thericher-v2\model-artifacts\candidate-depth-target-replay-shape-overlay`.
- Held-out/context overlay ran locally as artifact-only work, used no Docker or
  GPU job, and wrote one compact artifact under
  `D:\thericher-v2\model-artifacts\candidate-depth-target-replay-shape-overlay`.
- ADI/AGG driver attribution ran locally as artifact-only work, used no Docker
  or GPU job, and wrote one compact artifact under
  `D:\thericher-v2\model-artifacts\candidate-depth-target-replay-shape-driver-attribution`.
- ADI/AGG feature-input diagnostic ran locally as artifact-only work, used no
  Docker or GPU job, and wrote one compact artifact under
  `D:\thericher-v2\model-artifacts\candidate-depth-target-feature-input-diagnostic`.
- Cross-slice feature-input stability check ran locally as artifact-only work,
  used no Docker or GPU job, and wrote one compact artifact under
  `D:\thericher-v2\model-artifacts\candidate-depth-target-feature-input-stability`.
- Bounded feature-input ablation ran once locally as a no-backend dry-run and
  once in Docker `research` with PyTorch CUDA on RTX 4090. It changed no Docker
  or dependency files and wrote metrics/model artifacts under
  `D:\thericher-v2\model-artifacts\feature-input-ablation`.
- Full-row feature-input ablation ran locally as a no-backend dry-run and in
  Docker `research` with PyTorch CUDA on RTX 4090 using the current `src`
  read-only mount. It changed no Docker or dependency files and wrote
  metrics/model artifacts under
  `D:\thericher-v2\model-artifacts\feature-input-ablation\bounded-feature-input-ablation-fullrow-cross-slice-20260717-r2`.
- Slice-aware feature-input evaluation ran one Docker `research` PyTorch CUDA
  job with current `src` mounted read-only and wrote metrics/model artifacts
  under
  `D:\thericher-v2\model-artifacts\feature-input-ablation\bounded-feature-input-ablation-slice-aware-cross-slice-20260717-r1`.
- Unique-signal feature-input evaluation ran one Docker `research` PyTorch CUDA
  job with current `src` mounted read-only and wrote metrics/model artifacts
  under
  `D:\thericher-v2\model-artifacts\feature-input-ablation\bounded-feature-input-ablation-unique-signal-cross-slice-20260717-r1`.
- Unique-signal probability-band diagnostic ran one Docker `research` PyTorch
  CUDA job with current `src` mounted read-only and wrote metrics/model
  artifacts under
  `D:\thericher-v2\model-artifacts\feature-input-ablation\bounded-feature-input-ablation-probability-bands-cross-slice-20260717-r1`.
- Raw pre-entry band attribution ran one Docker `research` PyTorch CUDA job
  with current `src` mounted read-only and wrote metrics/model artifacts under
  `D:\thericher-v2\model-artifacts\feature-input-ablation\bounded-feature-input-ablation-raw-band-attribution-cross-slice-20260717-r1`.
  It changed no Docker, compose, or dependency files and kept PyTorch confined
  to the `research` target.
- Raw pre-entry local-paper outcome attribution ran CPU/artifact-only, used no
  Docker or GPU job, changed no dependency files, and wrote one compact
  artifact under
  `D:\thericher-v2\model-artifacts\raw-pre-entry-outcome-attribution\bounded-raw-pre-entry-outcome-attribution-cross-slice-20260717-r1`.
- Raw pre-entry contract tightening ran CPU/focused tests and one CPU artifact
  smoke only. It used no Docker or GPU job, changed no dependency, compose, or
  Docker files, kept artifacts outside Git, and narrowed attribution imports so
  raw outcome/trade-path helpers do not import the execution barrel or load
  broker modules.
- First bounded parallel-agent cadence used disjoint external roots. Data Agent
  ran locally with no Docker/GPU requirement. Engine Research Agent ran one
  Docker `research` job with current `src` mounted read-only, RTX 4090 visible,
  and artifacts written under `/app/model_artifacts` mounted to
  `D:\thericher-v2\model-artifacts`. The external queues were empty afterward
  and no `gpu.lock` remained.

## Next Handoff

- Keep `engine` and `web` on the light base image while GPU training uses the
  Docker `research` target and external artifact mount. A future infra slice
  should restructure Docker layers so source edits do not reinstall PyTorch.
- Prefer cap-limited calibration commands until the local-paper variant replay
  loop is made faster or more incremental.
- The runner now has explicit one-job enqueue/run semantics, queue/run artifacts
  outside Git, current `src` read-only Docker mount, and Docker `research` GPU
  execution. Keep future runner changes away from daemon, scheduler, dashboard,
  notification, or auto-commit behavior.
- Data Agent now reuses the same external queue/run-state discipline with a
  separate `data-agent` artifact root and no GPU/Docker requirement. Keep it
  separate from Engine Research Agent's Docker/PyTorch lane while the next
  simplification pass uses existing artifacts.
- Temporary Codex sub-agents are runtime helpers, not Docker services or repo
  workers. Do not add a scheduler/coordinator layer for them in the next slice.
- The next research cadence should run Docker `research` only through the
  existing Engine Research Agent single-shot runner, with `src` mounted
  read-only and model artifacts under `/app/model_artifacts`.
- Do not add scheduler/coordinator plumbing for the next opportunity-gap
  diagnostic. Use existing artifacts or one existing single-shot runner job.
