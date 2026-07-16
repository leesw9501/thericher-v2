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

1. Start a bounded longer-window out-of-symbol replay before another model axis
   or threshold-only branch is tried.
2. Keep short experiments for breadth and longer candidate training for depth
   visible as separate queues.
3. Do not call either path a production recommendation, promotion, or pass/fail
   result.

## Running Jobs

- Previous completed: `bounded-dq-visible-candidate-replay-cvs-20260716`, status
  `completed`, candidate `m1_lb3_b10_s10`, replayed CVS at `0.48/0.455`,
  produced `37` `source: local_paper` fills, PnL `-0.08440213623047`, and
  wrote artifacts under
  `D:\thericher-v2\model-artifacts\candidate-replay\bounded-dq-visible-candidate-replay-cvs-20260716`.
- Previous completed: `bounded-hidden4-derivation-guard-replay-cap2-20260716`,
  status `completed`, candidate
  `m1_lb3_b10_s10__core_plus_bar_pressure_v1`, replayed guarded threshold
  pairs `0.998/0.447` and `0.999/0.447` across CVS, FCX, and KO holdout
  slices, produced zero fills, restored threshold pair count to `2`, and wrote
  artifacts under
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay\bounded-hidden4-derivation-guard-replay-cap2-20260716`.
- Last completed: `bounded-hidden4-opportunity-attribution-20260716`, status
  `candidate_feature_branch_replay_attribution_only`, attributed 6 guarded
  threshold variants across CVS, FCX, and KO holdout traces, found `0` buy
  opportunities versus `136` sell opportunities, kept replay fill count at
  `0`, and wrote artifacts under
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-hidden4-opportunity-attribution-20260716`.
- Last completed: `bounded-weightdecay-opportunity-attribution-20260716`,
  status `candidate_feature_branch_replay_attribution_only`, consumed the
  weight-decay `core_plus_bar_pressure_v1` replay, found `0` buy opportunities
  versus `124` sell opportunities across 6 guarded holdout variants, kept
  replay fill count at `0`, and wrote artifacts under
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-weightdecay-opportunity-attribution-20260716`.
- Last completed:
  `bounded-standardized-bar-pressure-feature-normalization-smoke-20260716`,
  status `candidate_feature_branch_evaluated_only`, trained/evaluated
  `core_plus_bar_pressure_v1` with `hidden_units=4` and
  `feature_standardization`, recorded source probability range `0.724726`
  with max probability `0.792910`, and wrote feature-branch, training,
  evaluation, model, and research-job artifacts outside Git.
- Last completed:
  `bounded-standardized-bar-pressure-feature-normalization-replay-cap2-20260716`,
  status `completed`, replayed source-derived threshold pairs `0.791/0.440`
  and `0.792/0.440` across CVS, FCX, and KO holdout slices, produced zero
  local-paper fills, and wrote replay/robustness/research-job artifacts outside
  Git.
- Last completed: `bounded-standardized-opportunity-attribution-20260716`,
  status `candidate_feature_branch_replay_attribution_only`, attributed the
  standardized cap-2 replay to `0` holdout buy opportunities versus `160` sell
  opportunities across 6 variants, kept replay fill count at `0`, and wrote
  artifacts under
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-standardized-opportunity-attribution-20260716`.
- Last completed: `bounded-standardized-probability-alignment-20260716`,
  status `candidate_feature_branch_replay_attribution_only`, extended the
  standardized replay attribution with source-vs-holdout probability
  summaries: source max `0.792910`, holdout max `0.526492`, buy threshold min
  `0.791000`, threshold gap `0.264508`, zero buy opportunities, and zero
  local-paper fills. Artifact:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-standardized-probability-alignment-20260716`.
- Last completed:
  `bounded-disjoint-eval-bar-pressure-standardized-smoke-20260716`, status
  `completed`, trained `core_plus_bar_pressure_v1` with
  `feature_standardization` on CVS/FCX/KO from
  `snapshot=2026-07-09-shadow-t0-8d-probe`, evaluated on disjoint CVS/FCX/KO
  from `snapshot=2026-06-18`, recorded evaluation probability range
  `0.504265`, and wrote feature-branch/training/evaluation/model/research-job
  artifacts outside Git.
- Last completed:
  `bounded-disjoint-eval-bar-pressure-standardized-replay-cap2-20260716`,
  status `completed`, replayed disjoint-evaluation-derived thresholds
  `0.525/0.431` and `0.526/0.431` across CVS, FCX, and KO eval slices,
  produced `4` verified `source: local_paper` fills, and wrote replay,
  robustness, event, and research-job artifacts outside Git.
- Last completed: `bounded-disjoint-eval-opportunity-attribution-20260716`,
  status `candidate_feature_branch_replay_attribution_only`, found `2` buy
  opportunities, `182` sell opportunities, `4` replay fills, all fills
  `source: local_paper`, and wrote artifacts under
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-disjoint-eval-opportunity-attribution-20260716`.
- Last completed:
  `bounded-out-of-symbol-disjoint-eval-replay-cap2-20260716`, status
  `completed`, replayed disjoint-evaluation-derived thresholds `0.525/0.431`
  and `0.526/0.431` across AAPL, ABNB, ABT, ACN, and ABBV from
  `snapshot=2026-06-18`, produced `10` verified `source: local_paper` fills,
  and wrote replay, robustness, event, and research-job artifacts outside Git.
