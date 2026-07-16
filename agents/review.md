# Review Agent

## Engine Loop

- backtest and walk-forward validation
- paper trading
- live-risk control

## Owns

- Simplicity review and v1-sprawl detection.
- Checks for unnecessary docs, gates, reports, scripts, and workflows.
- Boundary review for credentials, broker calls, live mode, and dashboard
  exposure.

## Must Not

- Own implementation.
- Add review artifacts unless they directly reduce engine risk.
- Block research iteration for warnings that are not execution hard stops.

## Held Resources

- None.

## Active Queue

1. Review the next feature/model branch for bounded scope and artifact sprawl.
2. Keep agent stateboards short and retire stale ones.

## Running Jobs

- None.

## Done Recently

- Drift checks kept market-data and handoff changes small.
- Validation target stayed broker-free, credential-free, and artifact-light.
- Experiment queue stayed a single runner and concise metrics artifact, with no
  promotion gate or dashboard expansion.
- Walk-forward stayed capped and artifact-only, with no promotion gate.
- GPU candidate smoke stayed metadata-only and did not add a promotion gate.
- GPU runtime smoke stayed `nvidia-smi`-only and outside Git.
- GPU compute smoke stayed research-profile-only, did not add heavy base
  dependencies, and produced one concise external artifact.
- GPU training smoke scaffold added one CLI and one focused test file without
  adding a framework dependency or a promotion gate.
- PyTorch CUDA was confined to the Docker `research` stage, with tests checking
  that base/runtime stages and `pyproject.toml` remain torch-free.
- Research job runner stayed single-kind and artifact-only; it did not create a
  broad agent platform or new stateboard files.
- Candidate training extended the job runner with one explicit second kind,
  stayed bounded by caps, wrote artifacts outside Git, and did not add a
  promotion gate, dashboard, broker call, or new report family.
- Candidate evaluation extended the job runner with one explicit third kind,
  stayed artifact-only, kept PyTorch lazy/research-only, and deferred
  local-paper conversion instead of creating a promotion gate.
- Candidate replay extended the job runner with one explicit fourth kind,
  stayed broker-free/local-paper-only, kept fills labeled `source:
  local_paper`, and did not add a promotion gate or dashboard surface.
- Candidate replay comparison extended the job runner with one explicit fifth
  kind, stayed artifact-only and local-paper-only, consumed existing replay
  evidence when available, and did not add a promotion gate, dashboard, or
  scheduler.
- Candidate threshold sweep extended the job runner with one explicit sixth
  kind, reused the candidate replay execution path, kept PyTorch lazy/research
  only, and did not add a promotion gate, dashboard, or scheduler.
- Candidate threshold robustness extended the job runner with one explicit
  seventh kind, reused the threshold sweep variant primitive, capped slices,
  kept output descriptive, and did not add a promotion gate, dashboard,
  scheduler, or autonomous agent process.
- Multi-slice candidate training reused the existing candidate dataset feature
  builder, shared the slice parser instead of cloning it, kept PyTorch in
  Docker `research`, and did not add a new replay path or promotion gate.
- Probability calibration added one deterministic threshold-grid helper and one
  job kind, reused the existing robustness/local-paper path, and did not emit a
  best threshold, promotion gate, dashboard, scheduler, or autonomous agent
  process.
- Calibration holdout added one thin job kind, consumed calibration thresholds
  unchanged, reused the existing robustness/local-paper path, and did not emit
  a best threshold, promotion gate, dashboard, scheduler, or autonomous agent
  process.
- Candidate breadth queue added one thin job kind, reused existing
  training/evaluation primitives, capped variants at three, and did not emit a
  best candidate, promotion gate, dashboard, scheduler, or autonomous agent
  process.
- Breadth holdout bridge added one thin Docker dispatch kind because the bridge
  needs to run inside `research`; it reused existing calibration/holdout
  primitives, capped variants at three, and did not emit a best candidate,
  promotion gate, dashboard, scheduler, or autonomous agent process.
- Depth target added one thin Docker dispatch kind because training/evaluation
  need to run inside `research`; it reused existing
  training/evaluation/calibration/holdout primitives, selected at most one
  candidate for research scheduling only, and did not emit a best candidate,
  promotion gate, dashboard, scheduler, or autonomous agent process.
- Zero-fill local-paper verification was narrowed rather than expanded into a
  gate: missing event files are tolerated only when replay fill count is zero.
- Depth-vs-breadth comparison added one thin artifact-diff job, reran no
  training or holdout work, and did not emit a best candidate, promotion gate,
  dashboard, scheduler, or autonomous agent process.
- Fill-aware threshold rerun added one thin wrapper around the existing
  holdout/robustness/local-paper path, avoided retraining and optimization, and
  did not emit a best threshold, promotion gate, dashboard, scheduler, or
  autonomous agent process.
- Zero-fill threshold attribution added one thin artifact-only job kind,
  reran no training, inference, or local-paper execution, and did not emit a
  best threshold, promotion gate, dashboard, scheduler, or autonomous agent
  process.
- Attribution-informed threshold band rerun added one thin wrapper around the
  existing holdout/robustness/local-paper path, closed the immediate
  threshold-only loop, and did not emit a best threshold, promotion gate,
  dashboard, scheduler, or autonomous agent process.
