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

## Latest Research Integration

- The first source-local Tiingo raw-D1 snapshot is complete for SPY, QQQ, and
  IWM at `D:\market_data\us_equities\tiingo_etf_daily\canonical\snapshot=20260801T173121Z-tiingo-etf-d1-r1`.
  It spans available raw daily history through 2026-07-31 and has a source-safe
  aggregate receipt under `D:\thericher-v2\model-artifacts\data-receipts\tiingo-etf-d1`.
  The companion CPU control precommitted a causal `5/20/60` lookback matrix,
  70/30 chronological split, 61-session purge, raw feature-side discontinuity
  mask, event window, and fixed `5/10/20`-bp cost band. Its evaluated validation
  momentum cells were below flat across the band; SPY/QQQ 60-session validation cells were
  input-unavailable. It is descriptive offline evidence only: no winner, GPU
  appointment, ensemble, KIS runtime input, Paper action, or profitability
  claim follows. A later daily family needs a new hypothesis and source contract.
- The distinct Tiingo sequence breadth campaign is also complete. Its source-
  contract input is `sha256:340a6acede3e8d9d8058a766c9a7b1bfc6fb98a0bab68656d2bad3ed928d7849`;
  its CPU comparator is at
  `D:\thericher-v2\model-artifacts\research\tiingo-d1-sequence-breadth-v1\cpu\sequence-cpu-20260802T032249\summary.json`
  and its network-disabled Docker PyTorch CUDA summary is at
  `D:\thericher-v2\model-artifacts\research\tiingo-d1-sequence-breadth-v1\cuda\sequence-cuda-20260802T032438-r2\summary.json`.
  The family fixes `5/20` raw-OHLCV sequences through completed `t`, a next-day
  open-to-close direction label, a 70/30 split, 22-session purge, retrospective
  event masking, and `5/10/20`-bp costs. GRU, causal TCN, and compact attention
  wrote no weights or checkpoints; all six fixed architecture-window aggregates
  are negative at 10 bp. This is descriptive no-selection evidence, not a model
  winner, ensemble, profitability claim, KIS runtime feature, or Paper action.
  A later campaign must use a distinct hypothesis rather than retuning this run.
- The updated local Norgate trial was tail-checked before an expensive broad
  rebuild. The official Windows host interface resolves the active US database
  to `D:\market_data\us_equities\norgate_us_platinum_trial`; its aggregate-only
  receipt is
  `D:\thericher-v2\model-artifacts\data\norgate-trial-tail-readiness-v1\tail-norgate-tail-20260802-r1`
  (`sha256:457b27d392c812782b56da2962bccbc2e8bcd8e00d593ead15f09cc960a13952`).
  SPY/QQQ/IWM expose 28 common completed sessions after 2026-06-22, and the
  41-calendar-day interval cannot reach the predeclared 126-session independent
  holdout. The prospective Norgate broad campaign is therefore
  `input_unavailable`; no rebuild, membership recheck, per-symbol scan, GPU
  appointment, model result, or Paper consequence follows. This scoped data
  fact must not delay another ready engine or execution package.
- The independent QQQ 1m window-sensitivity CPU preflight completed against the
  retained 20-session KIS cache. Its frozen `30/60/90/120/180`-bar matrix had
  a real Brier spread of `0.000233701152146`, below its session-block-permuted
  null P95 of `0.000627602629947`, so the predeclared result is
  `no_structure`. The source-safe external summary is
  `D:\\thericher-v2\\model-artifacts\\research\\kis-intraday-window-matrix-v1\\qqq-20260623-20260721-window-null-r1\\summary.json`.
  It selected no window, wrote no checkpoint or raw data, made no KIS/broker
  call, and does not qualify a CUDA follow-up. The spent comparison sessions
  cannot be reused to retune this family.
- The pure target-position policy foundation now joins an already-attested
  opportunity fact, explicit `1m/5m/10m/1h/3h` model evidence, and current
  exposure into a `TargetExposureProposal`. It has no default alpha, data read,
  credential, network, KIS, or order behavior; stale, missing, duplicate,
  misaligned, future, and conflicting inputs abstain. Focused tests prove that
  a unanimous entry reaches only the existing `local_paper` preparation bridge.
  The requested Claude drift check timed out, so it is recorded only as
  `review_unavailable`, not as support for a later model or Paper promotion.
- The completed-bar multi-timeframe momentum adapter now creates those five
  evidence inputs causally from one KIS-private 1m session. Its actual offline
  QQQ 2026-07-21 smoke found `sell/sell/buy/sell/sell` and correctly returned
  `expert_conflict` / `abstain`; it did not invent a signal, order, KIS call,
  credential read, network call, checkpoint, or raw-data artifact. Its
  source-safe external summary is under
  `D:\\thericher-v2\\model-artifacts\\research\\multitimeframe-momentum-policy-smoke-v1\\qqq-20260721-r1\\summary.json`.
- The first fixed 20-session QQQ multi-timeframe consensus replay completed
  locally at
  `D:\\thericher-v2\\model-artifacts\\research\\kis-intraday-multitimeframe-consensus-replay-v1\\qqq-20260623-20260721-consensus-r1\\summary.json`.
  It used only the retained verified cache, the existing receipt-to-
  `local_paper` bridge, one-share next-bar execution, and in-memory replayed
  terminal-flat fills. It retained no raw bar or fill events, called no KIS,
  broker, network, or credential path, and wrote no checkpoint. Its two entry
  sessions had a positive aggregate after-cost result, but the all-20-session
  always-long comparator is not an equal-count selection null. Treat it only
  as descriptive plumbing and preserve it immutable; the next Engine Research
  package is a separately frozen equal-count session-subset null diagnostic,
  followed by later/disjoint replication rather than parameter tuning.
  The requested Claude invocation exceeded its time limit, so it is recorded
  as `review_unavailable`; no Claude verdict is relied upon.
- The separately frozen equal-count selection-null diagnostic completed at
  `D:\\thericher-v2\\model-artifacts\\research\\kis-intraday-consensus-selection-null-v1\\qqq-20260623-20260721-null-r1\\summary.json`.
  It reproduced the baseline replay digest exactly, enumerated all `190`
  equal-count two-session subsets, and observed a one-sided subset-null value
  of about `0.1684`. With only two round trips against the predeclared minimum
  of `30`, it is `selection_unqualified`. This confirms the initial positive
  aggregate is not a model or profitability result; it creates no GPU,
  ensemble, KIS, Paper, or tuning follow-up. Future comparative evidence needs
  later/disjoint sessions under an unchanged candidate contract.
- The pure `target-exposure-allocation-v1` foundation is complete. It takes an
  existing long-only target proposal plus caller-owned exposure/capacity facts,
  applies confidence and risk multipliers before capacity/concentration caps,
  and returns only a deterministic target state. A stale, unqualified, or
  inconsistent entry allocation abstains; exhausted capacity holds current
  exposure; a fresh upstream reduce/exit is preserved. It has no data, KIS,
  credential, network, broker, artifact, or GPU path. Multi-symbol atomicity
  remains a caller-serialization and Execution revalidation responsibility.
- The local `paper_decision_bridge` can now be imported independently of the
  broad research re-export surface. Its KIS-only decision classes load only at
  KIS preparation time; this fixes a direct-import cycle without changing a
  route, order, credential, or broker behavior.
