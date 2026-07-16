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

1. Run one bounded AMD entry feature-input diagnostic from the completed
   segment-quality artifact before changing source context, feature/model axes,
   or thresholds again.
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
- Last completed:
  `bounded-out-of-symbol-disjoint-eval-replay-cap2-240bars-20260716`, status
  `completed`, replayed AAPL, ABNB, ABT, ACN, and ABBV with `max-bars 240`,
  produced `14` verified `source: local_paper` fills, PnL range
  `-0.8866000000000` to `0E-13`, and wrote replay, robustness, event, and
  research-job artifacts outside Git.
- Last completed:
  `bounded-longer-out-of-symbol-disjoint-eval-post-entry-summary-20260716`,
  status
  `candidate_feature_branch_replay_longer_window_post_entry_summary_only`,
  found `7` closed segments, all with post-entry sell-threshold signals, and
  no open segments remaining in the 240-bar replay.
- Last completed:
  `bounded-longer-out-of-symbol-disjoint-eval-trade-path-20260716`, status
  `candidate_feature_branch_replay_trade_path_attribution_only`, attributed
  `7` closed segments, found `5` fee-aware negative and `2` non-negative
  segments, recorded fee-aware delta sum `-2.5214`, and verified all `14`
  parsed fills were `source: local_paper`.
- Last completed: bounded trade-path attribution helper, which codifies the
  manual trade-path evidence as a pure function with focused tests, reuses
  shared fill-source verification, handles FIFO partial fills and open segments,
  and matched the longer-window artifact shape in a real-artifact smoke.
- Last completed:
  `bounded-out-of-symbol-eval-bar-pressure-standardized-smoke-20260716`,
  status `candidate_feature_branch_evaluated_only`, trained
  `core_plus_bar_pressure_v1` with `hidden_units=4` and
  `feature_standardization` on CVS/FCX/KO source slices, evaluated directly on
  AAPL, ABNB, ABT, ACN, and ABBV with `1180` examples, recorded probability
  range `0.414124`, and wrote feature-branch/training/evaluation/model
  artifacts outside Git.
- Last completed:
  `bounded-out-of-symbol-eval-bar-pressure-standardized-replay-cap2-240bars-20260716`,
  status `completed`, replayed out-of-symbol threshold pairs `0.554/0.438`
  and `0.555/0.438` across AAPL, ABNB, ABT, ACN, and ABBV with `max-bars 240`,
  produced `4` verified `source: local_paper` fills, PnL range
  `-0.9266000000000` to `0E-13`, and wrote replay/robustness/event/research
  artifacts outside Git.
- Last completed: `bounded-out-of-symbol-eval-opportunity-attribution-20260716`,
  status `candidate_feature_branch_replay_attribution_only`, found `2` buy
  opportunities, `832` sell opportunities, `4` replay fills, all fills
  `source: local_paper`, and wrote an artifact-only attribution under the
  external model artifact root.
- Last completed: `bounded-out-of-symbol-eval-trade-path-20260716`, status
  `trade_path_attributed_only`, used the shared trade-path helper on the
  out-of-symbol evaluation replay, attributed `2` closed ABNB segments, found
  both fee-aware negative, and recorded fee-aware delta sum `-1.8532`.
- Last completed: bounded entry-quality diagnostic helper, which codifies
  buy-opportunity and local-paper entry diagnostics from provided probability
  trace entries and `Bar` data, keeps fixed 5/15/30-bar diagnostic overlay
  marks, and writes no artifacts itself.
- Last completed: `bounded-out-of-symbol-eval-entry-quality-20260716`, status
  `entry_quality_diagnostic_only`, consumed the out-of-symbol replay,
  opportunity, trade-path, trace, event, and selected bar evidence, found `2`
  ABNB buy opportunities, both entered via `source: local_paper`, with all
  5/15/30-bar forward close marks negative and sell-threshold signals `7` bars
  after entry.
