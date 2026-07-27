# TheRicher v2 Handoff

This is the current company-state projection. Git owns prior code and
decisions; D: owns raw data and generated evidence.

## Start Here

Repository: C:\Users\Public\Documents\thericher-v2

Run:

    .\scripts\start_next_codex_task.ps1

Then read NEXT_CODEX_GOAL.md, AGENTS.md, RUNBOOK.md, and the active
stateboards.

Authority:

    Operator -> Codex Orchestrator -> Role Agents

Codex owns routine lane assignment, implementation, verification, Git, and
next-goal refresh. Ask the operator only for a real live-money, paid,
unclear-rights, public-exposure, or major-runtime decision.

## Product Direction

The product is a private US-equity engine that learns toward repeatable
profits:

    data -> features/models -> realistic validation -> KIS Paper
         -> PnL attribution -> cautiously considered live capital

Its incremental policy graph is:

    opportunity selection -> per-symbol multi-timeframe evidence
                          -> enter / hold / reduce / exit
    current positions ----> target-weight allocation
    target deltas --------> deterministic risk -> persisted broker intent

Research evidence improves the model claim. It is not an approval chain for
authorized private KIS Paper work.

## Operating Reset

- A prospective input requirement controls only its named consumer, campaign,
  or promotion. The first-five QQQ 1m pair does not block historical Research,
  Data collection, local simulation, or Paper execution preparation.
- A material company-goal block gets one compact alternatives record in the
  existing orchestration board: exact stop fact, original plan, and ready
  packages with owner, resource, engineering approach, completion evidence,
  strongest kill test, and recovery action. An apparent operator decision also
  records options, Codex's recommendation, and its exact authority boundary.
  Claude reviews that record when available; an expired CLI session is
  `review_unavailable`, not a new wait. Codex immediately advances every
  non-conflicting package inside standing authority.
- A timer, cooldown, or scheduled due time belongs to its owning worker. Codex
  advances every other ready lane rather than foreground-waiting.
- A company objective may have several disjoint role-owned packages. The
  stateboards describe lane readiness; they do not create a second goal.
- At each bounded role handoff, update only its changed objective, ready or
  running item, one evidence pointer, recovery class, and next action. This
  preserves recoverability for the next temporary executor without creating
  role-specific work diaries.
- At task resume or after an observed unexplained foreground idle period,
  Codex runs a bounded Throughput Review from ready work, active-job ownership,
  owned resources, and worker waits. It records a compact `ready / owned / due`
  dispatch fact, starts or attaches to one ready non-conflicting package, and
  keeps one measured reversible improvement in the orchestration board; it
  does not create a new approval gate or standing lane.
- Role progress is recoverable from a short stateboard plus a source-safe
  handoff event: role, bounded objective, run or Git reference, phase, owned
  resource, recovery class, next action, and evidence pointer. Until the shared
  ledger exists, use the matching Git commit and immutable external receipt;
  do not create role diaries or per-role next-goal files.
- Use parallel focused tests only when their mutable artifacts, control roots,
  Docker services, and environment are isolated. They accelerate feedback but
  do not replace the required serial goal-boundary `pytest -q`.
- Commit work that changes behavior, a contract, a test, or a measured fact.
  Do not substitute schedule reattestation or document repetition for engine
  progress.
- For KIS Data, distinguish token issuance, page pacing, and worker schedule
  facts. A token-start guard or an owned `next_due` is not a foreground delay;
  it is a reason to run another ready package while the owning worker yields.
- A completed, drained, or source-limited KIS cache is a fact about its exact
  cursor contract, not a claim that all historical coverage is exhausted. A
  future coverage need begins with a bounded endpoint-reach/page-yield probe,
  then uses one reused client and durable serial cursor progress at the measured
  request pace. It never turns a five-minute token-start guard into a worker
  sleep or replaces measured collection with a parallel request flood.
- An active KIS collection records its scope, cursor, accepted and categorical
  failure page counts, observed pace, remaining-page estimate or `unknown`, ETA
  bucket or `unknown`, owned `next_due`, and recovery class in the Data
  stateboard. That forecast is for dispatch and recovery only; it never blocks
  another lane or promises an unsupported completion date.