- The target-free Norgate D1 representation plumbing campaign completed its r6
  Docker CUDA batch across GRU, LSTM, temporal-convolution, and compact
  attention. It is source-isolated, static-survivorship-conditioned, and
  non-promoting; it produced no forecast, ranking, PnL, Paper signal, or model
  selection. Weights remain safe numeric files only under the external artifact
  root.
- Campaign custody now uses the append-only external control ledger. The first
  Strategy Discovery handoff pins official Chronos, TimesFM, and Uni2TS/Moirai
  code sources and licenses, but does not establish checkpoint rights,
  financial-data provenance, or a runtime adoption decision.
- Claude's `supported-with-limits` challenge found that Norgate alone cannot
  prove a KIS-reconstructible input contract. The next causal-model preparation
  step is an offline dual-source metadata conformance check, not a new GPU
  training run or a performance campaign.

## Latest Execution Integration

- The 2026-08-01 06:20 KST QQQ scheduler cycle retained a new source-safe
  terminal `sha256:f063df8e542b63698d827085d5d33e349e541e9cc7a0f0c5956f1ff70acc9b9c`
  as `recovery/collection_exit_nonzero` with scheduler exit one. Its paired
  session `sha256:6d4749bad343e070491f76b5924b0174e6fb42d87c2367d6b90523c0e4605f5b`
  is explicitly `paper_only` but closed `no_intent/runtime_window_stale`;
  no canary or durable intent is present. The matching offline validator
  `sha256:48858f9f1c5ffb50701fcdb435e88b36176698cd352a3cfef3aaff7b42b22a2c`
  reattests the same session hash and stale runtime-window lineage as
  `validated`, with no local-paper replay or canary to interpret. This is
  scoped source/collection recovery evidence, not a `canary_completed`
  lifecycle, fill/PnL evidence, or a replacement-submit trigger.
- The 2026-08-01 04:31 KST QQQ scheduler cycle retained a fresh runtime window
  and complete terminal. Its session
  `sha256:1cc710fdc948f0108dd5397eba85e654150c0ab41a48dccfdaba6902fdf5aeb6`
  was explicitly `paper_only` but closed
  `no_intent/account_unavailable`; no canary or durable intent was present.
  The paired terminal
  `sha256:f14100fe40688c506e6f5eeaeebab589ff8cf5b0fa1572f9c27970251c1fbf67`
  is `complete/complete` with collection exit zero and matching prospective
  validation `validated`; the offline local-paper replay likewise matched the
  session as `no_intent`. This is scoped recovery evidence, not a
  `canary_completed` lifecycle or a replacement-submit trigger.
- Completion interpretation for the pending QQQ canary is now fail-closed at
  the independent offline validator. A session labelled `canary_completed`
  counts only when its embedded route is explicitly Paper-only, its canary
  phase is `cancelled`, and reconciliation is `clean`; a submitted, ambiguous,
  future, non-Paper, or unresolved record remains recovery evidence rather than
  lifecycle completion. The change neither submits nor retries an order, nor
  changes the installed scheduler, decision table, sizing, or live boundary.
  Claude's falsification-first review was `supported-with-limits`: this proves
  a persisted record is self-consistent, while exact ambiguous intents still
  require their existing reconcile-first recovery path.
- The exact prior KIS Paper `outcome_unknown` run
  `canary-20260729T143501313369Z` was reconciled through the hardened
  read-only entrypoint. Its original source-safe evidence remains hash
  `sha256:2e612d02224e768c1f16aeff6a9874bc06cbf549048964795bac8370fae1858c`;
  the immutable reconciliation receipt is
  `sha256:c3ec1489d61e23ee82b2986355fafa17298be53c7fb58fe130c6a02103f83b90`.
  It remained `outcome_unknown/reconciliation_unresolved`, made no submit,
  cancel, modify, or replacement call, and did not involve a live route.
- The current QQQ lifecycle objective remains independent: the installed
  freshness-gated scheduler owns its next eligible session. The recovered
  generic unknown run is evidence about its own exact intent, not a new QQQ
  lifecycle or a hold on another authorized Paper action.
- The 2026-08-01 02:31 KST QQQ scheduler cycle retained a complete terminal
  and a runtime-ready immutable input-manifest lineage. Its session
  `sha256:a9dffdc9de7d6e9d9f0628ca9281ef2b5d5805aca6c3be5357b559b01527373e`
  was explicitly `paper_only` but closed `no_intent/account_unavailable`;
  no canary record existed. The paired terminal
  `sha256:df085f929f3bfccf359109533e2dc0a4238c6058e849f75604dbbac26af86fa3`
  is `complete/complete` with collection exit zero and matching prospective
  validation `validated`; the offline local-paper replay evidence matched the
  same session. This is scoped recovery evidence, not a
  `canary_completed` lifecycle, and it creates no replacement intent.
- The 2026-08-01 00:31 KST QQQ scheduler cycle retained a complete,
  source-safe current-window lineage and terminal `complete`. Its session
  `sha256:04a272bfb8445748718dc26ddc57173327443b1116b158f931b542880f1d2f09`
  was explicitly `paper_only` but closed `no_intent/receipt_not_eligible` from
  an input-ready abstain before account, quote, intent, canary, or broker work.
  The paired terminal
  `sha256:a3d01a68f3427c81ea5cb41f0651488cfad2e7a5431f8986484f1063378a2f35`
  is `complete/complete` with collection exit zero and prospective validation
  `validated`; its matching offline replay is likewise `no_intent`. It is not
  a `canary_completed` lifecycle and changes neither the fixed route nor the
  scheduler-owned next observation at 02:31 KST.
- The 2026-07-31 02:31 and 04:31 KST QQQ scheduler cycles both retained clean
  current head pages and terminal `complete`. The latest session
  `sha256:eca780e356bc6e8d44ef6117bc1c41c05cd83bd898b66a8933faaf841f51541b`
  closed `paper_only` `no_intent/receipt_not_eligible` before account, quote,
  intent, or canary work; its paired terminal
  `sha256:df7668bd44db53f67b9df85eb37e0f13c714896a1a38643496cecf866c662d95`
  has successful collection and prospective validation. These clean no-intent
  sessions do not change the fixed route.
- The 2026-07-31 06:20 KST QQQ scheduler cycle retained a source-safe
  Data-local recovery. Its capture
  `sha256:e76e76df43243c521ef7a7b14f8a24d4fddeb386d9a74b660c2d441f41aac529`
  rejected both current minute inputs as `minute_duplicate_conflict`; its QQQ
  session `sha256:e2c213f9558d0d2dcde3ba2e1903aee88e367a6d3f7741dd697ffaeb2e8d068c`
  closed `paper_only` `no_intent/runtime_window_stale`, before account, quote,
  intent, or canary work. Its terminal
  `sha256:d895258c638d0d4f85fdb27aeff68e8cfd76aed707e7d8694acab2c743ba21a2`
  is `recovery/collection_exit_nonzero` with prospective validation `validated`.
  The next owned due time is 2026-08-01 00:31 KST; no collector, decision-table,
  sizing, or scheduler change follows.