- Last completed: `bounded-entry-adverse-feature-branch-smoke-20260716`, status
  `candidate_feature_branch_evaluated_only`, added
  `core_plus_entry_adverse_v1`, trained on CVS/FCX/KO source slices, evaluated
  directly on AAPL, ABNB, ABT, ACN, and ABBV with `1180` examples, and recorded
  probability range `0.417344`.
- Last completed:
  `bounded-entry-adverse-feature-branch-replay-cap2-240bars-20260716`, status
  `completed`, replayed thresholds `0.524/0.478` and `0.525/0.478` across the
  out-of-symbol slices, produced `8` verified `source: local_paper` fills, PnL
  range `-0.5477000000000` to `0.2254000000000`, and max drawdown
  `1.3644012207031`.
- Last completed:
  `bounded-entry-adverse-feature-branch-opportunity-attribution-20260716`,
  found `4` buy opportunities, `682` sell opportunities, `8` replay fills, and
  all fills `source: local_paper`.
- Last completed: `bounded-entry-adverse-feature-branch-trade-path-20260716`,
  attributed `4` closed segments, found `3` fee-aware negative and `1`
  non-negative segment, and recorded fee-aware delta sum `-1.0069`.
- Last completed:
  `bounded-entry-adverse-feature-branch-entry-quality-20260716`, found `4`
  entered buy opportunities across AAPL, ABNB, and ACN; `3` of `4` 5/15/30-bar
  forward close marks were negative, and all fills stayed `source:
  local_paper`.
- Last completed: `bounded-feature-branch-comparison-20260716`, status
  `feature_branch_comparison_only`, consumed only existing bar-pressure and
  entry-adverse artifacts, found entry-adverse added `4` local-paper fills and
  `2` buy opportunities, reduced the negative PnL floor by `0.3789`, added one
  non-negative closed segment, increased max drawdown by `0.41109572753904`,
  and wrote a descriptive comparison artifact outside Git.
- Last completed: `bounded-entry-adverse-segment-contrast-20260716`, status
  `entry_adverse_segment_contrast_only`, consumed existing replay,
  trade-path, entry-quality, trace, and selected local-bar evidence, contrasted
  three fee-aware negative segments against one non-negative segment, found the
  negative segments had negative 5/15/30-bar forward close marks while the ACN
  non-negative segment had non-negative forward marks, and wrote a compact
  descriptive artifact outside Git.
- Last completed: `bounded-entry-adverse-wide-sample-summary-20260716`, status
  `entry_adverse_wide_sample_summary_only`, replayed the completed
  `core_plus_entry_adverse_v1` branch on 10 additional out-of-symbol local
  Yahoo slices in two Docker `research` batches, verified all `18` fills were
  `source: local_paper`, found `9` buy opportunities, `9` closed segments, `6`
  non-negative and `3` negative fee-aware segments, no open segments, and
  fee-aware delta sum `2.7739`.
- Last completed: `bounded-entry-adverse-wide-sample-signal-quality-20260716`,
  status `entry_adverse_wide_signal_quality_diagnostic_only`, consumed existing
  wide-sample replay, trace, trade-path, and selected local-bar evidence, found
  the non-negative segment group had higher average entry probability margin,
  faster first sell-threshold timing, larger favorable excursion, and less
  adverse excursion than the negative group, and recorded second-batch zero
  fills as buy thresholds above observed slice maximum probabilities.
- Last completed: `bounded-entry-adverse-hidden8-contrast-summary-20260716`,
  status `entry_adverse_hidden_units_contrast_summary_only`, ran hidden-units
  `8` for `core_plus_entry_adverse_v1` in Docker `research`, observed
  probability range `0.617755`, replayed cap-2 thresholds across the first six
  wider-sample symbols, produced `4` verified local-paper fills, and attributed
  both closed AMAT segments as fee-aware negative with fee-aware delta sum
  `-8.4776`.