- GPU scheduling is work-conserving only for frozen eligible research: when the
  GPU is free, Research starts its next ready campaign or records the exact
  missing data, contract, or resource fact. It does not manufacture training to
  keep utilization high.
- After a useful KIS intraday reach/continuation probe, collection becomes a
  durable per-target cursor queue. Fresh market-session work has priority; the
  queue uses otherwise-unused measured capacity for historical backfill, and
  Research consumes immutable snapshots without waiting for collection to end.

## Current State

### Data

- D: is about 40.45 percent free. Keep data under D:\market_data and stop new
  large work before the 15 percent floor.
- The bounded NAS-only KIS Paper daily-universe probe completed on 2026-07-27
  with one token request and twelve daily pages: `AAPL`, `AMZN`, `GOOGL`,
  `META`, `MSFT`, and `NVDA` on `NAS` were all accepted through two pages with
  strict continuation progress. Its source-safe span reaches 2025-10-08 from
  the 2026-07-24 head. Raw rows remain only in the isolated D: probe cache;
  its raw-row-free evidence is under the external artifact root. This is a
  current fixed-basket capability fact, not a PIT universe, ranking input, or
  paper-trading result.
- That exact cache now has a dedicated offline, hash-bound daily panel: all six
  streams share 199 sessions from 2025-10-08 through 2026-07-24. The panel
  dataset hash is `sha256:fdd24d53ee9f7f5fd876f1f51561fc3fe7c8aea6d79d87bce83355dc4c07ed66`;
  its D: manifest and source-safe evidence hashes are
  `sha256:99ba614688e199e6c40d9c20d5d22bebbe586e4e479deeee0c40a9a40417e6f4`
  and `sha256:55bfaaa68d29e8040dc08fa0c5459a7c7123fc242389b4da3f30394ae9250978`.
  It exposes per-symbol `CatalogedBars` only to offline/local-paper validation.
  It has no network, credential, KIS, order, ranking, or Paper-trading path.
- The KIS private daily cache has a QQQ/SPY common historical intersection of
  4,756 sessions. The three-target QQQ/SPY/IWM intersection has 694 sessions;
  IWM remains source-limited at its qualified boundary.
- The bounded daily catch-up reconciliation completed with a terminal cache:
  `QQQ/NAS` is complete at 27 chunks and cursor `20070820`, `SPY/AMS` is
  complete at 26 chunks and cursor `20070821`, and `IWM/AMS` is
  `source_limited` at 10 chunks and cursor `20231010`. The one Docker catch-up
  invocation returned `drained` with zero attempted, retained, or completed
  chunks because no target was ready. It constructed no client and made no KIS
  token or market-data request. Its immutable source-safe receipt is external
  under `D:\thericher-v2\model-artifacts\data\kis-paper-daily-catchup-v1`
  with hash
  `sha256:a5a2f5bbcc8a75c72995a9e5b8e58bbda5af19e1339c09abcc55f989a17fd561`.
  This proves terminal recovery state, not new history or a research result.
- The private intraday cache has 21 complete QQQ and SPY regular sessions from
  the prior bounded historical scope. This is a pipeline control, not a KIS
  history ceiling or sufficient model corpus. On 2026-07-27, source-safe
  QQQ/NAS and SPY/AMS `PINC=1` probes each accepted terminal same-exchange-date
  pages without a continuation cursor. Their external evidence is
  `20260727T145537118121Z-09f1f5872ad57830.json` and
  `20260727T150227658709Z-6d826de2f017e316.json` under the minute-capability
  artifact root. The result closes only these exact routes as
  `source_limited` for serial continuation; it does not claim that all KIS
  historical minute paths are unavailable, and no unsupported cursor queue was
  started.
- The first fresh 2026-07-28 KST prospective QQQ head capture completed. It
  produced a ready same-session 90-minute QQQ/NAS runtime window while its
  distinct full-session coverage remains incomplete. QQQ/NAS and SPY/AMS each
  retained one current terminal page in the canonical D: cache; no raw rows are
  repeated here. This is a Data-local source fact, not a model or company hold.