- The 2026-07-31 00:31 KST QQQ scheduler cycle captured clean current head
  pages and reached its fresh eligible-exit receipt, but its session
  `sha256:4d4be5eaf55c5ddcc8e7d80b0c4af60e53618817521ee47deed67b1c7cb402e7`
  closed `paper_only` `no_intent/account_unavailable`. It made no canary,
  durable order intent, submit, cancel, modify, or live call. Its paired
  terminal `sha256:235a322afd6ff0db56fbd49a759ea39fea2b1e34489b28ff9bf85abfa32de4fc`
  is `complete` with collection and prospective validation both successful.
  A separate virtual-only read-only bridge completed one minute later under
  `sha256:9dfe4e83a1cd7ed33c81930c34e4c9afd430032a3ceb7942fb6149722f3a99b4`,
  but cannot substitute for this session's account/quote boundary. Claude's
  falsification-first verdict was `unsupported` for treating that bridge as
  exact-session recovery. This scoped fact does not authorize a collector,
  decision-table, sizing, or scheduler change.
- A source-only Execution/Validation trace confirms this is not a static route
  contradiction: `receipt_not_eligible` exits before account, quote, or order
  work, and later fresh `enter` or `exit` sign pairs can use the same installed
  QQQ one-share canary path without a table, sizing, freshness, or scheduler
  change. The relevant focused tests cover the mocked fresh entry path, all
  decision-table combinations, and QQQ intent route isolation. A Claude
  block-classification request timed out without a body and is
  `review_unavailable`, not a substantive conclusion.

## Operating Reset

- A prospective input requirement controls only its named consumer, campaign,
  or promotion. The first-five QQQ 1m pair does not block historical Research,
  Data collection, local simulation, or Paper execution preparation.
- A material company-goal block gets one compact alternatives record in the
  existing orchestration board: exact stop fact, original major-work plan and
  dependency order, and ready packages with owner, resource, engineering
  approach, completion evidence, strongest kill test, and recovery action.
  First run the bounded Throughput Review to prove that no undispatched ready
  package remains. An apparent operator decision also records options, Codex's
  recommendation, and its exact authority boundary. Claude challenges whether
  the block is real, whether the alternative packages still advance the company
  outcome, and whether the recommendation crosses that boundary. An expired CLI
  session is `review_unavailable`, not a new wait. Codex immediately advances
  every non-conflicting package inside standing authority. Claude/Codex
  agreement resolves only an already-delegated reversible no-cost choice; for a
  reserved live, paid, unclear-rights, public, or major-runtime choice it
  produces one recommendation and safe preparation, never the authorization
  itself.
- A shared-worktree file without a known author is a bounded integration input,
  not a reason to hold a company objective. Codex reads the diff and provenance,
  then reattests/tests it or replaces that one package. Only a concrete
  contract/test failure can defer its dependent consumer; all other ready work
  continues.
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
  do not replace changed-path serial coverage. The full clean-root parallel
  runner is the goal-boundary Python authority after its completed 2026-07-31
  serial baseline and matching four/eight-worker results; serial `pytest -q`
  remains a weekly/material-routing compatibility diagnostic, never an
  unrelated foreground hold.
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
- The first source-scoped liquid-universe manifest is reattestable at
  `D:\market_data\us_equities\source-scoped-liquid-universe\v1\us.equities.source-scoped-liquid-universe-v1-068c34ced08eac50.json`
  with hash `sha256:068c34ced08eac50de53e9fbc27f3f78b36412b03aef6b602c35b4de5a083f4c`.
  It binds the terminal QQQ/SPY/IWM D1 index and six-symbol current NAS D1
  panel as separate source partitions and exposes nine offline unranked
  instrument references. It makes no PIT membership, liquidity, ranking,
  cross-partition alignment, model, Paper, or profitability claim.
- The first source-partitioned D1 eligibility receipt is reattestable at
  `D:\thericher-v2\model-artifacts\data\d1-liquidity-eligibility\v1\source.partitioned.d1.liquidity.eligibility-v1-7232c9c21c08b956.json`
  with hash `sha256:7232c9c21c08b9564b526a34f02c109f499594a5b2a06af889b242edf2be09de`.
  It records only a fixed 60-bar/20-bar-positive-volume/USD-10M-median-turnover
  D1 proxy, source provenance, categorical eligibility, and limitations. The
  ETF and NAS groups stay separate; IWM remains source-limited. The receipt
  contains no raw rows, observed price/volume/turnover values, credentials,
  account facts, orders, model data, ranking, or Paper authority.
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
- The bounded 2026-07-28 `SPY/NAS` `PINC=1` minute probe made one token request
  and one minute-page request, accepted zero pages, and retained the source-safe
  `minute_response_empty` result at
  `D:\\thericher-v2\\model-artifacts\\data\\kis-paper-minute-capability-probe\\20260728T161832343621Z-aeda6d998380bd52.json`.
  This makes that exact request shape `unavailable`; it is not evidence that the
  exchange mapping, provider, or all historical-minute paths are unavailable.
  No retry, cache mutation, or serial collector followed.
- A matched 2026-07-28 `SPY/AMS` `PINC=1` native-route control made one token
  request and one minute-page request, accepted one full terminal page, and
  retained source-safe evidence at
  `D:\thericher-v2\model-artifacts\data\kis-paper-minute-capability-probe\20260728T171242245242Z-0cb5b3ecc42de3c5.json`.
  It establishes only that the same client path was data-bearing on SPY/AMS
  about 54 minutes after the empty SPY/NAS observation. SPY/NAS remains an
  observed-only unavailable candidate; neither result establishes a permanent
  route property or KIS-wide historical-minute reach.
- The first fresh 2026-07-28 KST prospective QQQ head capture completed. It
  produced a ready same-session 90-minute QQQ/NAS runtime window while its
  distinct full-session coverage remains incomplete. QQQ/NAS and SPY/AMS each
  retained one current terminal page in the canonical D: cache; no raw rows are
  repeated here. This is a Data-local source fact, not a model or company hold.
- A later manual head invocation at 2026-07-27T18:58Z rejected QQQ/NAS and
  SPY/AMS with source-safe `minute_duplicate_conflict/retained_cache` results.
  Its exact head-only quarantine kept old immutable D: snapshots, rejected the
  conflicting response, and a later `session-capture` completed with a clean
  120-row page per target and zero exact overlap. The terminal receipt
  `intraday-head-20260727T1922500308577Z.json` is `complete`; the chained QQQ
  session is a validated `no_intent/runtime_window_stale`, because its 19:20Z
  latest completed bar was observed at 19:22:46Z under a fixed two-minute
  budget. No account, intent, order, or live call occurred. Quarantine markers
  now validate their exact chunk/manifest/raw identities and new snapshots
  persist `head` or `historical` scope, so historical terminal pages cannot be
  quarantined by caller convention. A subsequent 19:31Z lane-owned run, made
  before this rebuilt image was available, again found a retained-cache conflict
  and wrote a truthful `recovery/collection_exit_nonzero`; its embedded session
  remained validated `no_intent/runtime_window_stale` with a 15:30Z active
  window. A later rebuilt 19:48Z route recovered the current cache: generation
  22 has nine retained `head` chunk records per target with no current conflict
  origin or reason. The exact 19:48Z session remains a truthful stale no-intent,
  while its network-disabled `runtime-freshness-v2` reattachment records the
  completed-window end, route observation time, lag category, and fixed
  two-minute budget in a new immutable validation namespace. It does not alter
  the old receipt, force a Paper intent, or justify changing the budget.
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
- At 05:45 KST on 2026-07-28, only that existing task was rebuilt and updated
  through the scoped installer. Its action still targets the local runner with
  four triggers, `IgnoreNew`, `StartWhenAvailable`, and a 90-minute limit; its
  last-run and next-due facts remained 04:31 and 06:20 KST. The deployment built
  local images only and did not invoke KIS, a container, a Paper account, or a
  broker action.