- Last completed: `bounded-entry-adverse-hidden8-loss-attribution-20260716`,
  status `entry_adverse_hidden8_loss_attribution_only`, consumed existing
  hidden8 artifacts plus selected AMAT bars, found hidden8 AMAT segments had
  lower average entry probability margin, smaller favorable excursion, larger
  adverse excursion, and fee-aware delta sum `-11.1294` below the hidden4 AMAT
  reference.
- Last completed: `bounded-entry-adverse-weightdecay-contrast-summary-20260716`,
  status `entry_adverse_weightdecay_contrast_summary_only`, ran
  `core_plus_entry_adverse_v1` with hidden-units `4`, `weight_decay=0.01`, and
  `feature_standardization` in Docker `research`, replayed cap-2 thresholds on
  ADBE/ADI/ADP/AEM/AGG/AMAT, verified `4` local-paper fills, attributed `2`
  closed AMAT segments with fee-aware delta sum `2.6518`, and wrote the
  descriptive contrast under the external artifact root.
- Last completed:
  `bounded-entry-adverse-weightdecay-wide-sample-summary-20260716`, status
  `entry_adverse_weightdecay_wide_sample_summary_only`, replayed the same
  `weight_decay=0.01` branch on AMD/AMGN/AMT/AMZN, found zero additional buy
  opportunities or fills, and summarized the 10-symbol evidence as `4`
  local-paper fills, `2` buy opportunities, `18` zero-fill variants, `2`
  non-negative closed AMAT segments, and fee-aware delta sum `2.6518`.
- Last completed:
  `bounded-entry-adverse-weightdecay001-wide-sample-summary-20260716`, status
  `entry_adverse_weightdecay001_wide_sample_summary_only`, ran
  `core_plus_entry_adverse_v1` with hidden-units `4`, `weight_decay=0.001`,
  and `feature_standardization` in Docker `research`, replayed the 10-symbol
  wider sample, found `4` local-paper fills, `2` buy opportunities, `18`
  zero-fill variants, `2` non-negative closed AMAT segments, fee-aware delta
  sum `2.6518`, and first-six probability range `0.531473`.
- Last completed:
  `bounded-entry-adverse-regularization-trace-collapse-20260716`, status
  `entry_adverse_regularization_trace_collapse_diagnostic_only`, consumed
  existing hidden4, hidden8, `weight_decay=0.01`, and `weight_decay=0.001`
  artifacts only, reran no training or replay, verified referenced fills stayed
  local-paper-only, and recorded that regularization removed hidden4 negative
  segments while reducing buy opportunities from `9` to `2` and replay fills
  from `18` to `4`.
- Last completed:
  `bounded-entry-adverse-feature-input-concentration-20260716`, status
  `entry_adverse_feature_input_concentration_diagnostic_only`, consumed
  existing traces, trade paths, and selected local Yahoo rows only, found the
  regularized AMAT entries were the same unique signal row as hidden4 AMAT
  non-negative entry, and recorded batch2 top-probability margins remained
  below buy thresholds for hidden4, `weight_decay=0.01`, and
  `weight_decay=0.001`.
- Last completed:
  `bounded-entry-adverse-sourcebreadth-weightdecay001-summary-20260716`,
  status `entry_adverse_sourcebreadth_weightdecay001_summary_only`, trained
  the fixed `core_plus_entry_adverse_v1`, hidden-units `4`,
  `weight_decay=0.001`, `feature_standardization` branch on ADBE, ADI, ADP,
  AEM, AGG, and AMAT from `snapshot=2026-06-18`, replayed AMD, AMGN, AMT, and
  AMZN, produced `4` local-paper fills on AMGN, and attributed both closed
  AMGN segments as fee-aware negative with fee-aware delta sum `-4.923`.
- Last completed:
  `bounded-sourcebreadth-amgn-loss-attribution-20260716`, status
  `sourcebreadth_amgn_loss_attribution_only`, consumed existing source-breadth,
  trade-path, opportunity, feature-input, and selected AMGN local-bar evidence,
  reran no training or replay, found the AMGN entry reused the previous
  `weight_decay=0.001` batch2 near-threshold AMGN feature row within `1e-9`
  tolerance, and attributed the conversion to a probability lift plus lower
  source-breadth buy band around a zero-range, low-volume signal shape.