- The latest 2026-07-26 source-safe QQQ KIS Paper minute calibration used one
  in-memory client/token and a 1.0-second candidate request-start interval. It
  accepted two full terminal-head pages with zero categorical limits or errors
  (three attempts including token issuance). It did not establish a route-wide
  ceiling, historical continuation, or a complete 390-minute session, and it
  retained no raw bars. Its source-safe external evidence is
  `20260726T150223752216Z-d52c06ef917b80e5.json`. The installed shared
  request-start interval is now 1.0 seconds, and the daily and intraday local
  pacing constants alias that same setting. The 60-second categorical cooldown
  and five-minute token-start guard are unchanged.
- The first single-client `session-capture` worker is implemented and its
  bounded Paper Data-only smoke wrote a source-safe D: receipt:
  `20260726T131355216487Z-cb15a58ccd594f44.json`. The scoped QQQ capture
  collected a terminal extended-session page, so its exact regular-session
  coverage is zero of 390 minutes. This is valid source evidence, not a
  strategy input or a collector failure.
- The existing `thericher-kis-paper-intraday-head` task now uses the tested
  `session-capture` mode and runs at 00:31, 02:31, 04:31, and 06:20 KST. After
  collection it runs one virtual-only QQQ session that owns its embedded
  `local_paper` recomputation, then an offline exact-session validator, a
  conditional older observer, and a source-safe terminal dispatch receipt. The
  scheduled path never builds images: task installation/update prebuilds them,
  then runtime uses `--pull never` and truthfully fails if an image is missing.
  The receipt records only stage categories and safe session IDs under the
  external artifact root. It preserves a collection failure code and exposes a
  required downstream fault as task recovery (`20`) rather than a false task
  success; the older observer is invoked only after its pair evidence exists.
  The 90-minute runtime selector is distinct from the 390-minute coverage
  observer, and a fresh receipt remains a Data/Execution fact rather than a
  company hold.
- A finite 2026-07-26 `session-capture` invocation completed through the owned
  Paper market-data path. Its QQQ/SPY outcomes recovered existing cache state;
  it did not add a qualified 390-minute regular session or a Research input.
  No account, position, order, cancel, modify, or live route was called.

### Engine Research

- The frozen QQQ KIS-private-daily CPU baseline completed with 4,756 sessions,
  an 80/20 chronological split and one-session purge. Both fixed naive
  candidates were after-cost negative in development and the descriptive
  holdout; all fills were `local_paper`. No candidate was selected.
- A Docker CUDA replication compared LSTM, causal TCN, and compact attention on
  the existing 20-session intraday scope. It wrote no checkpoint or raw data;
  it made no winner, ensemble, profitability, or Paper-authorization claim.
- The first daily QQQ/SPY sequence breadth screen completed a CPU smoke and a
  network-disabled Docker CUDA attempt. It froze 20 completed-bar features,
  3,783 development sessions, a 22-session purge, and 951 validation sessions;
  every validation feature window stayed within validation and all six replay
  cells retained `local_paper`. Three checkpoints per attempt are external
  only. No model, ensemble, promotion, holdout, KIS route, or Paper action was
  selected.
- The corrected immutable CPU L2 logistic control run
  `cpu-control-20260726T154600Z-r2` used the same hash-attested QQQ/SPY daily
  panel, 20 completed-bar features, and `3,783 / 22 / 951` split. Its
  precommit fixes `10000` local-paper cash and one-share sizing before fit and
  replay. Both model replay cells were after-cost negative and weaker than the
  previous-bar direction comparator; no model, ensemble, promotion, Paper
  intent, or profitability claim was selected. The earlier r1 artifact remains
  immutable but is unqualified because its precommit omitted replay sizing.
- The independent fixed histogram-gradient tree breadth smoke completed in the
  network-disabled Docker research profile on 2026-07-28. It used the same
  QQQ/SPY `3,783 / 22 / 951` daily split and existing local-paper replay costs,
  but no serialized estimator or raw rows. Its after-cost QQQ/SPY result was
  `-45.8296 / -73.7783`, below `previous_bar_direction` at
  `-1.7914 / -44.1851` and below flat. The candidate is falsified without
  tuning, ensembling, promotion, GPU rerun, or Paper consequence. Its external
  summary is under
  `D:\thericher-v2\model-artifacts\kis-daily-regime-tree-breadth-v1\20260728-cpu-smoke`.