- Last completed:
  `bounded-out-of-symbol-disjoint-eval-opportunity-attribution-20260716`,
  status `candidate_feature_branch_replay_attribution_only`, found `7` buy
  opportunities, `312` sell opportunities, replay PnL range
  `-0.95330549316406` to `0E-13`, all fills `source: local_paper`, and wrote
  attribution plus compact summary artifacts under the external model artifact
  root.
- Last completed:
  `bounded-out-of-symbol-disjoint-eval-loss-attribution-20260716`, status
  `candidate_feature_branch_replay_loss_attribution_only`, consumed existing
  replay/robustness/trace artifacts only, found `5` fill-bearing variants and
  `5` zero-fill variants, observed all fill-bearing variants had negative PnL,
  verified `10` local-paper fill events, and wrote one compact artifact outside
  Git.
- Last completed:
  `bounded-out-of-symbol-disjoint-eval-fill-lifecycle-20260716`, status
  `candidate_feature_branch_replay_fill_lifecycle_attribution_only`, parsed
  existing fill event files plus selected Yahoo bars, found `3` closed
  segments, `4` open segments, and `4` of `5` fill-bearing variants held an
  open long position to the bounded window end, with all `10` fill events
  `source: local_paper`.
- Last completed:
  `bounded-out-of-symbol-disjoint-eval-post-entry-attribution-20260716`,
  status `candidate_feature_branch_replay_post_entry_attribution_only`,
  consumed existing probability traces and lifecycle evidence, found all `3`
  closed segments had post-entry sell-threshold signals and all `4` open
  segments had no sell-threshold signal before the bounded window end.
- Last completed:
  `bounded-out-of-symbol-disjoint-eval-exit-diagnostic-20260716`, status
  `candidate_feature_branch_replay_exit_diagnostic_overlay_only`, compared
  open segments against fixed 5-bar and 15-bar `diagnostic_overlay` marks,
  found only `2` of `8` marks available inside the 120-bar window, and kept
  diagnostic marks separate from local-paper fill counts.
- Previous completed: `bounded-dq-visible-candidate-evaluation-depth-20260716`,
  status `completed`, candidate `m1_lb3_b10_s10`, evaluated 708 examples,
  probability range `0.451895`, and confirmed CVS, FCX, and KO source slices
  carry compact non-blocking `data_quality` summaries.
- Interrupted: `bounded-dq-visible-candidate-calibration-depth-20260716` ran
  for more than 10 minutes without writing its calibration artifact and was
  stopped; diagnose this before relying on the calibration path for longer
  loops.
- Completed runtime probe: `bounded-calibration-runtime-cvs-40-20260716`
  finished a 40-bar, one-slice calibration in about 35 seconds.
- Completed bounded cap probe:
  `bounded-calibration-runtime-3slice-80-cap2-20260716` finished an 80-bar,
  three-slice calibration with `threshold_pair_cap=2` in about 2 minutes 36
  seconds, replayed 6 variants, and produced 214 local-paper fills.
- Last completed: `bounded-dq-visible-calibration-holdout-cap2-20260716`,
  status `completed`, replayed the cap-2 thresholds on disjoint CVS, FCX, and
  KO holdout slices, produced 228 verified `source: local_paper` fills, and
  recorded holdout PnL range `-0.76329816894531` to `-0.10999633789062`.
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
- Calibration runtime is now bounded at the research job wrapper with
  `--threshold-pair-cap`; the runbook smoke uses cap 2 to avoid accidentally
  replaying the full derived grid across multiple slices.