- Last completed:
  `bounded-entry-adverse-signal-hygiene-diagnostic-20260716`, status
  `entry_adverse_signal_hygiene_diagnostic_only`, consumed existing
  entry-adverse artifacts only, found the zero-range/very-low-volume pattern
  concentrated in one AMGN row that recurred across regularized batch2
  near-threshold rows and the source-breadth loss entry, and recorded that the
  pattern does not explain all hidden4 first-six loss-bearing rows.
- Last completed:
  `bounded-entry-adverse-sell-latency-attribution-20260716`, status
  `entry_adverse_sell_latency_attribution_only`, consumed existing
  signal-hygiene, AMGN loss, and wider-sample signal-quality artifacts only,
  compared `11` entry-adverse segments, found loss-bearing segments averaged
  `6.6` bars to first sell signal versus `1.333333333333` for non-negative
  segments, and recorded larger adverse movement before sell in the
  loss-bearing group.
- Last completed:
  `bounded-entry-adverse-exit-timing-overlay-20260716`, status
  `entry_adverse_exit_timing_overlay_only`, consumed existing artifacts and
  selected local Yahoo rows, labeled fixed 2/3/5-bar overlays as
  `diagnostic_overlay`, preserved local-paper fills, found fixed 2-bar exits
  improved `5` of `5` loss-bearing segments on average, and also worsened
  `4` of `6` non-negative segments.
- Last completed:
  `bounded-entry-adverse-exit-policy-sketch-20260716`, status
  `entry_adverse_exit_policy_sketch_only`, consumed existing exit-timing,
  sell-latency, and signal-hygiene artifacts only, recorded `5`
  research-only exit-policy family sketches, kept fixed 2-bar exit as a stress
  overlay, and identified latency-cap plus adverse-then-latency overlays as the
  next replayable evidence shape without selecting a policy.
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
- The 240-bar replay closed all fill-bearing segments but still left negative
  PnL. The next evidence should attribute closed trade paths before changing
  model or threshold axes.
- Trade-path attribution shows the longer-window losses are closed-trade
  losses, not open-position residue. The next step should codify this
  attribution so future replay artifacts can be inspected without manual
  scripts.
- Trade-path helper behavior is now codified. The next evidence should return
  to bounded GPU research by evaluating the current feature branch directly on
  the out-of-symbol slices before trying a new feature or model axis.
- Out-of-symbol feature-branch evaluation reduced entries to two buy
  opportunities, but both resulting closed ABNB trade segments were fee-aware
  negative. The next evidence should inspect entry quality and sell-threshold
  timing around those buy opportunities before changing another model or
  threshold axis.
- Entry-quality diagnostics show the loss-bearing entries had almost no
  favorable excursion and negative 5/15/30-bar marks, while sell-threshold
  signals did appear before the later bounded-window adverse extreme. The next
  evidence should try one bounded feature branch aimed at pre-entry adverse
  pressure or weak follow-through, not a threshold-only branch.
- The entry-adverse feature branch changed opportunity distribution and reduced
  the negative PnL floor versus the prior out-of-symbol branch, but total
  trade-path fee-aware delta stayed negative. Compare the two completed
  branches artifact-only before changing another feature/model axis.
- The feature-branch comparison shows entry-adverse changed trade distribution
  but still has negative fee-aware aggregate behavior. The next evidence should
  inspect negative versus non-negative entry-adverse segments before changing
  another feature/model axis.
- Entry-adverse segment contrast showed useful path differences, but only four
  closed segments. The next evidence should widen replay to a capped additional
  out-of-symbol sample before changing another feature/model axis.