- The frozen six-symbol daily CPU local-paper control completed on 2026-07-27
  from the exact 199-session current-basket panel. Its fixed 159/1/39
  development/purge/validation geometry, three-bar momentum rule,
  `always_long` comparator, one-share sizing, and after-cost replay economics
  are hash-bound in external evidence. Four descriptive per-symbol deltas were
  positive versus the comparator and two were negative. This is a
  falsification-triggering observation only, not a winner, profitability,
  ranking, promotion, ensemble, GPU, or Paper-order result; the source is not
  PIT or corporate-action qualified.
- No GPU job is active. The completed daily evidence must not be promoted or
  used to choose a Paper order. The current six-symbol panel is too small for
  depth training. QQQ/SPY has sufficient historical count for the next newly
  frozen bounded breadth campaign; it must use a new hypothesis and
  falsification contract rather than retune the rejected fixed pair. The active
  v2 joint-event contract is external at
  `D:\thericher-v2\model-artifacts\research-contracts\snapshot=2026-07-24-qqq-spy-tiingo-events-v1-joint-event-window-contract-v2.json`:
  artifact `sha256:f908dd5570c795e94e92f54b3a9e243ee0c6cef641a557561bfc4db4983bb814`,
  contract `sha256:d8c1a382ca8a16b87288ede8f31df22797574940e50f0c208d4e28dc2677c2a6`.
  It joins 114 QQQ/SPY event sessions across `t-20..t+2`, preserves the
  `3783 / 22 / 252 x 3 / 151` geometry, and has validation eligibility
  `146 / 128 / 145`. It is explicitly candidate-only with
  `model_execution_review: review_unavailable`; no model, GPU, replay, or
  Paper action follows from it.
- That parent was then locally rebuilt and reattested into exactly one
  source-safe `expanding-1` input at
  `D:\thericher-v2\model-artifacts\research-contracts\snapshot=2026-07-24-qqq-spy-tiingo-events-v1-joint-event-window-fold-input-expanding-1-v1.json`.
  Its artifact hash is
  `sha256:a15c26b6ce8f9c8c1e204cd8300b46241e2e7d894548666c73d32d030f790f0b`
  and its input identity is
  `sha256:b019c7e9a10eb2add48bbaa815c046a9b216ca9069c4ca8e4f836bc91085a1db`.
  It binds parent lineage and joint-mask identity plus exact sparse indices:
  2,345 development and 146 validation decisions. It persists no prices or
  returns and remains non-executable; the local catalog remains the sole
  source of in-memory values for its fold-local consumers.
- Temporary Validation independently recomputed the fold-input identity and
  confirmed the parent linkage, non-executable scope, required reattestation
  flag, and pure import boundary without any credential or network access.
- The first reattested `expanding-1` D1 materializer is complete. Its immutable
  source-safe validation receipt is
  `D:\thericher-v2\model-artifacts\research-contracts\snapshot=2026-07-24-qqq-spy-tiingo-events-v1-d1-materializer-expanding-1-validation-first-v1.json`
  with hash `sha256:247142b6f84f7e0ce88e538ea6832c083be2d1b29b66b079c99a2ad6d6b2f748`
  and materializer identity `sha256:d8b096b6bb9e38aad7976cebff61ffb628a913da0e05be4a345dec4f8e41d772`.
  It proves only the in-memory `t-20..t+2` geometry for one sparse validation
  decision; its receipt has no price, return, label, prediction, checkpoint,
  credential, order, or PnL values. Independent Validation passed its hash,
  geometry, source-safety, and pure-import checks.
