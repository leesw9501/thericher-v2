# Execution Agent

## Engine Loop

- paper trading
- live-risk control
- PnL attribution

## Owns

- Local paper order lifecycle, simulated fills, positions, and cash accounting.
- Broker adapter boundaries, KIS paper/live adapters when explicitly allowed.
- Execution hard stops such as emergency stop, duplicate client order id, and
  risk limits.

## Must Not

- Introduce strategy logic beyond risk checks.
- Call KIS APIs until a future goal explicitly allows it.
- Place paper or live orders until explicitly allowed.
- Read credentials or `.env`.

## Held Resources

- Local emergency state only.

## Active Queue

1. Add execution risk-limit preflight only when a future paper-loop goal needs
   it.
2. Keep future KIS adapter work separate from local paper simulator behavior.
3. Add more realistic order types only when paper-loop evidence needs them.

## Running Jobs

- None.

## Done Recently

- Local emergency store exists for stop-new-orders and cancel-open-orders
  requests.
- Broker-free local paper simulator now supports accepted/rejected/canceled
  order events, next-bar-open fills, duplicate id rejection, emergency-stop
  blocking, deterministic account replay, and local paper fill metadata.
- Bounded validation now consumes local paper only and keeps fills labeled with
  `source: local_paper`.
- Candidate replay now consumes local paper only and verified generated fills
  remain labeled with `source: local_paper`.
- Candidate replay comparison verified both candidate and momentum baseline
  fills remain labeled with `source: local_paper`.
- Threshold sweep replay verified every variant fill remains labeled with
  `source: local_paper`.
- Threshold robustness replay verified every CVS, FCX, and KO variant fill
  remains labeled with `source: local_paper`.
- Multi-slice candidate robustness replay produced zero fills under the existing
  grid; no non-local fill source was observed.
- Probability-derived calibration robustness replay produced `524` simulated
  fills across CVS, FCX, and KO; every fill source was verified as
  `local_paper`.
- Calibration holdout replay produced `511` simulated fills across CVS, FCX,
  and KO; every fill source was verified as `local_paper`.
- Breadth holdout bridge mini smoke produced `400` simulated fills across three
  candidates and CVS, FCX, and KO holdout slices; every fill source was
  verified as `local_paper`.
- Depth target mini smoke produced `347` simulated fills across CVS, FCX, and
  KO holdout slices; every fill source was verified as `local_paper`.
- Holdout verification now treats missing event files for zero-fill replay
  variants as empty evidence while still requiring readable event artifacts for
  variants that produce fills.
- Depth-vs-breadth comparison reran no execution, preserved existing
  local-paper source verification, and confirmed both compared artifacts report
  all simulated fills as `local_paper`.
- Fill-aware threshold rerun replayed stricter threshold variants through the
  local-paper path and produced zero fills, with no non-local fill source.
- Zero-fill threshold attribution reran no execution, preserved existing
  local-paper verification, and attributed the zero fills to thresholds above
  observed buy opportunities.
- Attribution-informed threshold band rerun replayed 12 threshold variants
  through local paper, produced `247` fills, and verified every fill source was
  `local_paper`.
- Feature-branch replay attribution replayed 9 threshold variants through local
  paper, produced `46` fills, and verified every fill source was `local_paper`.
- Local-paper fill-source evidence is now centralized in an execution helper.
  It can return local-paper-only fills, flag mixed or unknown sources, tolerate
  missing zero-fill event files, and reject unreadable nonzero-fill evidence.
- Broker adapter boundary contracts now exist with disabled KIS capabilities,
  typed unavailable submit/cancel/status results, `source: broker_disabled`,
  and tests proving no network, credentials, broker submit, or event-log writes.
- Cap-limited calibration holdout replay produced `228` simulated fills across
  CVS, FCX, and KO holdout slices; every fill source was verified as
  `local_paper`.
- Bar-pressure feature-branch replay produced `6` simulated fills across CVS,
  FCX, and KO holdout slices with cap 2; every observed fill source was
  verified as `local_paper`.
- Hidden-units model-axis feature-branch replay produced zero simulated fills
  across CVS, FCX, and KO holdout slices with cap 2; no non-local fill source
  was observed.
- Hidden-units contrast replay also produced zero simulated fills across CVS,
  FCX, and KO holdout slices; no non-local fill source was observed.
- Feature-branch derivation-guard replay restored the hidden4 cap-2 threshold
  pair count and still produced zero simulated fills across CVS, FCX, and KO
  holdout slices; no non-local fill source was observed.
- Feature-branch replay opportunity attribution rebuilt fill-source evidence
  from robustness JSON event paths. The guarded hidden4 variants still had zero
  fills, missing zero-fill event files were recorded separately, and no
  non-local fill source was observed.
- Regularization model-axis replay rebuilt fill-source evidence from the
  existing local-paper robustness path. The weight-decay cap-2 variants still
  had zero fills, missing zero-fill event files were recorded separately, and
  no non-local fill source was observed.
- Feature-normalization replay rebuilt fill-source evidence from the existing
  local-paper robustness path. The standardized cap-2 variants still had zero
  fills, missing zero-fill event files were recorded separately, and no
  non-local fill source was observed.