- Cap-limited calibration holdout kept fills local paper but stayed negative
  across the disjoint slices, so the next research block should branch to
  feature/model inputs rather than continuing threshold-only tuning.
- Added `core_plus_bar_pressure_v1` as one bounded feature-set branch using the
  existing candidate feature builder and research job family. Docker
  `research` trained/evaluated 348 CVS/FCX/KO examples with 7 features,
  observed probability range `0.517376`, then replayed a cap-2 holdout band
  across CVS, FCX, and KO with `6` verified local-paper fills and PnL range
  `-0.23820000000000` to `0.15070000000000`.
- Added one bounded hidden-units model-axis branch. Docker `research`
  trained/evaluated `core_plus_bar_pressure_v1` with `hidden_units=16` on 348
  CVS/FCX/KO examples, observed probability range `0.963878`, then replayed a
  cap-2 holdout band across CVS, FCX, and KO with zero local-paper fills and no
  non-local fill evidence.
- Ran one hidden-units contrast branch with existing code only. Docker
  `research` trained/evaluated `core_plus_bar_pressure_v1` with
  `hidden_units=4` on 348 CVS/FCX/KO examples, observed probability range
  `0.904793`, then replayed a cap-limited holdout band across CVS, FCX, and KO
  with zero local-paper fills and no non-local fill evidence. The derived
  threshold pair count fell to 1 because max probability was `1.000000`.
- Added a bounded feature-branch replay threshold derivation guard. Saturated
  max-probability evidence now clamps the buy ceiling to `0.999`, records
  `saturation_guard` metadata only when applied, and the hidden4 guarded replay
  restored the requested cap-2 threshold count while still producing zero fills.
- Added bounded saturated feature-branch replay opportunity attribution without
  adding a job kind. The guarded hidden4 holdout traces had max probabilities
  near `0.465` to `0.469`, so both `0.998` and `0.999` buy thresholds sat above
  the observed holdout range and produced no buy opportunities.
- Added one bounded regularization model-axis selector, `weight_decay`, for
  candidate training and feature-branch jobs only. The Docker `research`
  smoke used `core_plus_bar_pressure_v1`, `hidden_units=4`, and
  `weight_decay=0.01`; source max probability remained `1.000000`, cap-2
  replay produced zero local-paper fills, and attribution found zero holdout
  buy opportunities.
- Added one bounded feature preprocessing selector,
  `feature_standardization`, for candidate training and feature-branch jobs
  only. Docker `research` trained/evaluated `core_plus_bar_pressure_v1` with
  `hidden_units=4`; source probability range widened to `0.724726`, but
  cap-2 holdout replay still produced zero local-paper fills and attribution
  found zero holdout buy opportunities.
- Extended existing feature-branch replay opportunity attribution with compact
  source-vs-holdout probability alignment deltas. The standardized branch's
  source max probability exceeded holdout max by `0.266418`, explaining why
  source-derived buy thresholds produced zero holdout buy opportunities.
- Added one bounded disjoint-evaluation feature-branch path. Defaults are
  unchanged, job runner accepts `--evaluation-data-slice` only for
  `candidate_feature_branch`, artifacts record training and evaluation
  lineage, and Docker `research` replay recovered a small number of
  local-paper fills without changing broker behavior.
- Replayed the disjoint-evaluation feature branch on five additional existing
  symbols. Probability range was no longer the main mismatch, but fills landed
  with a negative PnL floor, so the next step should attribute loss behavior
  before changing another model axis.
- Attributed the out-of-symbol negative PnL floor to fill-bearing variants
  rather than probability range mismatch. The next evidence should connect
  those fills to price path and final position lifecycle before changing model
  or threshold axes.
- Connected fill-bearing out-of-symbol variants to local-paper lifecycle and
  selected bar paths. The next evidence should inspect post-entry probability
  traces to see whether sell signals appeared before the bounded window end.
- Confirmed open loss-bearing segments had no post-entry sell-threshold signal
  before the bounded window end. The next evidence should keep actual replay
  untouched and compare a tiny diagnostic horizon overlay, clearly separated
  from local-paper fills.
- The 120-bar replay window was too short for most fixed horizon diagnostics
  because open entries occurred near the bounded window end. The next evidence
  should rerun the same out-of-symbol slices with a longer bounded window
  before changing model or threshold axes.

## Next Handoff

- The files under `agents/` are stateboards, not autonomous workers. The next
  task should run a bounded longer-window out-of-symbol replay before another
  hidden-units, regularization, preprocessing, or threshold-only branch.