- The wider entry-adverse sample produced more closed segments and a positive
  aggregate fee-aware delta, while a second batch had zero buy opportunities.
  The next evidence should explain segment quality and zero-fill behavior from
  existing artifacts before changing another feature/model axis.
- Signal-quality diagnostics now explain the wider sample enough to spend one
  bounded GPU contrast on hidden-units `8` for the same feature set, without
  adding a new feature axis or threshold search.
- Hidden-units `8` widened probability evidence but concentrated fills into
  AMAT losses. The next evidence should explain that loss concentration from
  existing traces and paths before another model or threshold branch.
- Hidden8 loss attribution argues against spending the next block on a wider
  hidden-units axis. The next bounded GPU contrast should keep hidden-units `4`
  and test one regularization setting for the same feature set.
- The weight-decay contrast produced fewer opportunities than the 10-symbol
  hidden4 reference but kept its first-six fills local-paper-only and
  non-negative. The next evidence should finish the same branch on the
  remaining wider-sample symbols before adding another feature or model axis.
- The completed `weight_decay=0.001` wider sample matched `weight_decay=0.01`
  on local-paper fills and AMAT trade paths, while adding only a tiny first-six
  probability-range delta and still leaving batch2 at zero buy opportunities.
  The next evidence should diagnose this regularization trace-collapse from
  existing artifacts before adding another feature, model, or threshold branch.
- The regularization trace-collapse diagnostic points to a feature-input
  concentration question: the surviving regularized entries are AMAT-only while
  batch2 max probabilities sit below the buy bands. The next evidence should
  compare entry-adverse feature inputs for entered AMAT rows, hidden4 negative
  and non-negative rows, and batch2 near-threshold rows before another GPU
  model axis.
- Feature-input concentration showed the regularized AMAT entries are not new
  breadth; they are the same hidden4 AMAT non-negative row. The next evidence
  should keep feature set, model size, preprocessing, and `weight_decay=0.001`
  fixed while testing one wider source-symbol training context against the
  batch2 symbols.
- Source-breadth training moved fills away from AMAT and broke the previous
  batch2 zero-fill state, but the recovered AMGN fills were both fee-aware
  negative. The next evidence should attribute AMGN loss paths from existing
  artifacts before changing another feature/model or threshold axis.
- AMGN loss attribution showed source breadth converted an existing
  near-threshold row into entry rather than finding the earlier AMAT
  non-negative pattern. The next evidence should inspect zero-range and
  low-volume signal-shape recurrence across existing entry-adverse artifacts.
- Signal-hygiene diagnostic showed the zero-range/very-low-volume pattern is
  real but narrow. The next evidence should compare sell-threshold latency and
  adverse movement before changing another feature/model axis.
- Sell-latency attribution showed delayed sell signals and adverse movement are
  broader than the AMGN zero-range row. The next evidence should compare simple
  diagnostic exit overlays against the existing local-paper exits without
  changing replay.
- Exit-timing overlay showed a real loss-side benefit but also a non-negative
  segment trade-off. The next evidence should sketch a research-only exit
  policy family before any replay rerun or code change.
- Exit-policy sketch narrowed the next code step to a pure diagnostic overlay
  helper. Ask Claude before adding it, keep overlays separate from local-paper
  fills, and add focused tests only.
- Diagnostic exit-overlay helper now codifies fixed 2/3/5-bar overlays and
  conditional latency/adverse metadata from provided segments and `Bar` inputs
  only, with all overlay outcomes labeled `source: diagnostic_overlay`.
- Diagnostic exit-overlay helper smoke applied the helper to `11` existing
  entry-adverse segments, produced `33` fixed overlay marks, matched previous
  one-off timestamp/price evidence for all `33`, and preserved local-paper
  sources.
- Conditional exit-overlay contrast compared `3` metadata probes across `5`
  loss-bearing and `6` non-negative segments. The latency>=5, 2-bar probe
  matched `4` loss-bearing segments and no non-negative segments, while
  adverse<=-1 at 3 bars matched only the duplicated AMGN loss path.
