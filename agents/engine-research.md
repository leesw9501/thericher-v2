# Engine Research Agent

## Engine Loop

- feature/model research
- backtest and walk-forward validation
- PnL attribution

## Owns

- Feature research, indicators, model experiments, and strategy logic.
- GPU model training and validation once GPU research begins.
- Backtest and walk-forward evidence used for model selection.
- Model registry inputs and concise experiment summaries.

## Must Not

- Modify broker submit code.
- Read credentials or `.env`.
- Store generated model artifacts in Git.
- Treat weak research quality as an execution hard stop.

## Held Resources

- GPU: available for bounded research planning; smoke detected NVIDIA GeForce
  RTX 4090 with 24564 MiB.
- Model artifacts root: `D:\thericher-v2\model-artifacts`.
- Docker artifact path: `/app/model_artifacts`.

## Active Queue

1. Diagnose why `candidate_threshold_calibration` can run past the bounded
   operator window without emitting an artifact, then rerun a compact
   calibration or robustness replay.
2. Keep short experiments for breadth and longer candidate training for depth
   visible as separate queues.
3. Do not call either path a production recommendation, promotion, or pass/fail
   result.

## Running Jobs

- Last completed: `bounded-dq-visible-candidate-replay-cvs-20260716`, status
  `completed`, candidate `m1_lb3_b10_s10`, replayed CVS at `0.48/0.455`,
  produced `37` `source: local_paper` fills, PnL `-0.08440213623047`, and
  wrote artifacts under
  `D:\thericher-v2\model-artifacts\candidate-replay\bounded-dq-visible-candidate-replay-cvs-20260716`.
- Previous completed: `bounded-dq-visible-candidate-evaluation-depth-20260716`,
  status `completed`, candidate `m1_lb3_b10_s10`, evaluated 708 examples,
  probability range `0.451895`, and confirmed CVS, FCX, and KO source slices
  carry compact non-blocking `data_quality` summaries.
- Interrupted: `bounded-dq-visible-candidate-calibration-depth-20260716` ran
  for more than 10 minutes without writing its calibration artifact and was
  stopped; diagnose this before relying on the calibration path for longer
  loops.