- The fold-local QQQ target/cost adapter is now complete with deterministic
  two-fill semantics: entry at `t+1`, exit at `t+2`, one basis point fee and
  two basis points slippage per fill, `0.0001` quantization, and an explicit
  Decimal precision of 34 with `ROUND_HALF_EVEN`. Its active source-safe v2
  receipt is
  `D:\thericher-v2\model-artifacts\research-contracts\snapshot=2026-07-24-qqq-spy-tiingo-events-v1-d1-target-cost-expanding-1-validation-first-v2.json`
  with hash `sha256:90beea4c501a946dd5502a2b0eb4a06b10a0ef36ed5f70f29c595a17dd6d7486`
  and target-cost identity `sha256:2c0ecbb889b8f1660929e87458e4a90d01f2390e41b25ed47e7201ab8a94b842`.
  It writes no opens, returns, labels, predictions, checkpoints, credentials,
  orders, or PnL. The immutable v1 receipt remains historical evidence only:
  Validation found that its intermediate Decimal arithmetic depended on ambient
  precision, so no v1 target result may be used. v2 independently passed the
  reproducer, source-safety, geometry, and pure-import checks.
- The first `expanding-1` candidate-only D1 screen completed in the
  network-disabled Docker research container. Its immutable CPU and CUDA
  summaries are under
  `D:\thericher-v2\model-artifacts\kis-daily-joint-event-d1-sequence-screen-v1\cpu-smoke-20260727-r1`
  and
  `D:\thericher-v2\model-artifacts\kis-daily-joint-event-d1-sequence-screen-v1\cuda-screen-20260727-r1`.
  Their source-safe result identities are `sha256:81e486...247f5` and
  `sha256:8c4e49...32068`. Both consumed exactly `2345 / 146` sparse
  development/validation decisions, fit normalization only on development,
  and recorded aggregate classification metrics only. They wrote no rows,
  targets, predictions, model parameters, replay, PnL, broker event, or Paper
  decision. CUDA used the RTX 4090 once; no candidate was selected.
- The independent `expanding-2` lineage is now reattested without consuming
  any first-screen result. Its immutable fold input is
  `sha256:79723a4713b5a4751b6a62ddcd700b67542012bf3ff17a44958b7bd3d67c9305`
  with input identity
  `sha256:6507570e49022133ff1055d49d610a6c32e80b92c0f881115f67d9e68e899f4e`.
  It binds exactly `2511 / 128` sparse development/validation decisions. Its
  source-safe materializer and target/cost receipts are respectively
  `sha256:e489f1bfadf0c685acaa0ff030d184fdc94b191aa4684b4cad7db3c69099709f`
  and `sha256:4de77ac80db46b1378c5728473e2f31c04b5c5343ffde8ddf507b9afb16941da`.
  Both reattest byte-for-byte from the local catalog, retain only lineage and
  `t-20..t+2` geometry for validation decision `4099`, and persist no market
  values, labels, predictions, weights, replay, PnL, broker, account, or
  credential data. The pure adapters now accept only explicit `expanding-1`,
  `expanding-2`, or `expanding-3` pins; they do not form a multi-fold campaign.
- Temporary Validation independently passed the second-fold parent lineage,
  `2511 / 128` counts, final 151-session-tail exclusion, source-safety, pure
  import/route isolation, and the narrowly scoped Docker external-mount rule.
  A Docker recovery invocation reached the external mount and correctly refused
  to overwrite the existing immutable receipts.
- The fixed `expanding-2` candidate-only D1 screen is now complete. Its
  immutable CPU and CUDA evidence is under
  `D:\thericher-v2\model-artifacts\kis-daily-joint-event-d1-sequence-screen-v1\cpu-smoke-expanding-2-20260727-r1`
  and
  `D:\thericher-v2\model-artifacts\kis-daily-joint-event-d1-sequence-screen-v1\cuda-screen-expanding-2-20260727-r1`,
  with source-safe result identities
  `sha256:96a29b18e95e495a8ccfb0146b8654dadde37118ca99c672ef48c55b20a7106e`
  and `sha256:233629de1a3fc1a4c0a1ab2a1d86f7a0d0c4c387c3a6a26a169442f380b2826e`.
  Both use only the fixed linear and compact-GRU candidates, exact `2511 / 128`
  sparse decisions, and development-only normalization. They retain aggregate
  classification evidence only; no model, threshold, ensemble, replay, PnL,
  broker event, Paper intent, or account artifact was selected or created.
  Temporary Validation passed lineage, counts, tail, source-safety, and route
  isolation. The CUDA attempt used the research container's network-disabled
  GPU path once.