- The first natural post-deployment 06:20 KST run produced terminal
  `recovery/collection_exit_nonzero` and advanced the current head index to
  generation 23 with nine retained chunks per target. Its QQQ session was
  `paper_only` `no_intent/runtime_window_stale`; the normal offline
  `runtime-freshness-v2` validator matched that exact session. No account,
  quote, prepared decision, canary, order, cancellation, live route, or duplicate
  task resulted. The named worker owns its next 00:31 KST recovery attempt.
- The 2026-07-29 00:31 KST scheduled head collection returned `exit_zero` and
  the exact QQQ virtual-only session returned
  `no_intent/receipt_not_eligible`. Its baseline `reduce` action correctly
  projected to a non-entry `abstain` decision receipt, so no canary, account,
  quote, intent, order, cancellation, or live route followed. The immutable
  parent terminal remains `recovery/prospective_validation_exit_nonzero`
  because the earlier offline validator incorrectly compared those two
  representations as raw strings. The shared receipt projection is now
  revalidated by construction and the exact retained session independently
  reattached through the network-disabled `runtime-freshness-v2` validator.
  This repaired no KIS data, rewrote no terminal receipt, and created no new
  broker action.
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
- The fixed ETF-source-local D1 trend-regime control completed offline from the
  reattested QQQ/SPY/IWM eligibility receipt. It used the fixed completed-D1
  20/50 SMA rule, next-two-open one-share `local_paper` replay, exact
  chronological 70/30 decision-slot split, and a time-matched always-long
  comparator. Its source-safe summary is
  `D:\thericher-v2\model-artifacts\etf-d1-trend-regime-v1\etf-d1-trend-regime-20260728-0400\summary.json`;
  its aggregate result is not globally falsified because only the SPY validation
  slice exceeded its comparator. QQQ and IWM did not; IWM's source-limited
  history limitation is fail-closed. This is neither a model, selection,
  ensemble, GPU, nor Paper input. The required source-safe Claude result review
  was unavailable because the local OAuth session is expired.
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
  projections only. On 2026-07-28 the virtual-only `kis-readonly` bridge
  completed a fresh post-hardening observation with external source-safe
  evidence `execution/kis-paper-console-bridge/20260728T115736150112Z-complete.json`.
  The loopback dashboard reattached the complete `kis_paper` envelope with
  `read_only: true` and `submission_capability: false`; it exposed only typed
  category/count facts plus local control state. No KIS order, cancellation,
  modification, or reconciliation route ran. A five-minute expiry still makes
  the runtime view unavailable rather than serving stale facts.
- The `kis-readonly` Compose service now has a read-only root filesystem and
  `/tmp` tmpfs. Its only intended writable locations are its existing local
  runtime and external artifact mounts, reducing accidental container-local
  response retention without changing the virtual read-only route.
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
- Engine Research owns campaigns, features, models, validation, research-side
  portfolio hypotheses, and model-side PnL attribution.
- Research Steward owns cross-track exclusive-GPU and sealed-evaluation
  allocation, not strategy or Execution risk.
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
remained expired during the relevant checks, including route simplification,
blocked-goal governance, and the shared-worktree integration refinement; no
private material was sent. This is a scoped tooling fault, not a hold on ready
private work or a substitute for reserved authority.

## Recovery

At start, after interruption, and before trusting a checkpoint, inspect
durable evidence and classify a run as resume, restart, reconcile, complete,
unrecoverable, or operator. A failed source probe, a missing prospective pair,
or a scheduled wait affects only its own input or worker. It cannot become a
global permission or progress latch.

## Next Handoff

The validated QQQ Paper no-intent, bounded minute-route comparison, and first
static Norgate D1 opportunity-development campaign are complete. The latter
reattested the 523-symbol frozen panel, froze a 22-date-purge causal contract,
and completed one offline CPU baseline plus one network-disabled Docker
PyTorch CUDA causal-TCN job. Its external contract/CPU/CUDA hashes are
`sha256:27e0...d8d348`, `sha256:913e...3dbf42f5`, and
`sha256:f091...541fa13`; no result selected a model or opened a KIS/Paper
route. QQQ/NAS and SPY/AMS remain source-limited only for their exact
historical-minute continuation contracts, while SPY/NAS remains an observed-
only unavailable request shape. The next company objective generalizes and
starts a source-separated, resumable KIS Paper D1 broad-backfill cache from a
local current-listing registry. The existing fresh-head schedule continues at
its own due time and is not a foreground wait.

The QQQ/SPY D1 relative-regime and separate relative-allocation CPU controls
are complete and falsified. The allocation control reused the hash-attested
4,756-session catalog and fixed `3,783 / 22 / 951` geometry, selected QQQ 312
times and SPY 131 times across 443 local-paper slots, but was after-cost weaker
than the time-matched always-QQQ comparator. Its smoke/full receipts retain
only aggregate external evidence; neither result selects a model or changes
GPU, KIS Paper, or live routes.

The terminal NAS cache is now materialized as the source-local D1 panel
`sha256:7e8d6fe5...d57dc8e`. It has a 2,179-session common intersection from
`2017-Q4` through `2026-Q3`; AAPL, AMZN, and NVDA are complete while GOOGL,
META, and MSFT retain their source-limited facts. The local manifest and external
receipt contain provenance and aggregates only. This does not establish a PIT
universe, ranking, model, Paper, or live result.

The exact NAS D1 sequence campaign is frozen from that same panel. Its
source-safe external precommit is
`sha256:c54e795b3fb2caa76c9367a72aadc1c0ac685241bd5c59e2e12bdb0af603d37e`;
it binds `1,510 / 22 / 647` phase-local sessions, 20 per-symbol completed-close
returns with the `t-20` anchor also inside the phase, one-share `t+1` to `t+2`
after-cost target semantics, and target-free validation inputs.

The same-runtime Docker r2 breadth package is complete. Its six deterministic
CPU L2-logistic smokes are summarized by `sha256:e60cf92...ffc4fa`, and its
network-disabled Docker CUDA run completed all 18 fixed LSTM, causal-TCN, and
compact-attention cells on the RTX 4090. The CUDA summary is
`sha256:2c213d0...b99dae` and its 18 `state_dict` checkpoints remain only under
`D:\thericher-v2\model-artifacts\research\kis-nas-d1-sequence-breadth-v1`.
Every recorded validation forward was target-free, finite, and bounded before
the separate sealed evaluator opened its in-memory targets.

The Docker run exposed two path-validation defects before training: the panel
reader did not recognize the mounted `/app/market_data`, and the immutable
precommit writer did not recognize `/app/model_artifacts`. Both now permit only
the exact non-symlink `market_data` or `model_artifacts` mount beneath a
repository root; normal Git children remain rejected. Claude's concise
drift-check attempt was `review_unavailable` because local OAuth is expired.