- Previous completed: `bounded-candidate-feature-branch-replay-mini-smoke`,
  status
  `completed`, candidate
  `m1_lb3_b10_s10__core_plus_bar_position_v1`, replayed threshold pairs
  `0.482/0.457`, `0.483/0.457`, and `0.484/0.457` across CVS, FCX, and KO,
  produced `46` local-paper fills across 9 variants, and wrote artifacts under
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay\bounded-candidate-feature-branch-replay-mini-smoke`.

## Done Recently

- Basic momentum model and next-bar backtest harness exist.
- Market data can now resample deterministic `1m`, `5m`, `10m`, `1h`, and `3h`
  bars.
- Added a bounded validation harness that turns `Bar` data into model
  predictions, ensemble decisions, local paper `OrderIntent`s, and replayable
  local paper fills.
- Wrote smoke artifacts outside Git under
  `D:\thericher-v2\model-artifacts\validation`.
- Added a bounded short experiment queue and wrote metrics artifacts outside Git
  under `D:\thericher-v2\model-artifacts\experiments`.
- Prepared a GPU candidate smoke artifact after the CPU queue completed; no GPU
  training is running.
- Added capped walk-forward windows and PnL attribution metrics; wrote sample
  and FCX walk-forward artifacts outside Git.
- Selected `m1_lb3_b10_s10` as the first walk-forward GPU candidate and wrote a
  `prepared_not_trained` metadata artifact outside Git.
- Added a GPU runtime smoke artifact showing RTX 4090 readiness without adding
  heavy GPU dependencies to the base engine.
- Added a Docker research GPU compute smoke. The research container sees the RTX
  4090, but no compute backend is installed yet, so the artifact is
  `prepared_not_trained` rather than a training result.
- Added a GPU training smoke scaffold with an injected trainer test seam. Host
  execution sees the RTX 4090 but records `prepared_not_trained` until a
  research-only backend is approved and installed.
- Installed PyTorch CUDA only in Docker `research` and ran the tiny training
  smoke on the RTX 4090 for candidate `m1_lb3_b10_s10`; artifact status is
  `training_ran_only`.
- Added the first lightweight research job runner. It ran one bounded
  `gpu_training_smoke` job inside Docker `research` and wrote wrapper/training
  artifacts outside Git.
- Added the first bounded `candidate_training` job. It trained a tiny PyTorch
  MLP for selected candidate `m1_lb3_b10_s10` inside Docker `research` and
  wrote metrics/model artifacts outside Git.
- Added the first bounded `candidate_evaluation` job. It loaded the external
  `model.pt` inside Docker `research`, confirmed feature names matched, and
  wrote held-out classification metrics outside Git. Local-paper conversion was
  deferred.
- Added the first bounded `candidate_replay` job. It used the explicit CVS
  Yahoo intraday snapshot, mapped candidate probabilities into local paper
  decisions, produced one `source: local_paper` fill, and wrote PnL/drawdown
  attribution outside Git.
- Added the first bounded `candidate_replay_comparison` job. It consumed the
  existing candidate replay artifact, ran the simple momentum baseline on the
  same CVS bars through local paper, and wrote descriptive PnL/drawdown/fill
  deltas outside Git.
- Added the first bounded `candidate_threshold_sweep` job. It wrote a GPU
  probability trace once, replayed five candidate threshold pairs on the same
  CVS bars through local paper, and wrote descriptive variant deltas outside
  Git.
- Added the first bounded `candidate_threshold_robustness` job. It replayed
  the same five threshold pairs across CVS, FCX, and KO local Yahoo slices,
  wrote one aggregate robustness artifact outside Git, and kept all output
  descriptive.
- Added bounded multi-slice training/evaluation input. The smoke trained one
  PyTorch CUDA candidate from CVS, FCX, and KO local Yahoo slices, evaluated it
  from the recorded source slices, then replayed it through threshold
  robustness. The existing threshold grid produced zero fills, so calibration
  is the next research step.
- Added the first bounded probability-derived calibration probe. The Docker
  `research` smoke used PyTorch CUDA to trace CVS, FCX, and KO, derived four
  quantile-based threshold pairs, replayed them through the existing
  robustness/local-paper path, and kept the result descriptive with no
  promotion gate.
- Added the first bounded calibration holdout replay. The Docker `research`
  smoke reused the calibration threshold grid unchanged on the disjoint
  `snapshot=2026-06-18` CVS, FCX, and KO slices, produced 511 local-paper fills,
  and kept output descriptive with no best threshold or promotion gate.
- Added the first bounded real-data candidate breadth queue. The Docker
  `research` smoke trained and evaluated three nearby `m1_lb*_b10_s10`
  variants on CVS, FCX, and KO under strict caps and recorded no winner,
  recommendation, or promotion gate.
- Added the first bounded breadth holdout bridge. The Docker `research` smoke
  consumed the breadth queue artifact, calibrated each candidate on the source
  CVS/FCX/KO slices, replayed disjoint holdout CVS/FCX/KO slices through
  local-paper, verified all fills were `local_paper`, and recorded no winner or
  promotion gate.
- Added the first bounded depth target. The Docker `research` smoke consumed
  the breadth holdout artifact, selected `m1_lb3_b10_s10` with a deterministic
  `research_scheduling_only` heuristic, retrained/evaluated/calibrated/holdout
  replayed it under deeper bounded caps, produced `347` holdout local-paper
  fills, and recorded no winner or promotion gate.
- Added the first bounded depth-vs-breadth comparison. The Docker `research`
  smoke consumed existing external artifacts only, compared selected candidate
  evidence, recorded fill/PnL/drawdown/probability/cap deltas, and stayed
  `research_comparison_only` with no winner or promotion gate.
- Added the first bounded comparison-informed fill-aware threshold rerun. The
  Docker `research` smoke reused existing depth target traces and holdout
  slices, replayed a stricter capped threshold grid through local paper, got
  zero fills, and stayed `research_threshold_rerun_only` with no winner or
  promotion gate.
- Added the first bounded zero-fill threshold attribution. The Docker
  `research` smoke consumed existing rerun, robustness, calibration, and trace
  artifacts only, found the strict buy band sat above the observed probability
  range, and stayed `research_threshold_attribution_only` with no winner or
  promotion gate.
- Added the first bounded attribution-informed threshold band rerun. The Docker
  `research` smoke reused existing probability traces and disjoint holdout
  Yahoo slices, replayed four inside-range threshold pairs through local paper,
  produced `247` fills, and kept the result descriptive with no winner or
  promotion gate.
- Added the first bounded feature/model branch target. The Docker `research`
  smoke consumed the threshold band rerun as context, trained/evaluated
  `core_plus_bar_position_v1` on CVS, FCX, and KO, recorded a changed
  probability range, and wrote model/evaluation artifacts outside Git.
- Added the first bounded feature-branch replay attribution target. The Docker
  `research` smoke consumed the feature branch artifacts, replayed the changed
  probability evidence through local paper on CVS, FCX, and KO, produced `46`
  fills, and kept the result descriptive.
- Local-paper attribution now uses a shared source-filter helper, so research
  evidence can distinguish `source: local_paper` from future broker/live fills.
- Disabled broker boundary fuses now keep future KIS outcomes distinct from
  local-paper evidence, so bounded GPU research can resume without broker
  enablement.
- Longer bounded feature/model validation reused existing Docker `research`
  job kinds with PyTorch CUDA, trained/evaluated 708 examples for
  `core_plus_bar_position_v1`, observed probability range `0.463305`, replayed
  30 local-paper fills, and kept the result descriptive with no promotion gate.
- Warning-only market-data quality checks now explain local Yahoo 1m slice
  issues before more GPU time is spent; the initial CVS/FCX/KO smoke found only
  incomplete higher-timeframe bucket warnings.
- Candidate training/evaluation artifacts now carry compact
  `source_slices[].data_quality` summaries for local Yahoo inputs without
  changing rows, thresholds, replay behavior, or local-paper attribution.
- Data-quality-visible Docker `research` runs confirmed the summaries in both
  short 80-bar and deeper 240-bar CVS/FCX/KO candidate training/evaluation
  artifacts, then connected the deeper artifact to a single-symbol local-paper
  replay.

## Next Handoff

- The files under `agents/` are stateboards, not autonomous workers. The next
  task should keep the GPU path bounded by diagnosing the calibration runtime
  issue before launching broader threshold calibration or robustness work.