- The final independent `expanding-3` input contract is now complete. Its
  fold input is
  `sha256:40d6c9920a0edec12249f4b429c503b085b2e908466093496da8e0b6717128fc`
  with identity
  `sha256:1cf334306f1e2cc0e907d688d697c850aaf6ca0ef7ed2c42ee807f2c9633d11e`.
  It binds exact `2671 / 145` sparse development/validation decisions. Its
  source-safe validation materializer and v2 target/cost receipts are
  `sha256:e0b90a504e10c12460282b71707649f59c49f9b2b4b4c03598d892ceb3c147c8`
  and `sha256:4c389d437ed5c6ad35908dd98e1639e8ab17d41db889a7e5d1d6437c78961560`,
  with materializer/target identities
  `sha256:72c41ae3a2d6494d65879839ff8e93d6652352e8873928769b775f44726de43d`
  and `sha256:5511c3f072e81debe81c39792d6ca4b9500773ebf0d4029b9c7d501286176cc3`.
  They preserve only parent lineage and `t-20..t+2` geometry before the final
  151-session tail. Host and network-disabled Docker reattestation both kept
  the immutable-write boundary; Temporary Validation passed source-safety and
  route isolation. No model, replay, PnL, broker, or Paper artifact exists.
- The final independent `expanding-3` candidate-only D1 screen is now complete.
  Its immutable CPU and CUDA evidence is under
  `D:\thericher-v2\model-artifacts\kis-daily-joint-event-d1-sequence-screen-v1\cpu-smoke-expanding-3-20260727-r1`
  and
  `D:\thericher-v2\model-artifacts\kis-daily-joint-event-d1-sequence-screen-v1\cuda-screen-expanding-3-20260727-r1`,
  with source-safe result identities
  `sha256:438b720b0aeb6e95b884d03b9e60add9e10b63030544af94a4451783b7c20e87`
  and `sha256:f3ad319969ac2b59965e1a545ef52cd17bb7afef9135c45cb4b250402803922a`.
  Both consume only E3's `2671 / 145` sparse split with development-only
  normalization and retain aggregate classification evidence only. Independent
  Validation passed lineage, tail, source-safety, immutability, and route
  isolation. No result selected a model, changed a threshold, created an
  ensemble, replay, PnL, Paper decision, account, order, or broker artifact.
- The fixed D1 cross-fold falsification check has written immutable source-safe
  external evidence under
  `D:\thericher-v2\model-artifacts\kis-daily-joint-event-d1-crossfold-falsification-v1\crossfold-falsification-20260727-r1`.
  Its precommit and result identities are
  `sha256:991a344522cdd9a51af370e8a8ec9e9b1335cf8f301b8bb9af4f490c325b2330`
  and
  `sha256:1bbbc7ea47ceb6ce4d2b75409d020a1486bb4a6a6ea071ce4246852cca18bc5d`.
  It pins exactly the six E1/E2/E3 CPU/CUDA summary/precommit pairs, preserves
  mode and fold separation, and never pools their overlapping windows. All
  twelve fixed candidate/mode/fold observations are `falsified`: neither fixed
  candidate strictly exceeds its own fold-local class-majority count. This is
  a failure result for the fixed pair only, not model selection, a claim about
  all future architectures, replay, PnL, KIS, or Paper evidence. Temporary
  Data, Execution, and Validation checks passed; the Claude CLI OAuth failure
  remains `review_unavailable`. The verifier also rejects Windows reparse-point
  destinations before creation and statically excludes environment/subprocess
  route expansion. Full goal-boundary verification passed: focused tests were
  `9 passed`, the parallel full suite was `1365 passed, 13 skipped` in 102.86
  seconds, and the authoritative serial suite matched it in 510.80 seconds.
- `expanding-1` ends before the parent contract's later `expanding-2` and
  `expanding-3` folds. The final 151-session unused tail begins after those
  folds, not immediately after `expanding-1`; exact sparse input lists prevent
  this screen from consuming either later fold or the final tail.