Independent review then tightened the completed breadth package: the executable
runner requires the exact frozen campaign contract/precommit before it can write
a CPU or CUDA artifact; CUDA accepts only a complete, source-safe CPU smoke
receipt and immutable sibling precommit from outside the Git workspace; and the
research container mounts repository `data` and `reports` read-only. The first
host/Docker hash mismatch remains an immutable r1 failure receipt, but r2
regenerated the unchanged package fully in Docker rather than relaxing lineage.

The Docker r4 sealed evaluator then completed all 24 fixed candidates and 18
fixed comparators using only in-memory validation targets and `local_paper`
fills. Every replay reconstructed to a terminal-flat account; no raw rows,
labels, predictions, event rows, checkpoint copies, ranking, selection,
ensemble, promotion, KIS call, or Paper order was retained or enabled. Its
source-safe precommit and summary are `sha256:999750...f71746` and
`sha256:032342...35fedf`; the latter records only a marker-detected
`execution_environment: docker` class, not a Compose-security attestation. The
versioned Compose profile and focused tests establish the network/mount contract.
The independent review also required that field. Claude's source-safe drift-check
attempt remained `review_unavailable` because local OAuth is expired.

The distinct NAS D1 volatility-conditioned package completed its one fixed
Docker sealed local-paper falsification. Its r2 CPU/CUDA input summaries remain
`sha256:65ba9f682bb6477bd7fdfa5d61761fb7ab67f3db23601187a92f88415bad69a8`
and `sha256:3158ac0e69c002394d97dc5f52946d70637e082f292a7c549498f4c045e5bc2c`.
The completed r5 precommit and source-safe summary are
`sha256:e7bd2cd8b17959a9b6df5c49c8bfa5a22ae875d9b2a53311890d55e51d7b4618`
and `sha256:803ead4440415dd2818c2bc81a5579f5ae01354a43955ad97e5a526a8634d010`.
It independently classified 24 frozen candidates and 36 fixed comparator cells;
six paired cells met the precommitted kill rule. This is a mixed candidate-only
falsification result, not a winner, aggregate performance claim, selection,
ensemble, promotion, or KIS Paper input. Every fill was in-memory
`local_paper`, every replay reconstructed a terminal-flat account, and no raw
row, target, prediction, event row, checkpoint copy, broker request, KIS call,
or live route was retained or invoked. Claude's post-evaluation challenge again
returned `review_unavailable` because OAuth could not refresh.

The completed r3/r4 evaluation directories preserve precommit-only interrupted
attempts. They are immutable recovery evidence; r5 is the only completed
receipt for this exact package. The evaluator now reattests comparators once per
bounded comparator rather than once per slot, matches CPU refits to their frozen
receipt, writes a source-safe candidate-evidence failure receipt before target
opening, and marks drawdown with entry, intrabar-low, and exit equity points.

The prospective NAS D1 shadow observer is now complete. It reattests the
frozen r2/r5 artifact identities and derives its boundary from the frozen
source input rather than file timestamps. It requires all six NAS symbols to
share a complete post-boundary decision, `t+1`, and `t+2` D1 window before
opening any target. Its network-disabled Docker smoke wrote immutable external
precommit `sha256:628663053db396626e009ec154ce17b7849fb5f2614384f74a5818f6e46f24da`
and `input_unavailable` receipt
`sha256:56e0f503b7248e10e8461a1752c3baf7df5f1a70e89d0a63909f08cfde78616a`.
Its initial offline smoke had zero six-symbol common sessions after the
2026-07-24 r5 boundary. That closes only that observation attempt; it is not a
Research, Data, or Paper hold.

The separate NAS D1 forward cache is now present at
`D:\market_data\us_equities\kis_paper_private\daily-nas-forward\v1`. Its
first bounded Paper daily-data collection accepted six pages and retained one
all-six-symbol post-boundary common session. The frozen panel reattests unchanged
at `sha256:7e8d6fe5...d57dc8e`; the forward cache/index hashes are
`sha256:700f0f...aa3aa9` and `sha256:8e5a6a...49ee18`, and the source-safe
receipt is external under `D:\thericher-v2\model-artifacts\data\kis-paper-daily-nas-forward-v1`.
The read-only historical-plus-forward projection has 29 frozen context bars per
symbol but remains `input_unavailable` with zero target slots because it needs
three common later sessions. The actual network-disabled observer smoke on the
one-session cache produced that same scoped result without model execution,
selection, KIS, or a broker effect. The installed
`thericher-kis-paper-daily-nas-forward` task owns its next 06:40 KST run:
credential-free preflight, collector only when required, then observer only on
a current or complete cache. A partial/deferred collector or invalid cache exits
with recovery `20` and cannot dispatch the observer. Claude's requested
schedule drift-check remained `review_unavailable` because local OAuth could
not refresh. This remains a forward-data mechanism, not a PIT claim, candidate
selection, ranking, or broker-order path.

## Current Candle-State r3 Package

The current independent NAS D1 candle-state package is complete as
candidate-only plumbing. It reattests the frozen six-symbol panel, derives five
per-symbol OHLCV features from 40 completed bars under one fixed Decimal
context, and canonicalizes its normalizer so host and Docker compute the same
contract identity. The original r1 mismatch and r2 review findings remain
immutable scoped recovery records; r3 uses the corrected schema and external
artifact family under
`D:\thericher-v2\model-artifacts\research\kis-nas-d1-candle-state-breadth-v3`.

The r3 CPU smoke and network-disabled Docker CUDA breadth both completed with
target-free validation forwards. The CPU receipt has a source-safe immutable
summary-attestation sidecar; CUDA ran the frozen LSTM, causal TCN, and
compact-attention candidates, and checkpoints are external safe-weight
artifacts. No selection, ensemble, PnL claim, KIS call, account action, Paper
order, or live behavior follows. Claude's falsification-first request could not
run because the local OAuth session was expired, so the evidence is explicitly
`review_unavailable`, not a claimed reviewer agreement.

## Latest Broad KIS D1 Update

The 2026-08-01 offline postprocess reattached the terminal broad cache without
a KIS, credential, network, account, order, or live call. Its generation-26,368
candidate panel covers all 2,119 current NAS targets with zero coverage gaps or
quarantines. The source-safe postrun receipt is
`sha256:5b24100dc992a4fed284859345c63b9b80f13e5c85cba0852adcef2b9453a593`;
its generation-604 overlap comparison is equal with zero target or row
mismatches. The paired chronology receipt
`sha256:d589714101992bea848ed430d30857d469bd7d5c62816c0fac177c645d10af7e`
records only aggregate span buckets and `1,089 complete / 1,030 source_limited`
target states. This completes the cache's source-local coverage observation but
does not create a PIT universe, common-history threshold, model input, ranking,
strategy, Paper action, or GPU eligibility. Any future collection remains owned
by the installed task.

The broad KIS Paper D1 cache is now active at the dedicated external
`daily-nas-broad/v1` root. Its hash-attested current-listing registry has 2,119
NASDAQ common-stock targets with explicit non-PIT/non-ranking scope. A first
eight-target bootstrap accepted 16 pages and a 32-target breadth-first
continuation accepted 64 pages, both with zero categorical failures. Its first
installed continuation advanced to generation 187: 187 targets with retained
coverage, 1,932 at zero, 368 accepted pages, and one factual target-local rate
limit. The latest source-safe receipt is `collected/reconcile` with 148 chunk
attempts and 288 accepted pages.