- Source-vs-holdout probability alignment reran no execution. It reused the
  existing feature-branch replay attribution local-paper verification, kept
  replay fill count at zero, and observed no non-local fill source.
- Disjoint-evaluation feature-branch replay used the existing local-paper path
  and produced `4` verified `source: local_paper` fills with no non-local fill
  source.
- Out-of-symbol disjoint-evaluation replay reused the existing local-paper path
  across AAPL, ABNB, ABT, ACN, and ABBV, produced `10` verified
  `source: local_paper` fills, and observed no non-local fill source.
- Out-of-symbol loss attribution parsed existing fill event evidence and
  confirmed all `10` fill events were `source: local_paper`; no broker path was
  used.
- Out-of-symbol fill-lifecycle attribution parsed existing local-paper event
  files and confirmed `10` fill events, `3` closed segments, and `4` open
  segments without rerunning replay or touching broker code.
- Out-of-symbol post-entry attribution reran no execution. It preserved the
  existing `local_paper` fill evidence and found open segments lacked a
  post-entry sell-threshold signal before the bounded window end.
- Out-of-symbol exit-horizon diagnostic overlay did not create local-paper
  fills; diagnostic marks were labeled separately from existing
  `source: local_paper` fill evidence.
- Longer-window out-of-symbol replay reused the existing local-paper path,
  produced `14` verified `source: local_paper` fills, and observed no non-local
  fill source.
- Longer-window trade-path attribution parsed existing event files and
  confirmed all `14` fill events remained `source: local_paper`; no broker path
  was used.
- Trade-path attribution helper reuses shared fill-source evidence, surfaces
  non-local fill sources separately, and does not touch broker submit/cancel
  code.
- Out-of-symbol evaluation feature-branch replay reused the existing
  local-paper path across AAPL, ABNB, ABT, ACN, and ABBV, produced `4`
  verified `source: local_paper` fills, and observed no non-local fill source.
  Follow-up opportunity and trade-path attribution parsed existing event files
  only; trade-path attribution found `2` closed ABNB segments, both
  fee-aware negative, without touching broker submit/cancel code.
- Entry-quality diagnostic reran no execution. It consumed existing
  local-paper source verification, linked the two ABNB buy opportunities to
  local-paper entry fills, kept path marks labeled as diagnostic overlay
  evidence, and observed no non-local fill source.
- Entry-adverse feature-branch replay reused the existing local-paper path,
  produced `8` verified `source: local_paper` fills, and observed no non-local
  fill source. Follow-up opportunity, trade-path, and entry-quality attribution
  parsed existing event files only and reran no broker behavior.
- Feature-branch comparison reran no execution. It consumed existing replay and
  attribution artifacts only and confirmed both compared branches kept fills
  `source: local_paper`.
- Entry-adverse segment contrast reran no execution. It consumed existing
  local-paper replay/event evidence only and confirmed the contrasted closed
  segments used `source: local_paper` fills.
- Wider entry-adverse replay ran through the existing broker-free local-paper
  path in Docker `research`, produced `18` verified `source: local_paper`
  fills across the first batch, zero fills in the second batch, and observed no
  non-local fill source.
- Wider entry-adverse signal-quality diagnostic reran no execution. It consumed
  existing local-paper replay/event evidence and preserved local-paper source
  verification.
- Entry-adverse hidden-units contrast ran through the existing broker-free
  local-paper path, produced `4` verified `source: local_paper` fills, and
  observed no non-local fill source.
- Hidden8 loss attribution reran no execution. It consumed existing
  local-paper replay/event evidence and preserved local-paper source
  verification.
- Entry-adverse weight-decay replay reused the existing broker-free
  local-paper path, produced `4` verified `source: local_paper` fills on AMAT,
  and follow-up opportunity, trade-path, and contrast attribution parsed
  existing event files only without touching broker submit/cancel code.
- Weight-decay wider-sample completion replayed AMD/AMGN/AMT/AMZN through the
  same local-paper path, produced zero additional fills, and preserved
  local-paper-only source verification for missing zero-fill event files.
- Lighter weight-decay replay used the same broker-free local-paper path,
  produced `4` verified `source: local_paper` fills on AMAT, produced zero
  additional AMD/AMGN/AMT/AMZN fills, and kept missing zero-fill event files as
  empty local-paper evidence rather than broker activity.
- Regularization trace-collapse diagnostic reran no execution and preserved
  existing local-paper source verification across hidden4, hidden8,
  `weight_decay=0.01`, and `weight_decay=0.001` artifacts.
- Feature-input concentration diagnostic reran no execution and only matched
  existing local-paper entry timestamps to probability traces and local bars.
- Source-breadth replay used the existing broker-free local-paper path,
  produced `4` verified `source: local_paper` fills on AMGN, and follow-up
  opportunity/trade-path attribution parsed existing event files only. Both
  closed AMGN segments were fee-aware negative.

## Next Handoff

- Keep broker execution disabled until a future explicit KIS paper goal allows
  API calls and credential handling.
- The next attribution task should consume existing AMGN local-paper evidence
  only and must not touch broker submit/cancel code.