- The offline reattestation helper now accepts an explicit market-data root,
  and the joint contract recognizes only Docker's `/app/market_data` and
  `/app/model_artifacts` bind mounts as external storage. Host storage remains
  `D:\market_data` and `D:\thericher-v2\model-artifacts`.
- The prospective pair-bound observer remains isolated and local-paper-only.
  It becomes an additional observation input when its Data pair exists.
- The new prospective QQQ runtime control freezes a same-session 90/18/9
  completed-bar baseline and a hash-bound provisional receipt. It replays the
  original proposal only through external `local_paper`; the current stale
  smoke and its independent cache reattestation create no model, GPU,
  selection, or profitability claim.

### Execution

- local_paper, kis_paper, and kis_live routes remain distinct. Simulated fills
  remain labeled source: local_paper.
- KIS Paper account/market/order work is standing-authorized for this private
  project. KIS_LIVE_* is never readable or callable.
- The local operations console is credential-free and reads sanitized
  projections only.
- The 2026-07-27 virtual-only `kis-readonly` bridge completed once and wrote
  source-safe external evidence
  `execution/kis-paper-console-bridge/20260727T020227800614Z-complete.json`
  with SHA-256
  `39eacd7453014d257216fc540939322f5105cdbdabe2bba8bc8313769b06e8db`.
  The validated runtime reader observed a fresh complete `kis_paper` envelope
  with `read_only: true` and `submission_capability: false`; no KIS order,
  cancellation, modification, or reconciliation route ran. Its five-minute
  runtime view later became safely unavailable rather than serving stale facts.
- The loopback-only dashboard now preserves the canonical sanitized account
  envelope in `/state`, including its source and read-only/submission
  capability fields. The private view may render typed account facts required
  by the local console, but never receives credentials, account identifiers, or
  raw broker payloads; those facts never enter Git, external evidence, logs,
  Claude, or chat.
- Existing scheduled Paper facts are categorical. No current receipt proves a
  selected model, external fill, or realized PnL.
- A target-position binding now derives a deterministic local-paper delta
  intent or a scoped no-intent for an already-satisfied/mismatched target. It
  preserves route isolation and makes no KIS call.
- The QQQ/NASD virtual canary route is now test-backed and isolated from the
  offline loop. It consults a fresh QQQ Paper account fact and conflicting-order
  state only after a current `enter` or `exit` receipt, then uses the existing
  durable receipt canary with cancellation/reconciliation. `hold`, `reduce`,
  `abstain`, stale, missing, or out-of-scope-position results are target-local
  no-intent facts. No KIS_LIVE_* path is readable or callable.
- Current and historical QQQ receipt pointers live in the Execution stateboard
  and external evidence. They do not prove model quality, external fill, or
  realized PnL, and no prior account view is an input to a later QQQ session.

## KIS Throughput Facts

- There is no verified daily call allowance for this route. KIS documents
  per-second request limits and lower REST capacity for Paper accounts.
- The project observed EGW00201 after a rapid virtual request sequence. The
  installed 1.0-second shared request-start gate and 60-second cooldown are
  evidence-backed temporary controls, not approval gates. The daily and
  intraday collector-local delays now alias the same shared interval.
- KIS documents a 24-hour access token and a six-hour renewal behavior. The
  current five-minute cross-process token-start guard prevents short-lived
  workers from colliding; it is not a token lifetime or a reason to idle a
  ready lane. One running collector keeps its in-memory client/token across
  eligible pages while it remains valid; the guard controls only a fresh token
  POST and does not
  imply cross-process token sharing.
- The bounded calibration accepted a 1.0-second QQQ terminal-head candidate
  with one in-memory token, two full pages, and zero categorical errors. It is
  evidence for one end-to-end setting change, not a universal throughput claim;
  do not use a parallel request flood. The probe rejects unsupported intervals
  and cannot record success when its observed page-request starts are faster
  than the claimed tested interval.