- Feature-branch replay attribution added one thin wrapper around the existing
  robustness/local-paper path, consumed the new feature branch rather than
  permuting the old candidate again, and did not emit a best threshold,
  promotion gate, dashboard, scheduler, or autonomous agent process.
- Source-filtered local-paper attribution stayed a shared execution helper and
  existing verification call-site update; it did not add a new report family,
  gate, dashboard, scheduler, or broker adapter implementation.
- Broker boundary fuses stayed one small execution module plus focused tests;
  they did not add KIS clients, env/config enablement, event-log writes,
  dashboard controls, schedulers, or a broker framework.
- Longer bounded GPU feature/model validation reused existing Docker
  `research` job kinds and external artifacts; it added no new `candidate_*`
  module, report family, scheduler, dashboard, or promotion gate.
- Market-data quality checks stayed a pure helper plus focused tests and
  validation CLI summary; they did not add a gate, report family, data
  acquisition path, dashboard, broker behavior, or scheduler.
- Candidate artifact quality summaries reused the existing checker and
  source-slice metadata; they did not add a new job family, report, gate,
  dashboard, scheduler, broker path, or model-promotion language.
- Data-quality-visible validation reused existing Docker `research`
  training/evaluation/replay job kinds and added no code, job family, report,
  gate, dashboard, scheduler, broker path, or model-promotion language. The
  stopped calibration attempt should be handled as a bounded-runtime issue, not
  by adding process sprawl.
- Calibration runtime control exposed an existing threshold-pair cap through
  the research job runner and runbook instead of adding a scheduler, new job
  family, gate, dashboard, broker path, or model-promotion language.
- Cap-limited calibration holdout reused the existing holdout/robustness
  local-paper path and added no code, new job family, report, gate, dashboard,
  scheduler, broker path, or model-promotion language.
- Bar-pressure feature branch reused the existing candidate feature builder,
  feature-branch job, and replay job. It added one feature-set ID plus explicit
  job arguments, and added no new job family, report, gate, dashboard,
  scheduler, broker path, or model-promotion language.
- Hidden-units model-axis branch reused an existing `CandidateTrainingConfig`
  knob and existing candidate training/feature-branch jobs. It added one
  selector plus bounded validation and added no new job family, report, gate,
  dashboard, scheduler, broker path, or model-promotion language.
- Hidden-units contrast branch used existing code only and added no new job
  family, report, gate, dashboard, scheduler, broker path, or model-promotion
  language.
- Feature-branch replay derivation guard changed one existing helper plus
  focused tests, emitted clamp metadata only when saturated evidence requires
  it, and added no new job family, report, gate, dashboard, scheduler, broker
  path, or model-promotion language.
- Feature-branch replay opportunity attribution added an artifact-only
  entrypoint that reuses the existing threshold attribution slice helper. It
  added no new research job kind, report, gate, dashboard, scheduler, broker
  path, or model-promotion language.
- Regularization model-axis work added one bounded selector to the existing
  candidate training and feature-branch job paths only. It added no new job
  family, report, gate, dashboard, scheduler, broker path, optimizer search,
  or model-promotion language, and replay/attribution stayed artifact-driven.
- Feature-normalization work added one bounded preprocessing selector to the
  existing candidate training and feature-branch job paths only. It added no
  new job family, report, gate, dashboard, scheduler, broker path,
  preprocessing search, or model-promotion language, and
  evaluation/replay/trace stayed artifact-driven.
- Source-vs-holdout probability alignment extended the existing
  feature-branch replay opportunity attribution artifact. It added no new
  module, job kind, artifact family, report, gate, dashboard, scheduler,
  broker path, alignment score, or model-promotion language.
- Disjoint-evaluation feature-branch work added one bounded slice-plumbing
  path and CLI flag for the existing feature-branch job only. It added no new
  job kind, report, gate, dashboard, scheduler, broker path, disjointness
  blocker, or model-promotion language.
- Out-of-symbol replay used existing feature-branch replay, robustness,
  local-paper verification, and attribution paths only. It added no code, job
  kind, report family, gate, dashboard, scheduler, broker path, threshold
  search, or model-promotion language.
- Out-of-symbol loss attribution used existing external artifacts only and
  added no code, job kind, report family, gate, dashboard, scheduler, broker
  path, threshold search, retraining, rerun replay, or model-promotion
  language.
- Out-of-symbol fill-lifecycle attribution used existing event artifacts and
  selected local Yahoo rows only. It added no code, job kind, report family,
  gate, dashboard, scheduler, broker path, threshold search, retraining, rerun
  replay, or model-promotion language.
- Out-of-symbol post-entry attribution used existing traces and lifecycle
  artifacts only. It added no code, job kind, report family, gate, dashboard,
  scheduler, broker path, threshold search, retraining, rerun replay, or
  model-promotion language.

## Next Handoff

- Challenge any new document or workflow that does not improve a named engine
  loop.
- Push the next task toward a compact diagnostic overlay that is clearly
  separated from local-paper fills before allowing another model axis or
  threshold-only branch.