Its dedicated Docker profile has only KIS Paper market-data credentials and
the daily endpoint. It cannot access account, position, quote, order, or live
routes. The read-only panel materializer then reattested a byte-stable
generation-187 snapshot and wrote only external manifest/receipt facts:
dataset `sha256:09de29cfd619b331853dd2e9063315b84e2fb9397e49b238cc565bdf8ec964b7`,
187 covered targets, zero quarantined conflicts, and all current-listing,
non-PIT, unadjusted, corporate-action, and session-finality limitations. It
did not call KIS or copy raw rows. The current 07:15-20:45 KST continuation
window left a measured post-rate-limit restart gap. The collector now permits
exactly one same-client, gate-due rate recovery within its existing runtime;
a second rate limit yields back to the existing scheduler. Its source-safe
receipt records only the recovery count, categorical outcome, and aggregate
post-recovery accepted-page count.

After rebuilding the Docker image, one 900-second manual continuation advanced
the cache from generation 187 to 604: 417 chunks accepted 818 pages with zero
new categorical failures. The external receipt is
`sha256:598ef0cd59385024b364b34bb09eaa49310e7ab4a795945288aef5cba6762c70`.
It did not encounter another rate limit, so the new recovery path was not
needed (`attempt_count: 0`); this is sustained-progress evidence, not proof
that an actual KIS rate-limit recovery succeeds. The trigger window, one-second
request-start gate, five-minute fresh-token guard, `IgnoreNew` behavior, and
source scope remain unchanged. The next bounded package materializes a new
byte-stable panel snapshot and checks immutable overlapping lineage before any
research consumer can use the expanded coverage.

That panel continuity package completed offline. The generation-604 panel has
dataset `sha256:2c3b9ddddc7160620210edecdeaef7925ccea33151def62e180eb4f1d0022660`,
manifest `sha256:b0eca31e6bfbfcdec0395837040a8e543d9c83fa3c915f8e651c5cee6deba15e`,
and receipt `sha256:ddc6be570a034090052b79fef9f0070e60e92d99b74efa2ddbc6d1f7c1c0cf7a`.
It preserves 604 covered targets, 1,515 at zero, and zero quarantined targets.
The external continuity receipt
`sha256:6b221366068fa9c1c40e35d707a1475fabbdea384eb4bdb06f66a17945c69c8b`
compared it with the generation-187 panel: 187 shared targets and 35,975 shared
target/session fingerprints, with zero mismatched targets or rows. The code
reattests both frozen panels and writes only aggregate hashes/counts; it opens
neither the collector lock nor any network, credential, account, order, or live
route. Claude CLI attempts returned no review body before their turn limits, so
the review fact is `review_unavailable`. The equal comparison does not qualify
PIT membership, adjustment semantics, corporate actions, session finality, or
model training.

The next independently scheduled continuation then advanced the mutable cache
to generation 853: 853 of 2,119 targets now have coverage, with 1,672 accepted
pages, three cumulative categorical failures, and at most two pages per target.
Its source-safe receipt
`sha256:69ee1bd010c8fab366e94ea9df5686f101af00af9c574c2d2613a8e00d3560b1`
records 251 chunk attempts, 486 accepted pages, and two categorical rate limits.
The bounded same-client recovery ran exactly once and accepted 50 more pages
before the second rate limit yielded to the scheduler. This validates the one-
recovery behavior for that run; it does not establish a provider-wide rate
limit. The frozen generation-604 panel remains immutable and separate from this
new mutable watermark.

At the 2026-07-29 08:23 KST source-safe index snapshot, the independent mutable
collector had advanced to generation 2,468: all 2,119 current NASDAQ targets
had at least one accepted page, for 4,827 accepted pages and 15 categorical
failures. This closes breadth coverage only. It leaves 2,014 targets ready for
further historical continuation; 94 are complete and 11 source-limited for
their exact cursor contracts. It remains neither a frozen panel nor a PIT or
Research-ready universe.

## Overnight/Intraday State CPU Smoke

The newly proposed QQQ/SPY D1 overnight-versus-intraday state rule completed
only a two-slot Docker CPU operational smoke. It reattached the fixed 4,756
session KIS-private pair, used phase-local 21-bar directional-count windows,
and replayed its candidate plus flat, always-long, and previous-bar-direction
comparators through in-memory `local_paper` only. Its source-safe precommit is
`sha256:dc37edf85605ba78171b006f0c35dd27fcb4355442c9d50d5a3d154a462dd5a1`;
the independent network-disabled validator reattached source and artifact
identity with summary `sha256:3fde8e7efd4bbbf78dbe8603d5635036db01b16a5691599994e46b01e030a8ca`.

Claude's falsification-first verdict on the revised non-telescoping rule was
`unsupported`: its target mechanism, adjustment uncertainty, and selection
surface do not justify a performance campaign. The retained result is therefore
strictly CPU plumbing evidence. It is ineligible for a full run, GPU, model
selection, ensemble, KIS Paper action, or order; no performance conclusion is
made from its two slots. The external run directory contains exactly precommit,
summary, and validation receipt JSON files, with no raw rows, event logs, model
weights, credentials, network, broker, or GPU use.

At 07:30 KST the independent broad D1 worker was still running at mutable
generation 1,251: 1,251 of 2,119 targets had coverage, 2,451 pages were
accepted, four categorical failures were recorded, and no target exceeded two
pages. This is a live source-safe watermark, not a frozen panel or research
input.

## QQQ/SPY D1 Forward Cache

The first source-separated QQQ/NAS plus SPY/AMS D1 forward cache is now
implemented under
`D:\market_data\us_equities\kis_paper_private\daily-qqq-spy-forward\v1`.
It accepts only completed daily rows strictly after the 2026-07-24 frozen
boundary and is never merged into the fixed QQQ/SPY history, six-symbol NAS
forward cache, Norgate data, Tiingo data, or mutable broad current-listing
cache. Raw cache bytes remain on D:; receipts remain external under
`D:\thericher-v2\model-artifacts\data\kis-paper-daily-pair-forward-v1`.

The Docker preflight is network-disabled, read-only, and credential-free. Its
`collection_required` receipt is
`sha256:c35d30de11d2d12dddf60ccf43d0738c1474ad88ba2e6c4b8ef8395c5e14ade4`.
The installed `thericher-kis-paper-daily-pair-forward` task runs at 06:55 KST
Tuesday through Saturday, with a 10-minute execution limit and `IgnoreNew`.
It defers through the same credential-free preflight whenever the NAS forward,
broad, or legacy daily collector is running. A manual guarded smoke while the
broad worker was active recorded only
`unavailable/shared_dispatcher_busy`, with receipt
`sha256:227a65afdf8e10f335fa7925ea94d7fe6d1707da927d50899f50e15ef78f86db`.
No credentialed pair collection, account/position/quote/order route, model,
GPU run, Paper action, or live route occurred.

At the 2026-07-29 09:50 KST source-safe broad-cache snapshot, the 09:45 KST
bounded collector run was active at generation 3,649. All 2,119 targets had
coverage, with 7,102 accepted pages, 60 categorical failures, and states
`1,928 ready / 136 complete / 55 source_limited`. Broad depth collection
continues independently; the pair cache's current deferred state is not a
global hold. Claude's requested collector/scheduler drift check timed out
without a review body, so it is recorded as `review_unavailable`.