- A focused end-to-end daily test now proves one shared-gate wait between token
  and the first page plus one collector-owned wait before a second page; it
  proves the second page is not delayed twice. The drained production path
  constructs no client, so it has no token-start or page pacing activity.
- Before any future shared-default change, Data must inventory the gate, client,
  collector, and scheduler delays. A lower gate alone is not an acceleration if
  a longer local collector delay remains effective. The cooldown and the
  five-minute token-start guard remain, and the token guard never means a
  five-minute worker or foreground wait.
- The measured single-client capture path now records capture-scoped coverage
  and is the existing head task's configured collection mode. A terminal page
  remains current-head evidence, not permission to invent a historical cursor.
  Data collection may continue while Research and Execution advance independent
  ready work.
- The new fixed NAS six-symbol daily-history collector is isolated at
  `D:\\market_data\\us_equities\\kis_paper_private\\daily-nas-history\\v1`,
  with source-safe receipts under
  `D:\\thericher-v2\\model-artifacts\\data\\kis-paper-daily-nas-history-v1`.
  Its bounded token-reusing continuation and fixed two-target recovery are
  complete. The recovery admitted only `MSFT/NAS` and `NVDA/NAS`, accepted
  seven pages in five chunks, and recorded one categorical result. `MSFT/NAS`
  reached its target-local `daily_response_invalid` source limit at `2017-Q4`;
  `NVDA/NAS` completed at `2007-Q3`. The generation-121 cache is terminal:
  `AAPL`, `AMZN`, and `NVDA` are complete, while `GOOGL`, `META`, and `MSFT`
  are source-limited. It records 239 accepted pages and eight categorical
  results, with no next due. The recovery used daily market-data only: no
  account, position, open-order, quote, order, Tiingo, or live route. Every
  immutable receipt remains external and source-safe; raw rows remain only in
  D:. The frozen probe, six-symbol panel, and QQQ/SPY/IWM catalog hashes remain
  unchanged at `sha256:ffe916...fd0eac`, `sha256:99ba614...17e6f4`, and
  `sha256:e0bb847...1ac660`.

## Active Lanes

- Data owns provider behavior, cache correctness, calendars, resampling,
  manifests, and capability measurement.
- Engine Research owns campaigns, features, models, validation, GPU work, and
  model-side PnL attribution.
- Execution owns deterministic risk, intents, fills, reconciliation, account
  facts, and KIS adapters.
- Validation and Infra are invoked only when a bounded package needs them.
- agents/orchestration.md is Codex's concise cross-lane projection, not an
  additional lane.

## Boundaries

- Keep market data on D:\market_data and generated artifacts on
  D:\thericher-v2\model-artifacts or /app/model_artifacts. Never commit either.
- Never output secrets, tokens, account identifiers, raw provider/broker
  payloads, raw prices, or sealed holdout labels.
- No paid source, paid service, unclear-rights asset, public service, or major
  runtime change without operator authority.
- Use source-separated datasets, point-in-time feature availability, and
  chronological splits. A source limitation constrains only the claim that
  depends on it.

## Claude

Claude is a concise drift brake for material architecture, promotion, holdout,
ensemble, scheduler-widening, execution-risk, blocked-goal, and operator-option
decisions. On 2026-07-26, 2026-07-27, and 2026-07-28 KST the CLI OAuth session
remained expired during the relevant checks, including route simplification and
blocked-goal governance; no private material was sent. This is a scoped tooling
fault, not a hold on ready private work or a substitute for reserved authority.

## Recovery

At start, after interruption, and before trusting a checkpoint, inspect
durable evidence and classify a run as resume, restart, reconcile, complete,
unrecoverable, or operator. A failed source probe, a missing prospective pair,
or a scheduled wait affects only its own input or worker. It cannot become a
global permission or progress latch.

## Next Handoff

Follow NEXT_CODEX_GOAL.md. The next company objective builds a small,
source-scoped liquid-universe manifest from existing local evidence. The fixed
NAS daily-history collector remains terminal for its exact current-listing
scope; do not reopen a terminal target, blend a provider, or reinterpret the
manifest as a PIT universe. Keep Data, Research, and Execution evidence
distinct, and let the scheduler own its session due time rather than the
foreground.
