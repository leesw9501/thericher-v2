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

1. Consume the bounded breadth queue artifact and replay the same candidates on
   disjoint holdout slices.
2. Reuse CVS, FCX, and KO from `snapshot=2026-06-18` for holdout replay.
3. Compare candidate variants descriptively; do not emit a production winner or
   promotion decision.

## Running Jobs

- Last completed: `bounded-candidate-breadth-queue-smoke`, status `completed`,
  variants `m1_lb3_b10_s10`, `m1_lb5_b10_s10`, and `m1_lb8_b10_s10`,
  trained/evaluated variants `3/3`, Docker `research` GPU `NVIDIA GeForce RTX
  4090`, artifacts under
  `D:\thericher-v2\model-artifacts\candidate-breadth-queue\bounded-candidate-breadth-queue-smoke`.

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

## Next Handoff

- The files under `agents/` are stateboards, not autonomous workers. The next
  engine-research task should consume the breadth queue artifact and add a
  bounded holdout/local-paper bridge before starting broader scheduling, longer
  training, or claiming robust model quality.