At the 2026-07-29 22:30 KST terminal source-safe watermark, the 09:45 KST
worker had exited zero at mutable generation 11,130. All 2,119 current NAS
targets retained coverage, with 21,683 accepted pages, 310 cumulative
categorical failures, and states `1,539 ready / 301 complete / 279
source_limited`. The ready target anchors ranged from 2020-03-09 through
2022-03-23. Breadth is complete but longitudinal backfill remains incomplete
and uneven. That worker loaded its runner before the host postprocess/observer
updates, so both postrun roots remained absent after its successful exit; this
is a scoped pre-update-worker fact, not a collector or data failure.

The next fresh 22:45 KST same-task worker owns the first automatic chain. It
uses an eight-hour inner bound, then runs one host-side `uv --offline`
postprocess after a successful Docker collector exit. The postprocess reuses
the two-read panel materializer, compares the candidate to generation 604,
requires full non-quarantined coverage and non-regressing zero-mismatch
overlap, and writes a deterministic source-safe receipt only under
`D:\thericher-v2\model-artifacts`. A scoped `retry` result exits `20` and does
not pause or alter the collector. The exact digest-bound receipt then invokes
the tested offline observer after a complete postprocess; an observer recovery
is warned without changing successful collector/postprocess state. Claude's
rerun gave `supported-with-limits`; its deterministic-receipt and
failure-boundary caveats are implemented. The observer records a
candidate-generation-bound per-target chronology distribution, never a global
common-history/`feasible` decision, so current-listing and source-limited
targets cannot become an accidental Research gate.

The same installed broad task now has one 30-minute Tuesday-Saturday trigger
per `:15`/`:45` slot across 00:15-23:45 KST. It retains `IgnoreNew`, the
870-minute outer limit, the shared cache lock/control root, and the existing
postprocess-after-successful-collector-exit boundary. This is the first
reversible overnight continuity observation, not a new task, concurrent
collector, provider-rate conclusion, KIS account/order call, or live route.
Its installed 11:24 KST baseline is one unchanged active owner at mutable
generation 4,946, 9,618 accepted pages, and 110 target-local categorical
results. More than one owner or two consecutive zero-progress added-slot runs
from the same shared rate/maintenance class restores daytime-only triggers;
one target-local source limit or scoped retry does not.

## KIS Paper Account Readiness

The current `kis-readonly` Docker image completed one bounded virtual-paper
account, position, and open-order read at 2026-07-30 05:11 KST. Its immutable
source-safe evidence is
`D:\thericher-v2\model-artifacts\execution\kis-paper-console-bridge\20260729T201139434674Z-complete.json`
with hash `sha256:104f8e82f56c7bde7a8704c6af5d0e6d93ae5e67f240dbbe7f9c8288e966f8d3`.
It is `paper_only`, has `submit_capability: false`, and exposes only fixed
currency/count category keys. It contains no credential, account identifier,
raw balance, price, position, order, token, or broker body. No intent, canary,
submit, modify, cancel, quote, or live endpoint was called.

The existing bridge already distinguishes a fresh complete snapshot from a
stale/malformed/rejected input. A new focused test additionally proves that a
valid flat account with zero positions and zero open orders is a complete
readiness observation, not `account_unavailable`. The historical QQQ
`account_unavailable` receipt remains scoped to that earlier session path and
does not contradict the present virtual read-only result.

## D1 Source Conformance

The offline Norgate/KIS D1 conformance objective completed under external
receipt `sha256:f57ff5456f1a21d2e110f0a5a0a5e170805cbcdea3b139177a747b7e910d7f60`
and contract `sha256:17a5c6043b410d7019a6a0e02a9d38f5c3f939ebe3fc80f24eb719a10bf26afa`.
It found the same completed-bar OHLCV shape but explicit adjustment and symbol
identity conflicts; corporate-action, timezone, and gap semantics remain
unknown. The receipt has no source rows, values, dates, labels, predictions,
model, PnL, credential, KIS, broker, or network data and is not model-eligible.

Claude rejected a proposed Tiingo six-symbol corporate-action sidecar expansion
as `unsupported`: it exceeded the documented standing token scope, would not
resolve the conformance conflicts, and has a cheaper offline kill test. The
offline audit then reattested the frozen six-symbol KIS D1 panel at contract
`sha256:1a3b295e...6ded2cb` and receipt `sha256:3930a95a...05176e`. All five
fixed AAPL/AMZN/GOOGL/NVDA split pairs were present and classified
`signature_observed`, so the aggregate is narrowly
`consistent_with_declared_unadjusted`. No source values, dates, rows, labels,
requests, credentials, or broker data were retained.

Claude's result review was `supported-with-limits` for that narrow observation,
but `unsupported` for turning it into a retrospective-label exclusion adapter.
The audit does not test dividend adjustments, full-panel restatement, the two
unaudited symbols, or source identity. Its recommended next package is an
offline all-six-symbol complement census of large adjacent-session
discontinuities outside the five fixed pairs. Preserve the current contract's
intentional rule that any missing/invalid required pair yields aggregate
`inconclusive`; do not reinterpret that as a bug or change it while closing the
audit objective.

## KIS D1 Discontinuity Census

The symbol-aware v2 complement census is complete under receipt
`sha256:0f92a3778020bfab20a74405e03f74de580a8a18ab13522d7788b0b4f2b93edb`.
It reattested the same frozen source and found one aggregate unexplained large
discontinuity for AAPL, with zero for AMZN, GOOGL, META, MSFT, and NVDA. It
retains no per-pair record, date, location, price, return, raw row, provider
call, credential, broker event, model, label, or PnL. The category has no
asserted cause and historical D1 remains quarantined.

Claude's follow-up review was `uncertain` about treating the category as a
source defect. It identified an incomplete static split list and corrected
symbol-keyed matching as the local code issue; that fix is in v2. It recommended
against another historical adapter/census now because none has a consumer, and
recommended the already-authorized KIS Paper canary lifecycle instead. The
next objective therefore reattests and observes the existing freshness-gated
QQQ virtual-paper session through its first new lifecycle outcome. It adds no
strategy, historical-data dependency, paper quota, or live route.

## Norgate Date-Indexed Capability

The bounded local Windows Norgate capability probe is complete at
`D:\market_data\us_equities\norgate_trial\daily_capability_probe\probe=20260801T152000Z-norgate-trial-daily-capability-r1`.
Its source-safe receipt is `sha256:8a6433a5...ae1d908d` and its local database
metadata fingerprint is `sha256:bbaae9c0...f3c06f5`. The precommit fixed AAPL
as a current-member case, PLTR as an in-horizon membership-change case, and AAL
as the source-confirmed former-member case. Norgate package `1.0.77` returned
the declared date-indexed membership/listing, unadjusted D1 OHLCV field, and
capital-event-marker aggregates for all three. No raw Norgate row or price was
put in Git, a model artifact, or the receipt.

The result is `qualified_for_offline_research`, not PIT/model/GPU/ranking/PnL/
Paper eligibility. Membership availability time, adjustment semantics, and
capital-event completeness remain `unknown`; the runtime namespace remains
`norgate_trial_daily_offline_research_only`. The pure Engine consumer outline
is complete and carries only completed-bar, next-session, chronological-split,
cost, naive-baseline, and availability-shift kill-test wording.