- Exit-latency composite diagnostic substituted fixed 2-bar
  `diagnostic_overlay` outcomes for the `4` latency-matched loss-bearing
  segments, retained `7` local-paper exits, and moved overall gross delta from
  `-1.4563` to `3.383729296875` descriptively without replay.
- Diagnostic exit-composite helper now codifies the source-labeled composite
  calculation as a pure helper with focused tests for substituted diagnostic
  outcomes, retained local-paper outcomes, missing metadata, and group
  summaries.
- Diagnostic exit-composite helper smoke reproduced the one-off composite
  source counts and gross-delta sums with the pure helper, including `4`
  diagnostic overlay outcomes, `7` local-paper outcomes, and overall composite
  gross sum `3.383729296875`.
- Research-only exit-latency sandbox helper now consumes provided trace timing
  records and `Bar` inputs, emits `source: diagnostic_overlay` marks when the
  latency condition is met, and reports missing signal/bar/horizon states
  without touching local-paper replay.
- Exit-latency sandbox helper smoke consumed existing real artifacts and
  selected `snapshot=2026-06-18` Yahoo rows, matched the composite helper smoke
  on `4` latency-matched diagnostic marks with gross-delta sum
  `-2.486370703125`, and created no local-paper fills or broker outcomes.
- Fixed entry-adverse GPU validation ran in Docker `research` with RTX 4090
  visible, trained on ADBE/ADI/ADP/AEM/AGG/AMAT, evaluated
  ANET/APH/APO/APP/ASML/AVGO, recorded probability range `0.493954`, replayed
  cap-2 local-paper thresholds with `4` fills, and attributed `2` closed APH
  segments with fee-aware delta sum `1.4194`.
- Longer-depth entry-adverse contrast ran in Docker `research` with RTX 4090
  visible, kept the same feature/model/source/evaluation settings, raised only
  training caps to `max_epochs=16` and `max_steps=512`, recorded probability
  range `0.460215`, replayed cap-2 local-paper thresholds with `4` fills,
  attributed `2` closed APH segments with fee-aware delta sum `8.0192`, and
  wrote a depth-vs-short comparison artifact outside Git.
- Short-vs-depth APH signal/path attribution consumed existing artifacts only,
  reran no training or replay, and found the deeper run's fee-aware lift came
  from one-bar-earlier APH entry plus a later sell-threshold crossing, while
  the larger drawdown came from staying long through a later close-marked peak
  and pullback.
- Second-holdout replay contrast ran existing Docker `research`
  feature-branch replay twice for the short and longer-depth entry-adverse
  artifacts on AAPL, ABBV, ABNB, ABT, ACN, and AMD. Both runs produced zero
  buy opportunities, zero local-paper fills, flat PnL/drawdown, and compact
  zero-fill threshold-gap attribution under the external model artifact root.
- First-evaluation source-context contrast discovered the existing
  `candidate_feature_branch` data-slice cap of `6`, left it unchanged, trained
  the cap-compliant ANET/APH/APO/APP/ASML/AVGO source context in Docker
  `research`, replayed AAPL, ABBV, ABNB, ABT, ACN, and AMD, recovered AMD-only
  local-paper fills, and attributed `3` closed AMD segments with fee-aware
  delta sum `3.3752`.
- AMD segment-quality diagnostic consumed existing source-context trace, event,
  trade-path, and selected AMD bar evidence only. The fee-aware negative AMD
  segment had entry margin `0.0000736074447632`, adverse delta about `-5.08`,
  and negative 2/3/5-bar diagnostic marks, while the two non-negative segments
  averaged entry margin `0.0009030294418335`, minimal adverse movement, and
  positive 2/3/5-bar diagnostic marks.

## Next Handoff

- The files under `agents/` are stateboards, not autonomous workers. The next
  task should inspect AMD entry feature inputs from the completed
  segment-quality artifact before spending another GPU block on source data,
  feature/model, or threshold changes.
