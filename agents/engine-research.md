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

1. Add a bounded multi-slice local Yahoo training/evaluation source so the next
   candidate is not trained only on deterministic sample bars.
2. Run one capped PyTorch CUDA candidate training job inside Docker `research`
   using selected local Yahoo slices.
3. Reuse the robustness replay path to compare the new candidate across CVS,
   FCX, and KO without a promotion gate.

## Running Jobs

- Last completed: `bounded-candidate-threshold-robustness-smoke`, status
  `completed`, slices `CVS`, `FCX`, `KO`, completed variants `15`, total fills
  `222`, PnL range `-0.691598626708984` to `0.19990000000000`, artifacts under
  `D:\thericher-v2\model-artifacts\candidate-threshold-robustness\bounded-candidate-threshold-robustness-smoke`.

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

## Next Handoff

- The files under `agents/` are stateboards, not autonomous workers. The next
  engine-research task should train/evaluate on multiple local Yahoo slices
  before starting broader scheduling or claiming robust model quality.