That separate pilot is now complete at
`D:\market_data\us_equities\norgate_trial\daily_pilot\pilot=20260801T161934Z-norgate-trial-daily-pilot-r2`.
Its manifest `sha256:7c81f09ad34151acb3896ef7f4cf22cadceedfb2992ac9241578a64db54fd264`
links the qualified capability receipt, package `1.0.77`, and unchanged database
metadata fingerprint. It retains raw D1, membership, and listing rows only on
`D:`: AAPL has 10 aligned source dates, PLTR has 8 and one membership transition,
and AAL has 10. The loader creates completed D1 `Bar`s plus a required exact-date
state lookup and rejects static substitution or source-date mismatch. This is
field-alignment plumbing only. The availability/PIT, provider-ticker identity,
adjustment, and corporate-action limits remain explicit; no model, GPU, ranking,
PnL, KIS, broker, or Paper path follows from it.

## Causal Multi-Timeframe Sequence Input

The pure `causal-multitimeframe-sequence-window-v1` Engine contract is complete.
It accepts injected completed `Bar` sequences only for `1m/5m/10m/1h/3h`, with
caller-declared positive lookbacks and one UTC cutoff. It preserves each
timeframe's ordered selected tail and completed-bar end while rejecting
incomplete, future, duplicate, non-contiguous, insufficient, or
symbol/market/timeframe-misaligned input. A valid higher-timeframe tail may
lag the cutoff by less than its own duration; a common close is not required.

It has no data-provider, KIS, credential, network, model, label, target,
artifact, PnL, local-paper, or broker path. It guarantees structural causality
only: Data remains responsible for session segments, resampling, data vintage,
and PIT/finality evidence. A real multi-session consumer must add a
calendar-aware upstream segmenter rather than fill gaps or weaken this contract.

## Current Source Opportunity Eligibility

The pure current-source opportunity adapter is now wired into the local KIS
intraday momentum smoke and a distinct fixed twenty-session v2 consensus replay.
It projects only a caller-supplied candidate using a causal completed-bar-prefix
source contract, symbol/market, completedness, and validity facts; it never
ranks/selects symbols or mints a candidate. The historical v1 external replay
artifact remains immutable. Matching v2 facts reproduce digest
`sha256:8855ec22147b9218fc83ac60eaf3cb17dd2a70b38bc46b7568aec5033ad383d1`;
an ineligible candidate, stale source, source gap, or duplicate yields only an
abstention and no local-paper intent. Future bars cannot alter the decision,
receipt, or bridge. All replay fills remain `source: local_paper`, terminal
flat, and broker-free.

The short Claude drift-check for the preceding current-source adapter timed out,
so that adapter's review state remains `review_unavailable`; it is not a
promotion or execution hold. Its later MIM follow-up is closed with current
source facts in the next section. The MIM derivative is not a paper replication
and its endpoint-scoped input result never alters the completed current-source
adapter, the existing scheduler, or another ready engine package.

## MIM-30 One-Minute Input Qualification

The bounded MIM-30 derivative input qualification is complete as
`input_unavailable` for that exact historical campaign. The source-safe public
source receipt is under
`D:\thericher-v2\model-artifacts\research\mim30-source-receipt-v1\mim30-primary-source-20260802-r1.json`
with hash
`sha256:4d91b03e4a1f688d31a7a67e0595a2493650a2d7abfefb5372774a8c2e186d91`.
The frozen pure contract is
`mim30-spy-long-only-derivative-v1` with hash
`sha256:2ef4d43bc0905c02d6cc95cae9c40c395b560b4d06ac903a09dc001013d5884f`.

The local KIS cache has 20 structurally complete SPY/AMS 1m sessions, 232 below
the fixed 252-session requirement. A fresh Data-owned exact-route probe made
two accepted 120-row requests with one reusable token/client and no categorical
error, but found only a terminal head continuation for one exchange-date
category. The route exposes no first-request historical-date input; `KEYB/NEXT`
is response continuation only. The source-safe probe receipt is
`D:\thericher-v2\model-artifacts\data\kis-paper-minute-capability-probe\20260801T210917385848Z-b061b611439008a3.json`
with payload hash
`sha256:b061b611439008a30dbcba230d950faeecbfb5074dd08bb5edffa580eff20a18`.
This is endpoint-scoped evidence, not a KIS-provider-wide history conclusion.

Claude's falsification-first verdict was `unsupported` for historical MIM
evaluation from this input. Current local-paper semantics also use a
next-completed-bar open entry and terminal 15:59 open exit, not a 16:00
close/auction fill. The contract records that source-window incompatibility
truthfully and cannot turn it into a Paper or profitability claim. No MIM GPU
appointment, model training, paper intent, or broker route follows. The next
company objective is a separately named prospective intraday baseline that can
advance while Data and Execution session workers wait on their own clocks.

## Prospective SPY Regular-Session Baseline

The first prospective SPY baseline is implemented as a pure research contract,
not a profitability result or a Paper action. It accepts only a complete
09:30-16:00 America/New_York session and decides at 15:30 ET from causal
1m/5m/10m/1h/3h selected tails of 30/6/3/2/2. Its fixed rule proposes a 2
percent long target only when every trailing view rises; otherwise it abstains.
It has no provider, network, credential, broker, order, raw-data, or artifact
authority.

Validation now rejects tampered duplicate or missing selected bars before the
baseline can evaluate them. Pure resampling moved to `thericher_v2.market` and
`data.resample` remains a compatibility export, so importing the baseline leaf
does not eagerly load KIS, provider, or execution modules. No prospective
session was captured, no KIS call or order occurred, and no GPU was used.
Claude's static drift review is `supported-with-limits`: it confirms the pure
extraction/import-isolation claim subject to the running runtime suite and
subprocess verification and the tightened tamper test.

Next context: Data should attach one newly observed complete SPY session to a
source-safe prospective observation receipt, then Engine may record the fixed
baseline's categorical proposal. Keep raw market data on D:, retain only
source-safe receipt facts outside Git as needed, and do not make the
orchestrator wait for the market session. A receipt is evidence only; a later
GPU campaign or Paper action needs its own bounded contract.

## Prospective SPY Observation Receipt And Local Replay

The dedicated `prospective-spy-observation-receipt-v1` is complete. It evaluates
the frozen 15:30 ET SPY baseline once per immutable session record and emits
only structural/session timestamps, source and record hashes, baseline/feature
identities, `ready`, and categorical `enter`/`abstain` decision facts. A
SHA-256 content commitment over all selected causal input bars binds the actual
input without retaining raw OHLCV. The receipt excludes prices, account/order/
fill data, paths, credentials, and mutable identifiers.

The injected local replay proves a rising record creates exactly one
`source: local_paper` fill, a rerun does not duplicate it, and abstention creates
no intent or fill. The focused integrated suite has 67 passing tests. No KIS
call, account read, KIS order, live behavior, raw-data persistence, artifact,
GPU use, training, PnL, or profitability claim occurred.

Next: prepare the Data-owned KIS Paper SPY fresh-session capture/receipt runner
for a newly complete 15:30 ET window. It uses market-data reads only, retains
raw bars on `D:`, emits source-safe evidence, and must not make the foreground
orchestrator wait for market time.
