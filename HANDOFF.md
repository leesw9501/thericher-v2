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

## Prospective SPY Fresh-Session Capture Runner

The Data runner is complete at
`scripts/capture_kis_paper_prospective_spy_observation.py` and
`thericher_v2.data.kis_paper_prospective_spy_capture`. It consumes only the
verified local `SPY/AMS/1m` cache, accepts the same America/New_York date only
after the fixed 15:30 ET cutoff, checks all 360 required completed minutes,
then invokes the pure session-record and dedicated receipt factories. It writes
one canonical receipt per session outside Git, under the configured model
artifact root. It never reads `.env`, starts a KIS client, calls a network,
reads account state, constructs an intent, or submits an order.

The source hash is scoped to all selected 09:30-15:30 source bars rather than
the mutable whole cache. A post-cutoff cache append does not alter a retry;
a changed selected minute conflicts with the immutable session receipt. Missing
or stale conditions emit only `not_yet_observed` and create no artifact. The
weekend smoke safely stopped as `regular_session_unavailable` before cache I/O.
The existing head collector remains the only scheduler/cache writer. Claude's
short drift check timed out (`review_unavailable`), so no Claude conclusion is
claimed.

Next Engine package: implement the CPU-only
`tiingo-d1-trend-mean-reversion-rotation-v1` falsification on the already
verified immutable `SPY/QQQ/IWM` Tiingo snapshot
`sha256:b47539a373bf2d625ad2380376808cf412219f6c5d932b66631bb3aa553683cf`.
It is a new trend-conditioned short-horizon mean-reversion portfolio rule, not
a retune of the failed momentum or sequence family. Do not allocate GPU, create
or open a new sealed evaluation, use KIS or credentials, or make a profitability
or Paper-input claim. Correction from Claude's falsification review: the snapshot
has already been used, so do not claim a sealed or independent tail. Use a
repeat-source 70% development / 61-session purge / 30% falsification split,
mask only facts through decision time, require at least 100 active validation
decisions before target evaluation, and compare active benchmarks on the same
candidate dates.

## Tiingo D1 Mean-Reversion Rotation Outcome (2026-08-02)

The bounded CPU-only repeat-source falsification completed with truthful
`input_unavailable`. The immutable three-ETF snapshot reattested to the frozen
dataset hash `sha256:b47539a...553683cf` and manifest hash
`sha256:8b2e375a...c072de`; its source-safe external run is
`20260802T081500Z-r1` with precommit `sha256:665532f2...b3c65137`. The frozen
event mask yielded three active validation decisions, below the required 100,
so no target-day return, result total, kill conclusion, selection, PnL, or
profitability claim was produced. The run made no network, credential, KIS,
account, order, local-paper, broker, GPU, sealed-tail, or live action.

The code now pins the 20-bp kill scenario separately from the 10-bp primary
view, preventing a cost-label mismatch. Focused tests passed. The requested
Claude CLI drift check timed out and is `review_unavailable`, not a conclusion
or a blocker. A later genuinely fresh source tail would need a new frozen
single-use replication contract; do not loosen this campaign's fixed event
mask or minimum-decision preflight.

## SPY Intraday Regime/Micro Consensus Outcome (2026-08-02)

The bounded CPU-only `kis-spy-intraday-regime-micro-consensus-v1` run completed
against the verified local `SPY/AMS` 1m cache with the frozen 21-session
`10 / 1 / 10` split. Its target-free preflight retained 32 validation decisions
above the fixed 30-decision floor. The subsequent aggregate-only evaluation is
truthfully `falsified`: the candidate's 20-bp all-in net total was not positive.
The result is a hypothesis rejection, not realized PnL, model selection,
profitability, Paper-input, or promotion evidence.

The source-safe receipt is outside Git at
`D:\thericher-v2\model-artifacts\research\kis-spy-intraday-regime-micro-consensus-v1\cpu-falsification-20260802-r1`.
It contains source identity, frozen contract, counts, and aggregate outcomes
only. The run made no KIS call, credential/environment read, account, order,
local-paper, broker, GPU, sealed-evaluation, or live action. Do not retune or
promote this exact long-only regime/micro-consensus family from this result; the
next Engine package must freeze an independently motivated hypothesis. Claude
produced no substantive verdict after two bounded attempts
(`review_unavailable`), which is not agreement or a work hold.

Next Engine package: `spy-first30-final30-momentum-v1` is a distinct,
source-local CPU falsification of Gao et al.'s first-half-hour/final-half-hour
SPY premise. The verified 21-session cache supports nine development and ten
validation daily decisions after the required prior-close lookup. Its small
sample makes every result non-promoting. Freeze the 10:00 ET causal sign,
15:30-to-16:00 target, `5/10/20` bps cost band, eight-decision validation
floor, and 20-bp non-positive-total kill before any target access. The
direction-inverted same-timestamp counterpart is comparative evidence only.
Claude's latest short check ended `review_unavailable`, which is not a hold.

## SPY First-30m/Final-30m Momentum Outcome (2026-08-02)

The bounded CPU-only `spy-first30-final30-momentum-v1` run completed on the
same verified local `SPY/AMS` 1m cache. Its causal preflight retained all ten
validation decisions above the fixed eight-decision floor, but the signed
candidate failed its precommitted 20-bp net-total kill test and is truthfully
`falsified`. The direction-inverted counterpart is comparative aggregate
evidence only; neither side is a model choice, profitability claim, PnL,
Paper-input, or promotion result.

The source-safe receipt is outside Git at
`D:\thericher-v2\model-artifacts\research\spy-first30-final30-momentum-v1\cpu-falsification-20260802-r1`.
It contains no raw bars, timestamps, prices, individual returns, credentials,
or broker data. This package made no KIS call, environment/credential read,
account, order, local-paper, broker, GPU, training, or live action. Do not
retune its first-30m/final-30m window, sign, costs, or filters after this
result. Claude's bounded request was `review_unavailable`, not a hold.

Next Engine package: `spy-intraday-mtf-logistic-10m-v1` is a deterministic
CPU-only, development-only L2 logistic baseline over causal completed
`1m/5m/10m/1h/3h` SPY inputs. It has 190 scheduled feature rows in each of the
ten development and ten validation sessions, but the effective validation unit
remains ten session blocks. Freeze `C=0.1`, no class weights, `0.55` long-only
threshold, fixed 10-minute target, 150-row/30-long-decision preflight, and the
20-bp positive-total plus per-executed-event always-long comparison kill. It
uses the existing dependency, is non-promoting, and receives no GPU. The
feasibility receipt is under
`D:\thericher-v2\model-artifacts\engine-research\spy-intraday-mtf-logistic-10m-feasibility-20260802.md`.

## SPY Intraday MTF Logistic Outcome (2026-08-02)

The bounded CPU-only `spy-intraday-mtf-logistic-10m-v1` package completed on
the same verified local `SPY/AMS` 1m cache. Its causal feature preflight
produced all 190 scheduled rows in each development and validation phase, but
the fixed development-only L2 logistic policy at its frozen `0.55` threshold
produced fewer than the required 30 target-free validation long decisions.
It therefore closed truthfully as `input_unavailable` before reading validation
targets or calculating returns, PnL, costs, or a kill result. This is neither a
falsification nor a profitability result.

The aggregate-only external receipt is
`D:\thericher-v2\model-artifacts\research\spy-intraday-mtf-logistic-10m-v1\cpu-baseline-20260802-r2`.
It contains the frozen source/contract, structural counts, model hash, and
categorical outcome only. The run made no KIS, network, credential,
environment, account, order, local-paper, broker, GPU, checkpoint, or live
action. Do not lower this campaign's threshold or minimum-decision floor after
the result; a distinct next package must freeze its own hypothesis and contract.

## Norgate Local D1 ETF Source Outcome (2026-08-02)

The official `norgatedata==1.0.77` client is now isolated in the dedicated
Windows-only `norgate-host` extra; it is absent from the base, `research`, and
Docker runtime dependencies. A real local-NDU materialization produced one
immutable fixed `SPY/QQQ/IWM` D1 source snapshot below `D:\market_data` and a
separate aggregate-only external receipt. Its reattested content has 511 common
completed sessions and 1,533 retained D: rows. The receipt hash is
`sha256:9e7c7561...6b3f5a08`; its source identity is
`sha256:efa1b14f...e15c58e7` with manifest
`sha256:7f30253d...69a33d45`.

This is `qualified_for_offline_research`, not a point-in-time, availability,
adjustment, corporate-action, ranking, model-promotion, Paper-input, PnL, or
live claim. The current raw snapshot's source scope still requires a separate
campaign contract before Engine may train or evaluate a model. No KIS,
credential, account, broker, local-paper, GPU, or live route ran. The original
same-label rerun reattests the immutable snapshot without invoking the Norgate
client again.

## Norgate D1 Trio Momentum Diagnostic Outcome (2026-08-02)

The fixed CPU-only `norgate-d1-trio-momentum-falsification-v1` diagnostic
reattested the existing local source without invoking the Norgate client. Its
frozen `350 / 21 / 140` session geometry produced 138 structurally eligible
validation slots and 59 long-rule decisions. The rule had 33 positive target
signs (`0.559322...`) versus 74 across the always-long comparator's 138 slots
(`0.536231...`), so it closed as `inconclusive_non_promoting`, not as a model,
candidate, performance, PnL, profitability, Paper, or promotion result. The
aggregate-only external receipt is identified by
`sha256:6211339e...7c868149` and contains no retained bars, dates, prices,
labels, decisions, or source paths.

Do not retune the 20-session rule, its strict-positive condition, split, or
comparator against this source. It created no model weights, GPU appointment,
KIS call, credential/environment read, account access, order, broker/local-
paper action, network request, or live route. A later package must be a
distinct frozen hypothesis or a source-stability check; this outcome is not a
reason to upgrade the raw source's availability, PIT, adjustment, corporate-
action, ranking, or Paper status.

## Norgate/KIS D1 Bar Conformance Outcome (2026-08-02)

The offline `norgate-kis-d1-bar-conformance-v1` reattested the fixed Norgate
snapshot and the pinned KIS `SPY/QQQ` private catalog without a KIS client,
credential, network, account, order, broker, local-paper, GPU, or model path.
Across 501 common sessions per symbol, every quiet-stratum field passed the
frozen 95-percent aligned-agreement and shifted-date discrimination tests;
aligned relationship agreement ranged from about 99.6 to 100 percent while
the shifted controls ranged from about 2.0 to 9.4 percent. The source-safe
receipt is `sha256:30914a1c5d0c70f9a5b3bca20cff0242ab8bc1f2bf5291a77512ebcdd6a46f9c`.

Both inputs had zero frozen 20-percent discontinuity events, so every required
event-adjacent stratum was empty and the aggregate result is
`input_unavailable`. This is useful current-vintage quiet-bar evidence only;
it does not establish point-in-time availability, corporate-action correctness,
tradability, source interchangeability, model eligibility, GPU eligibility,
or a Paper consequence. The source-safe receipt contains aggregates and hashes
only. The reviewed implementation uses common-session predecessors, matched
shift anchors, fail-closed noncommon-event projection, and no-clobber external
receipt writes; those plumbing improvements make no source-quality claim.

## KIS D1 Causal Representation Feasibility Outcome (2026-08-02)

`kis-d1-causal-representation-feasibility-v1` completed its bounded offline
Engine Research runtime study from the attested six-symbol KIS D1 development
phase only. The repaired `implementation-r2` contract is
`sha256:1303c4f67694322dc3b9f70418c7e41203ffaab8221e5ba5080f6630e6007a7d`.
Its Docker CPU smoke completed four steps and its single Docker CUDA appointment
completed all 192 fixed steps. Both runs recorded finite training and diagnostic
loss categories; the CUDA terminal-mini-batch decrease flag is false and is not
interpreted as a quality result. The CPU summary is
`sha256:ff7a5e01b5e100618fdb3f09abfc4dc970bfd6ccfb2f42a665407dfaa6931ff5`,
the CUDA summary is
`sha256:ea43ae579732f0f4c585bda98c2685987f6d664f862b698be0a2e7a01dff464e`,
and the CUDA custody outcome is
`sha256:0662586e9a22346326af174866825ab8307f9f11ab4789860b2785bfea56613c`.

Generated `.npz` weights and all receipts remain only under the configured
external artifact root. They are bound to the current campaign hash, rechecked
with `allow_pickle=False`, and an orphaned weight file fails closed. The first
implementation attempt ended at an argument-wiring error before a CPU receipt
or weight artifact; its external recovery receipt is
`sha256:487144d8f657102e5e96cc15d98d19fbfb07821e3864d2398e3e1171f787b879`
and it is closed as `non_promoting_abandoned`.

This proves only a reproducible KIS-shaped causal-TCN representation and GPU
artifact path. It does not produce a forecast, alpha, model selection,
ensemble, PnL/profitability claim, Paper input, KIS call, credential read,
account access, order, broker effect, or live behavior. A proposed distinct
SPY pullback-in-uptrend rule on the unused Norgate D1 segment was challenged by
Claude as `unsupported` for execution: its fixed 98-row window would likely
produce only about six to nine active rows, below the predeclared 30-row floor.
Retain that as a source-coverage requirement, not as a failed rule, next goal,
or wait on independent Engine and Paper work.

## KIS D1 Candle Noise-Floor Outcome (2026-08-02)

The CPU-only `kis-d1-candle-noise-floor-v1` campaign completed against the
same attested six-symbol KIS D1 development source, with contract
`sha256:ef296e312e5a1ddc58ac8884f176a330f928020153ddc2da7496a01379ed08f5`,
summary `sha256:e84540377f7f1985a325d5e730334ed4c3d9a941fcb30a12737e0de3ab70b48e`,
and custody outcome
`sha256:00a5abcd957b67733560dc179a2238cfe0b0dd9a17208e0389c13b4589b99c24`.

It used only 32 causal same-candle OHLC ratios, a frozen 1,000 / 33 / remaining
development split, five fixed-seed L2 logistic fits, and 64 within-symbol
contiguous-block label nulls. The result is `noise_not_separable`: the
actual-label median balanced-accuracy signal did not clear the precommitted
null-margin and seed-spread kill test. The external receipt has structural
counts, hashes, and metric categories only; it retains no raw bars, dates,
features, labels, probabilities, coefficients, numeric metrics, credentials,
or broker data.

No CUDA appointment, LSTM/TCN/Transformer training, checkpoint, sealed
evaluation, KIS/network call, account, order, local-paper, PnL, or live action
occurred. This closes only the proposed encoder-preflight path for this exact
source/split; it does not prohibit a distinct eligible Engine campaign or the
independent KIS Paper lifecycle work.

## KIS Paper ID-less Canary Recovery (2026-08-02)

The virtual-only canary can now recover one exact persisted
`outcome_unknown` intent after a successful submit response omitted its order
reference. A normal recovery binds an order reference only from the current
in-process open-order record when the original response category is a known
successful ID-less category and exactly one open order agrees on symbol,
exchange, side, remaining quantity, and limit price. It persists that private
reference, re-reads the same exact lifecycle, and only then uses the existing
cancellation path. Zero, multiple, contradictory, pre-submit-conflict, and
explicit read-only-recovery cases remain unknown and make no replacement or
cancellation side effect.

Raw order references stay in process memory and never enter safe runtime,
evidence, logs, Git, or artifacts. The bounded limitation is that a later,
unrelated order with the identical five attributes cannot be distinguished
without a separately verified broker-side correlation capability; a future
capability probe may assess that fact, but it does not block this narrow
recovery. Claude reviewed the repair as `supported-with-limits`.

Focused recovery coverage passed 84 tests. The full parallel and serial suites
both passed `2035 passed, 14 skipped`; Ruff and both Compose configurations
also passed. The existing `thericher-kis-paper-daily-spy-session` task was
rebuilt and reinstalled for its next regular schedule without a manual run.
The installer now resolves its default project root after parameter binding so
a normal PowerShell `-File` invocation does not lose that path.

## Norgate Active-Build Revision Probe (2026-08-02)

`norgate-active-build-revision-probe-v1` completed through the Windows-only
`norgatedata==1.0.77` host reader. Two identical active reads per fixed symbol
matched the immutable raw-D1 `SPY/QQQ/IWM` contract: 1,533 reference bars,
1,533 active bars, and zero bar-level divergences. The source-safe external
receipt is `sha256:aa3989e4246a21db6d45f5e85605f896ac0550ee5f6e8f535ee47b328a510bc7`;
its active response commitment is
`sha256:960bf9eb5ae10f2459456ea87fcd22d0b03ba5495b338433670558ece362773f`.
Provider-free reattachment confirmed the one-file receipt and redaction.

This is a present local-build reproducibility fact only. It does not establish
PIT availability, historical revision policy, corporate-action or adjustment
correctness, tradability, ranking, profitability, Paper eligibility, or a GPU
appointment. The next distinct Engine package may freeze one source-local CPU
baseline contract; it must retain those limitations rather than treating this
probe as source promotion.

The existing trio diagnostic receipt writer now reconstructs and validates the
exact base result immediately before persistence, so a mutated object or an
overridden subclass projection cannot forge a receipt. The combined active
probe, diagnostic, and scheduler-contract focused suite passed 33 tests. Full
serial regression passed `2047 passed, 14 skipped` in 17:47; the independent
eight-worker run passed the same count in 3:01. Ruff and both Compose
configurations passed.

The clean-root variant of the parallel helper is temporarily unable to start
because two recent helper-owned roots remain from interrupted tool executions.
They were not manually deleted or repurposed; the helper's default fresh-root
run passed. This is a test-hygiene recovery fact only, not an Engine, Data, or
Execution hold.

## Norgate D1 Intraday-Structure GBT Preflight (2026-08-02)

`norgate-d1-trio-intraday-structure-gbt-preflight-v1` completed CPU-only after
provider-free reattachment of the matching active-build receipt and fixed
source hashes. The frozen contract is
`sha256:ef3d6406a2aee63eacdb3c9abf6ea29e4df9bd24598dfbaa741326b5467c1bd0`;
the external source-safe receipt is
`sha256:ad4cb0f0050bb3d46236845e4ad51d6243cb14dd7310c54d1846b876fb419570`.

The result is `noise_not_separable` with reason
`effect_and_null_threshold_not_met`. Its fixed 1/5/10/20-session same-candle
ratio features and next-session within-candle label were multiplier-invariant,
but 139 validation date groups did not clear either the precommitted 0.08
balanced-accuracy advantage or the 64-shift date-block null threshold. The
one-session shifted-label control was below chance, so it did not indicate an
alignment fault. No raw bars, dates, labels, predictions, weights, network,
credentials, KIS, account, broker, local-paper, PnL, GPU, or live behavior was
used. Claude was not re-invoked because the strong-result condition did not
occur.

The existing no-network Docker `research` service reproduced the identical
source-safe receipt using `/app/market_data` and `/app/model_artifacts`. The
container invoked only the CPU sklearn path; it did not invoke Torch or CUDA
code and wrote no weights. Runner tests now pin both the host receipt-parent
root and the container market-data-root mapping.

Do not retune this exact feature set, split, classifier, or thresholds. The
next Engine direction needs independently reattested breadth or a distinct
causal hypothesis; the closed three-ETF preflight is not a generic ban on
research, Data work, Paper execution learning, or future GPU candidates.

## Norgate Broad Active-Build Conformance Taxonomy (2026-08-02)

`norgate-broad-d1-active-build-conformance-taxonomy-v1` completed on the
Windows-local `norgatedata==1.0.77` path in under 30 seconds. The hash-attested
523-symbol / 483-common-session broad D1 panel has 252,609 reference and
active bars. Both active reads per symbol were repeatable: 523 exact matches,
zero shared-session value mismatches, absent symbols, coverage mismatches,
malformed responses, and nonrepeatable responses. The source-safe receipt is
`sha256:235af9ebdef1f61081314edc71f1bc0d2de9f266e1ed2e7d265294a1e853cf7a`
under `D:\thericher-v2\model-artifacts\data\norgate-broad-d1-active-build-conformance-v1\active-build-taxonomy-20260802-r2`;
its canonical active-response hash is
`sha256:f949b05fa2124d87f5b44b16cdb66130d9d115f4e74a958b8cb0a1e1883443c0`.

Claude's `supported-with-limits` review correctly replaced the naive broad
one-count revision test with a predeclared taxonomy: only shared-session value
mismatch can yield `revision_detected`; absent symbols, session coverage,
reader nonrepeatability, or malformed responses yield `input_unavailable`.
The receipt holds only per-symbol categories/counts and hashes, no raw data,
dates, paths, exception text, credentials, models, PnL, GPU, Paper, or live
behavior. This is a frozen current-build reproducibility fact, not proof of
PIT, adjustment/corporate-action, availability, membership, model, ranking,
Paper, or GPU eligibility.

The r2 receipt pins the reference manifest before reads, preserves prior
per-symbol evidence if a later provider failure occurs, and accepts an
`expected_receipt_sha256` for provider-free consumers. A future consumer must
pin this receipt hash in its own frozen contract; receipt self-consistency alone
is not a source-authentication claim.

## Injected Multi-Timeframe Local-Paper Replay Seam (2026-08-02)

The bounded `injected-multitimeframe-local-paper-replay-seam-v1` integration
now takes caller-injected, deterministic completed `1m/5m/10m/1h/3h` bars
through the existing causal-window builder, existing momentum predictions,
target-position policy, immutable research receipt, local-paper intent bridge,
next-bar fill/replay, and the existing next-bar timing harness. Its focused
suite traversed every named existing path twice against independent temporary
stores, then retried against the same store. It confirmed a deterministic
eligible proposal, receipt-to-intent identity, `source: local_paper` fill,
exact fill replay, and next-bar timing. Backtest geometry and whole-1m
continuity are now validated before the first local-paper event; a short or
invalid timing sequence leaves no accepted, fill, or snapshot event behind.

The helper has no provider/cache, credential, network, KIS, account, external
broker route, model training, artifact, or GPU dependency. It returns only categorical
and opaque-reference facts; it does not return raw bars, timestamps, prices,
paths, account state, PnL, a predictive model-quality result, a ranking, an
ensemble, a KIS Paper decision, or an order. Claude's falsification-first
verdict was `supported-with-limits`: it approved only this existing-path seam
and rejected a duplicate score/decision/intent framework. Independent review
also required same-store fill recovery and pre-side-effect timing validation;
both are now covered by focused tests.

Focused seam/adjacent coverage passed `39` tests. The final fresh-root parallel
and full serial suites both passed `2082 passed, 14 skipped`; Ruff and both
Compose configurations passed. The clean-root helper remains correctly
fail-closed only because of two prior interrupted helper roots, which were not
deleted or bypassed.

The next trained-model consumer still requires a separately frozen,
source-qualified causal campaign with an independent temporal evaluation
surface. The promising distinct CPU candidate is a KIS-shaped six-symbol D1
volume-exhaustion reversal falsification; it needs its own Claude challenge,
precommitted target/cost/null contract, and cannot use this seam as a
performance or Paper promotion shortcut.

## KIS NAS D1 Volume-Exhaustion Falsification (2026-08-02)

The fixed `kis-nas-d1-volume-exhaustion-reversal-v1` CPU-only r4 attempt is
complete and `falsified`. Its external contract and summary live under
`D:\thericher-v2\model-artifacts\research\kis-nas-d1-volume-exhaustion-reversal-v1\cpu-falsification-r4`
with contract `sha256:ffe46f6a81e0e44e736db69fefcc7809a33b1e8eef9d1cc66aacb1a05d5f2e9d`,
summary `sha256:0fd63b26eaf6680825c13a02bb5fae4b642af0ef121a156e815d0e92e5f87eb4`,
and custody outcome `sha256:e2d3a129530315a3d2fa6a450d900b16bf97268fd5b96d7bc86d54099b65123c`.

It consumed only the attested six-symbol NAS D1 development phase. A
target-free 5,880-slot census found 107 structural signals across six symbols;
the frozen 22-session purge left a 2,802-slot one-shot falsification. At the
fixed 10/15/20bp band, the candidate was nonpositive versus flat at 20bp and
did not strictly exceed either candle-only or the 64 within-symbol 10-session
block-null P95. No raw OHLCV, dates, targets, numeric performance values,
predictions, credentials, account data, or checkpoints were persisted.

This is a closed source-local rule family, not a model, PnL/profitability,
GPU, ensemble, Paper, KIS, or live result. Do not retune or reuse it. The
earlier r1-r3 artifacts are retained only as non-promoting recovery evidence:
review successively fixed an Execution import route, leaf-only code custody,
abstention and child-symlink handling, Git-root creation before rejection, and
an artifact-root symlink route. The final r4 contract hashes all campaign code
dependencies and rejects Git-resident or symlink-traversing artifact roots
before creation. The direct Research leaf import is lazy/execution-free while
legacy public imports remain compatible. Claude's bounded architecture challenge
timed out (`review_unavailable`), so focused independent review and tests, not
a Claude verdict, support the final implementation.

## Tiingo D1 Compression-Continuation Falsification (2026-08-02)

The fixed
`tiingo-d1-trio-intraday-compression-continuation-falsification-v1` CPU-only
repeat-source r2 attempt is complete and `falsified`. Its external contract and
summary are under
`D:\thericher-v2\model-artifacts\research\tiingo-d1-trio-intraday-compression-continuation-falsification-v1\cpu-falsification-r2`,
with contract
`sha256:2b7be8338f99399d7c1af6c9710d9634fb6e2dc74eb428ccdefea9c649743c7b`,
summary
`sha256:d1964e6b40cff6691eafd6c8300f140d8727c300bd8d2d6a535f44595ed3a39d`,
and custody outcome
`sha256:da53555be430ff632c39a16763b7745288e438fae3a97ab60a3e4ac225ebc085`.

It reattached only the immutable local Tiingo SPY/QQQ/IWM snapshot: 6,583
common sessions, 4,608 target-free development sessions, a 61-session purge,
and 1,914 validation sessions. The frozen causal census found 702 qualifying
symbol signals across all three ETFs; 214 candidate-active days and 316 active
positions then entered the one fixed evaluation. At 10/15/20bp, the candidate
did not strictly exceed same-date equal exposure or the 64 joint 10-session
block-null P95, and its 20bp relation to flat was nonpositive.

This is a closed, repeat-source rule-family rejection, not a profitability,
PnL, model, ensemble, GPU, Paper, KIS, or live result. Do not retune the
thresholds, split, target, comparator, cost band, or null. The first r1 receipt
is recovery-only because review found repeated target reopening and incomplete
summary custody. The final r2 reattaches an exact allowlisted summary before
any evaluation, records target-free preflights as `holdout_access=none`, and
hashes the Data package initializer as part of the campaign revision. Claude's
bounded contract and import-boundary requests both timed out as
`review_unavailable`; independent review and focused tests supplied the final
correction evidence.

## KIS Intraday Multi-Timeframe Availability (2026-08-02)

`kis-intraday-mtf-availability-receipt-v1` is complete and
`qualified_for_prospective_input`. Its immutable external precommit and
summary are under
`D:\thericher-v2\model-artifacts\data\kis-intraday-mtf-availability-receipt-v1\local-cache-20260802-r2`,
with contract `sha256:31c301bd2e8c4c7a3bcc837aa07ab594ac044e2bc1aace9f827068b2a5421d53`,
precommit `sha256:5a13c89123f8898ca10b554798c2981feed2afe8a9d41a37cf0445a1305e5307`,
and summary `sha256:2b02ff48092b13a8d09ea19040434db2317a5ef212f96df69bc5475b8028d512`.

It reattached only the verified local `QQQ/NAS/1m` and `SPY/AMS/1m` KIS caches.
Both have 21 common regular-session 09:30-15:30 ET causal prefixes, and every
one reconstructs the fixed `1m/5m/10m/1h/3h` tails of `30/6/3/2/2`. The
receipt retains source identities, geometry, counts, categories, and hashes
only; no rows, dates, OHLCV, targets, returns, predictions, PnL, KIS call,
credentials, broker action, model, GPU, or checkpoint were used or persisted.

This proves the prospective input shape, not a historical evaluation surface:
21 session blocks are insufficient for a new independent train/validation
campaign. Engine's next evidence path is a source-safe, forward-only QQQ/SPY
pair observation sequence that excludes these 21 sessions; it can then freeze
a distinct campaign after 30 fresh aligned records. Claude's bounded structural
request returned no final verdict, so it is recorded as `review_unavailable`.

## QQQ/SPY MTF Prospective Observer

The current data-only `kis-qqq-spy-mtf-prospective-observation-v1` path is
implemented through the existing intraday-head chain. After its owned
collector, the credential-free pair observer consumes only local QQQ/NAS and
SPY/AMS cache prefixes and writes source-safe immutable records below
`D:\thericher-v2\model-artifacts\data\kis-qqq-spy-mtf-prospective-observation-v1`.
The initial offline/no-op verification created no fresh KIS observation, so the
forward primary-record count is `0`; the 21 historical availability sessions
remain explicitly excluded.

The current schedule is data-only: its legacy QQQ Paper/local-paper stages are
`not_applicable` for this frozen objective. `not_observed` is a valid sealed
zero/one-leg attempt; an unavailable verified input or busy append lock instead
produces a terminal recovery receipt so an eligible session cannot disappear as
a false success. Claude's drift check was `supported-with-limits`. This is not
a model, target, PnL, GPU, Paper, or live claim. Engine preparation continues
independently while the Data-owned future-session worker accumulates records.

## Causal MTF Prediction-Window Binding

`causal-mtf-prediction-window-binding-v1` is complete as a pure Engine
contract extension. `propose_target_exposure` now accepts an optional existing
`CausalMultiTimeframeSequenceWindow`; when supplied, it rebuilds the selected
completed-bar windows through the existing causal validator and requires every
prediction's `feature_window_end` to equal that timeframe's actual final bar
end. It also checks the identity reconstructed from the contained bars, so a
QQQ header cannot hide an internally consistent SPY window. A forged H1 cutoff
stamp, header/bar identity mismatch, or future bar becomes a categorical
abstain rather than an apparently fresh expert vote. The existing injected MTF
consumer that already owns a causal window now supplies it to the policy.

The injected CPU-only compatibility smoke confirmed the existing momentum
producer aligns all five timeframes with its causal windows. Claude's verdict
was `supported-with-limits`: do not add another evidence bundle or duplicate
freshness/missing/future checks, and do not bind source or feature-schema IDs
through untyped mutable prediction metadata. No provider, data cache, target,
return, PnL, training, GPU, artifact, Paper/local-paper, broker, or live route
was opened. The QQQ/SPY observer remains at `0` forward records and continues
independently; it is not a foreground wait.

## Causal MTF Momentum Expert Adapter (2026-08-01)

`causal-mtf-momentum-expert-adapter-v1` is complete as the smallest existing
momentum-model extension. The new direct input function consumes one existing
`CausalMultiTimeframeSequenceWindow`, rebuilds its selected bars through the
existing causal validator, and creates the existing
`MultiTimeframeMomentumEvidence` with exactly each expert's `lookback + 1`
trailing bars. It does not resample, widen a lookback, add a wrapper, or use
prediction metadata for source identity.

The raw completed-1m producer and the direct-window path produced identical
five-expert evidence in a CPU smoke and passed unchanged through the existing
causal-window-bound policy. Matching QQQ headers with internally foreign H1,
3h, or fully SPY bars, plus future, incomplete, non-contiguous, and
insufficient windows, all fail closed with empty predictions. The bounded
Claude CLI call timed out and is `review_unavailable`, not agreement or a
hold; an independent Review role confirmed the narrow API and strongest
identity-forgery test. Focused coverage passed `25` tests.

Goal-boundary verification then passed `2153 passed, 16 skipped` in a fresh
parallel temp root and again in full serial mode. Ruff and both credential-free
base/research Compose configurations passed. The clean-root authority mode
remains correctly blocked only by its two preserved recent interrupted roots.

No provider, credentials, source cache, target, return, PnL, model training,
GPU, artifact, Paper/local-paper, broker, or live route was opened. The
QQQ/SPY observer remains at `0` forward records under its independent Data
schedule and does not delay the next Engine package.

## Causal MTF Consensus Replay Input Integration (2026-08-01)

`causal-mtf-consensus-replay-input-integration-v1` is complete as a
no-behavior-change integrity integration. The frozen consensus replay retains
the existing raw completed-1m momentum builder as an unready compatibility
preflight. Only when that evidence is ready does it rebuild one canonical
`1m/5m/10m/1h/3h` causal window from the same `end_ts <= as_of` prefix and
frozen `lookback + 1` geometry, generate the direct-window evidence, require
exact equality with the preflight evidence, and pass that same window to the
existing target-position policy.

A ready/direct disagreement or causal reconstruction failure raises before the
policy can receive unbound predictions. An unready source does not construct an
adapter window and passes `None` to the policy. Focused spies prove the adapter
and policy receive the same object; post-cutoff raw price changes preserve the
bound decision/window; a missing in-prefix bar calls no adapter; and the
existing 20-session fixture retains its fixed
`sha256:8855ec22147b9218fc83ac60eaf3cb17dd2a70b38bc46b7568aec5033ad383d1`
digest and typed outcome. Focused coverage passed `36` tests, including the
CPU-only no-network integration smoke.

Goal-boundary verification then passed `2157 passed, 16 skipped` in a fresh
parallel temp root and again in full serial mode. Ruff and both credential-free
base/research Compose configurations passed. The clean-root authority mode
remains correctly blocked only by its two preserved recent interrupted roots.

The Claude CLI call timed out and is `review_unavailable`, not agreement or a
hold. The temporary independent Review role found no blocking semantic mismatch
and confirmed the completed-prefix, canonical-order, `lookback + 1`, and
no-fallback constraints. No provider, credential, account, order, new
local-paper action, data change, target, return, PnL, model, training, GPU,
artifact, or live behavior was created. The QQQ/SPY observer remains a
separate 0-record Data schedule, not a foreground wait.

## KIS NAS D1 HMM Source-Local Preflight (2026-08-02)

`kis-nas-d1-intraday-regime-hmm-preflight-v1` completed as
`source_local_non_promoting`. It reattached the immutable six-symbol NAS D1
panel and used only development-source indices `0..999`: per-symbol HMM
parameters and the long-state map use `0..599` only; `600..621` is a boundary
buffer whose `602..621` bars warm an already-frozen forward filter; a completed
bar at decision `t=622..998` predicts only bar `t+1` open-to-close after costs.
The screen clears its fixed pooled all-long and 1,000 joint ten-session-block
null relations at 10/15/20bp and survives the 15 percent extreme control.

The external source-safe contract and summary are under
`D:\thericher-v2\model-artifacts\research\kis-nas-d1-intraday-regime-hmm-preflight-v1\cpu-preflight-r1`
with contract `sha256:a98f89dba03cb6970d9a59bd33f923e31f401aa698e9992c75758e049304d1bd`
and summary `sha256:b70a2bcff4e846656309fa3ff6094a5b80db69ba48def308b626fb5049efd6f1`.
Claude returned `supported-with-limits`: this is only "not yet falsified
locally," not edge evidence. It has no PIT/current-membership, adjustment,
corporate-action, turnover, independent-date, sealed-holdout, PnL, Paper,
ensemble, GPU, or live claim. The next distinct contract must test stability
without selecting a configuration from this screen.

## KIS NAS D1 HMM Persistence Closure (2026-08-03)

The committed preflight code was later run once as
`kis-nas-d1-intraday-regime-hmm-persistence-v1`. Its precommit was written
before loading the local panel and exposed only fit bars `0..599` plus later
tail bars `1000..1509`; original screen bars `600..999` were not retained by
the input object. The tail used `1000..1019` only for completed-bar filter
warmup and made `1020..1508 -> 1021..1509` next-session decisions.

The fixed persistence check is `persistence_falsified`: its source-safe screen
relations are at or below the all-long and joint-null comparators across the
predeclared `10/15/20`bp band, and the per-symbol primary relation fails its
nonnegative guard. Preserve the family closed; do not retune, retrain, use
GPU, form an ensemble, or create a Paper input from either HMM receipt. The
external precommit, contract, and summary are at
`D:\thericher-v2\model-artifacts\research\kis-nas-d1-intraday-regime-hmm-persistence-v1\cpu-persistence-r1`
with precommit `sha256:8c0230ab77a2dd6d5b9686cca19224012a03f6d6d6511539df49e906460b4ce1`,
contract `sha256:187d72bc5c91e1a24bbf80ff598219386407dd43c89f4850f4493d258ecb5331`,
and summary `sha256:f226557a1cb5a1881550eba417525bc117b6e9615939bcf776bddf9d0243f600`.
Claude's design verdict was `uncertain`: this was honestly a frozen-fit
persistence check, not independent replication, and its falsification closes
only that family.

## Source And Window Contract Preparation (2026-08-02)

`source-and-window-contract-preparation-v1` completed two independent,
non-promoting packages. Data reattested the existing external Norgate Current
& Past membership snapshot twice with the same source identity and wrote only a
source-safe receipt under `D:\thericher-v2\model-artifacts`. Its receipt is
`sha256:a61a45322b089e94f7cbbf1fe86aac76d20dbdc799e38d4cfa079c63cd9bc95f`;
the unchanged source identity is
`sha256:6a574eb30a1f00e57c126fc8a6ca21e71455911c2f97fdaf4a0c6d074a644d2d`.
It records only aggregate 541-candidate / 266,647-row scope and the sparse
2024-07-18 through 2026-07-17 range, never a source row, symbol, path, or
credential. All direct-historical-universe, publication-time, PIT, campaign,
model, ranking, and sealed-holdout flags remain false.

Engine Research froze the six-cell causal `1m/5m/10m/1h/3h` catalog at
`sha256:ba7d1aeffdadad340d87667c7bfc4b16b1d2ce25632f330b597a0e2437e499e0`
and registered the catalog-only receipt
`sha256:891b8fb3b29571be9de68c1df9d6b14f133eb3417277320c4557dbae5899fc19`.
All six profiles pass the synthetic completed-bar feasibility smoke. The
registration selects neither a profile nor a campaign. A future campaign must
define its own one-profile selection custody in its frozen contract before
opening data or evaluation; no selection mechanism is created by this catalog
leaf. No dataset, target, label, return, GPU, Paper, broker, PnL, or live path
was used.

Claude's post-implementation verdict was `supported-with-limits`: the Norgate
snapshot remains current-and-past survivorship/backfill evidence, not as-of
universe truth, and the catalog's multiplicity must remain bounded by the
per-campaign immutable selection record. Neither limitation is an approval hold
on unrelated work.

## KIS MTF Profiled Feature-Input Preflight (2026-08-03)

`kis-mtf-profiled-feature-input-preflight-v1` reattached the two verified local
KIS minute catalogs and built all six frozen causal `1m/5m/10m/1h/3h` profiles
at the fixed 15:30 ET cutoff. Its aggregate-only result is
`feature_inputs_ready`: 21 common sessions and 126 aligned profile-pair inputs.
The external precommit is
`sha256:25e8ac3aa820ec6c33eb70427765c36c7c05c6cd67140e5f4408415f0b510c4c`,
the contract is
`sha256:25ed7202b60b2ac992e46aaca8d423875fee06f54a14e53bbf0fd8ad6280adbb`,
and the source-safe summary is
`sha256:ad00069df6c3da2874eca7070c08c07126b56699db0c4cec91a2f30718a8168e`.

Each selected `1h` and `3h` bar is reconstructed from exactly 60 or 180
contiguous completed minute constituents and must exactly match their full
OHLCV/volume aggregate. Post-cutoff and next-target-shaped minutes cannot alter
the in-memory projection/digest, while a legitimate pre-cutoff constituent
change changes it and a forged slow bar fails. The persisted receipt has only
hashes, profile identifiers, and aggregate readiness: it has no symbols,
dates, paths, OHLCV, feature values, targets, labels, credentials, or broker
state. This is an input boundary only, not a model, profile selection, target,
return, PnL, GPU, Paper, or live result.

## KIS MTF Profiled Prospective Observer (2026-08-03)

kis-mtf-profiled-prospective-observer-v1 now provides the forward-only
counterpart to the completed 21-session preflight. It leaves the installed
legacy observer and its scheduler-owned date/symbol-bearing store untouched:
the new leaf has its own small external hash-only commitment store because its
receipt must not retain symbols, dates, cache paths, timestamps, or OHLCV.

For one eligible future 15:30 ET session, it reattests both verified local
historical and head catalogs, excludes the exact historical 21-session set in
memory, and evaluates every frozen profile through the shared normalized
projection. Both legs must share the causal-prefix source contract, profile,
cutoff, feature timestamp, and completed-bar status. The saved commitment has
only opaque identities, six profile identifiers, per-profile categorical
readiness, and scope flags. An exact retry is duplicate; different sealed
content for the same opaque session key is an immutable conflict.

The head source identity is derived from the completed 09:30-15:30 prefix,
not the mutable whole head-cache hash. Therefore post-cutoff or
next-target-shaped data cannot alter a sealed result, while an altered
pre-cutoff constituent either fails the exact 60/180-minute reconstruction or
changes the opaque commitment after legitimate resampling. The current actual
head cache has no common ready prospective session, so no real forward
observation or model/GPU/Paper consequence exists yet. Claude's design check
was supported-with-limits; its decisive conditions are the historical
exclusion, prefix-only identity, and source-safe persistence tests.

Post-review hardening now reattests the exact frozen preflight source contract
and receipt rather than accepting an arbitrary 21-session fixture as equivalent
history. The observer's import boundary is also verified in a clean subprocess:
the data-only core and its resolved type hints do not import an Execution,
provider, credential, broker, local-paper, or live route. Exact canonical
payload equality is required for a duplicate retry; unreadable, noncanonical,
or conflicting stored content cannot be mistaken for success. Focused coverage
passed `44 passed, 3 skipped`; a fresh-root full parallel run passed `2219
passed, 20 skipped`, and the diagnostic full serial run matched it. Ruff and
both credential-free Compose configurations passed. This completion creates no
fresh observation, target, model, GPU job, local-paper event, Paper action, or
live behavior.

## Fresh Prospective SPY Paper Adapter

`fresh-paper-baseline-loop-v1` closes the code-level gap between the fixed
15:30 ET SPY `1m/5m/10m/1h/3h` observation receipt and the existing
deterministic KIS virtual-paper canary. Data now revalidates only the exact
canonical external receipt; Engine turns its full immutable identity into a
pure `ResearchDecisionReceipt`; Execution uses one SPY-specific adapter rather
than altering the distinct daily SPY path or adding a generic route/schedule.
Missing, malformed, stale, or abstaining receipt evidence returns no-intent
before configuration, account, quote, or canary activity. Broker-free replay
remains separately labeled `source: local_paper`; this adapter emits only
`kis_paper` route evidence.

Claude's falsification-first verdict is `uncertain`: before a named activation
can rely on this adapter, independently reattest import-time credential
isolation, timestamp-derived freshness, and route-discriminated durable
identity. Focused adapter/legacy regression coverage passed `126` tests and
Ruff passed; the full serial suite genuinely timed out at its 12-minute cap,
and the clean-root parallel helper failed closed on three recent roots. Both
Compose configurations passed. The existing `kis-readonly` container completed
one current virtual account health observation on 2026-08-02 UTC with a
complete snapshot and no order route. No fresh intraday receipt was
manufactured and no new virtual canary was submitted by this objective.

## Prospective SPY Paper Safety Reattestation

`prospective-spy-paper-safety-reattest-v1` is complete. The adapter now treats
`valid_until` as an exclusive execution boundary: a receipt is current only
when `decided_at <= now < valid_until`. This matches the canary decision's
positive-validity requirement and prevents an exact-expiry receipt from
reading Paper configuration, account facts, or a quote only to fail later.

Focused subprocess coverage imports the adapter while denying sockets,
`urlopen`, `.env` reads, and KIS secret environment keys. Missing, malformed,
stale, and abstaining receipt paths deny configuration, client, account, quote,
and canary access. A sequenced clock proves a receipt that expires during
preparation never reaches the canary. The test suite also reattests distinct
receipt-derived state identities for the intraday SPY and daily SPY D1 paths,
and rejects a live host before an injected canary transport can run.

No KIS request, credential read, account/quote read, intent, order,
cancellation, reconciliation, local fill, cache write, or artifact run
occurred. The new focused group passed `15 passed, 1 skipped`; relevant legacy
coverage passed `109 passed`; Ruff and both credential-free Compose
configurations passed. Claude's bounded review timed out, so the record is
`review_unavailable`, not a verdict. This does not hold independent Engine
work.

## Profiled MTF Flattened Control

`profiled-mtf-flattened-control-v1` is a small, pure MLP-style view over the
existing `NormalizedCompletedBarProjection`. It retains the projection instead
of copying its provenance and publishes canonical `1m/5m/10m/1h/3h` block
offsets, lengths, window ends, anchor policy, flattened values, and a digest
bound to the projection digest. It revalidates causal geometry through the
existing sequence-window contract and is deliberately not an independent
raw-value provenance calculation.

Claude's result was `supported-with-limits`: no LSTM, causal-TCN, or attention
adapter was added because the five timeframe sequences are ragged and their
alignment/masking must be selected in a future frozen campaign. Focused control
coverage passed `21 passed, 1 skipped`; related causal/MTF regression coverage
passed `33 passed, 2 skipped`; restored clean-root parallel authority passed
`2245 passed, 21 skipped`; targeted Ruff and both credential-free Compose
configurations passed. No cache, credential, network, model, GPU, artifact,
Paper, or broker route was touched.

The test helper now uses one shared active `C:\trpy\runs` root for ordinary and
authority runs, with parent/child non-link checks and the prior 24-hour
fail-closed recovery retained. The direct legacy roots were not moved or
deleted. Claude's review was `supported-with-limits`; the shared root preserves
current fast-lane visibility rather than silently bypassing it.

## Profiled MTF Runtime And Campaign Readiness

`profiled-mtf-runtime-and-campaign-readiness-v1` is complete. The narrow
runtime module consumes only existing `ProfiledMtfFlattenedControl` values and
fixes the `short` profile's canonical 42-control by 50-feature in-memory batch.
It validates the static five-timeframe layout, unique control identities,
external artifact containment, CPU-before-CUDA order, and categorical
CUDA-unavailable containment. It imports neither Torch nor Execution until a
runtime call is made.

The final external-only `local-cache-r4` contract is
`sha256:a143947894ca84d536577366e6091dd6f61869290a5babe0f133e6557d53f061`.
The CPU receipt completed eight fixed steps, then the Docker research image
used the RTX 4090 for one sixteen-step CUDA receipt. The paired original and
column-permuted CPU runs are runtime plumbing evidence only: 42 controls are
not enough to treat scalar losses as feature structure, learning, selection,
or PnL evidence. No raw rows, feature values, labels, predictions, weights,
checkpoints, cache mutation, KIS call, credential read, broker route, Paper
action, or live behavior occurred.

The local source inventory remains 21 aligned QQQ/SPY 15:30 ET causal input
prefixes with `predictive_target_ready_pair_count: 0`. The next exact
dependency is a forward-only QQQ/SPY 15:30 input commitment paired with each
leg's completed 15:45 ET outcome window. The initial predictive contract is
predeclared but not executable: `short` profile, per-leg 15-minute log-return,
30 target-ready pairs, `20/2/8` temporal split, 20bp round-trip sensitivity,
no-trade baseline, blocked-session target-permutation kill test, CPU receipt,
and a maximum ten-minute GPU appointment. No label has been opened.

Focused relevant tests passed `31 passed, 1 skipped`; clean-root full parallel
will be rerun after the final receipt-safety fixes. Ruff and both credential-free
Compose configurations passed. The next goal is the narrow delayed-outcome
witness that makes those forward pair commitments recoverable without exposing
market values in artifacts.

## Profiled MTF Forward Outcome Witness (2026-08-01)

`profiled-mtf-forward-outcome-witness-v1` is now a separate immutable outcome
namespace beside the existing forward input observer. It accepts only the
already persisted `short` 15:30 ET causal input, rederives that same prefix
from the current local head cache, and requires an exact complete M1 window
with bar starts `15:30` through `15:44` ET. At `15:45` ET or later, it binds
the opaque per-leg content commitments to the prior input witness. It computes
no return, target label, model result, PnL, or Paper decision.

Only a `target_ready` result writes anything: the exact two input prefixes and
two 15-bar outcome windows are first stored as one canonical immutable raw
snapshot below `D:\market_data`; the external artifact then receives only the
snapshot hash, opaque session/input identities, status, and content hashes.
Missing input/outcomes create no terminal artifact so later collection can
recover. Changed input yields `input_mutated`; changed outcome yields a
separate immutable conflict without overwriting the earlier witness. Exact
retries are duplicates and inventory exposes only a target-ready count plus an
opaque manifest identity.

The host runner is credential-, network-, account-, order-, and live-free. Its
2026-08-01 closed-market run returned `outside_outcome_window` with
`target_ready_pair_count: 0`; no raw snapshot or target was opened. Focused
coverage currently passes `13 passed, 2 skipped`. Two final Claude CLI review
attempts timed out, so this record is `review_unavailable`, not a substantive
verdict or a hold on independent work.

## Profiled MTF Ragged Sequence Runtime (2026-08-01)

`profiled-mtf-ragged-sequence-runtime-v1` is complete. It reattests the same
local QQQ/SPY `short` runtime source in memory and converts each control into
five native ordered sequences of lengths `15/3/3/2/2`, width two, with explicit
availability masks. It does not row-align timeframes: attention receives only
timeframe and within-frame causal-rank identities. The three target-free
structural consumers are per-timeframe recurrent, causal TCN, and masked
cross-timeframe attention.

The external-only `local-cache-r1` contract is
`sha256:0a235d0c4922c4891221e81773254bfdd353bc357cb40be8d49d2d9292a85188`.
Docker CPU completed twelve fixed steps; the configured RTX 4090 completed a
single bounded CUDA appointment of twenty-four fixed steps. The respective
source-safe summary identities are
`sha256:c50c6c36645386b4a044a4c3f874d37bdd3225bd51a24d61bdddc4f7ddb44a` and
`sha256:35fe95d260772a100de782869aa9ed732dc470c468cdf83b97c736ba150f8ed3`.
Artifacts contain only contracts and scalar runtime facts below
`D:\thericher-v2\model-artifacts`; no values, labels, predictions, weights,
checkpoints, cache mutation, KIS call, credential access, broker route, Paper
action, or PnL claim occurred.

The Claude drift check timed out after its bounded invocation, recorded as
`review_unavailable` rather than a verdict. It does not hold the next Engine
package. The 42-control source still has zero forward target-ready pairs, so
this is architecture/runtime evidence, not a trained predictor or a candidate
selection result.

## Profiled MTF Forward Campaign Readiness (2026-08-01)

`profiled-mtf-forward-campaign-readiness-v1` is complete. Engine now accepts
only Data's validated aggregate forward-outcome inventory and freezes the
predeclared first campaign shape as metadata: the `short` two-leg scope, 30
pairs, `20/2/8` temporal allocation, 20bp round-trip sensitivity, no-trade
baseline, blocked-session target-permutation kill test, CPU-first order, and a
ten-minute CUDA cap. It neither opens a D:-resident snapshot nor calculates a
feature, label, return, score, PnL, or Paper intent.

The source-safe `local-cache-r2` receipt is
`sha256:2164ee3fa0021fd3c095e55bd5e2c5bf9d2bce39788a2699cc3573cf45f119db`.
It is bound to forward outcome contract
`sha256:5ab795b173d489117e11dd02e71b94c5389a75d414376c4ee81461d9a5b1ae2c`
and reports `zero_target_ready`, count zero, and scoped `input_unavailable`.
It contains no raw rows, features, targets, predictions, or weights.

The Data inventory inspector was narrowed to a read-only resolver: an absent
store now returns zero without creating any artifact or market-data directory,
and an existing target-ready witness still requires its immutable raw snapshot
hash. The host and Docker research container reattached the same `r2` receipt,
which fixes the prior read-only `/app/market_data` inspection failure without
weakening integrity checks. Claude timed out as `review_unavailable`; no
decision, approval, or hold follows.

## Profiled MTF Forward Supervised Dataset Contract (2026-08-01)

`profiled-mtf-forward-supervised-dataset-contract-v1` is complete. Data now
opens a retained forward snapshot only through a canonical, hash-reattested
read-only loader. It rejects a missing, changed, malformed, noncanonical, or
time-misaligned snapshot and creates no paths when the store is absent.

Engine freezes one exact target contract against a matching readiness receipt:
the first 30 chronological QQQ/SPY pairs, each with two independent M1 legs,
use `ln(final 15:45 ET completed close / last causal 15:30 ET close)`. The
pair-level split is frozen before a model sees a target: 20 train, 2 purge, 8
validation. Target rows and snapshot references can exist only under
`D:\market_data`; external receipts retain hashes, counts, and fixed semantics
only. This is not a model, comparative result, PnL, Paper input, or GPU
appointment.

Fixture materialization verified first-30 ordering, target endpoints,
pair-level purge, stale readiness rejection, raw snapshot mutation/missing
rejection, and artifact isolation. The live local reattachment produced the
source-safe readiness `local-cache-r3` receipt
`sha256:bb6cc42c83a3b30dff968461528ba01dcf1e56df5eac55540b8e55d926b24a3f`:
the inventory is still `zero_target_ready`, count zero. The corresponding
dataset `local-cache-r1` receipt is
`sha256:7b94db11eaa66c6b253c7dc6b77784faed12b0b79a12153e01e5c3e39d9c8ff3`;
it contains no target-bearing D: dataset artifact. Claude's requested
falsification-first check timed out, recorded as `review_unavailable`, not a
verdict or a hold on the next independent Engine package.

## Profiled MTF Forward CPU Campaign Executor (2026-08-01)

`profiled-mtf-forward-cpu-campaign-executor-v1` is complete. It reopens a
supervised dataset only through its immutable external receipt, current Data
snapshot catalog, exact first-30 identities, and canonical D:-only payload.
It rejects stale, missing, or mutated materialization and pair-split drift
without creating a data path.

The fixed `short` representation uses completed 15:30 ET M1 prefixes only. It
preserves native `1m/5m/10m/1h/3h` windows (`15/3/3/2/2`) and makes one
explicit 50-value classical control from normalized close/volume features;
outcome-window values never enter features. The predeclared CPU-only controls
are `no_trade_zero`, `ridge_alpha_10`, and a depth-limited histogram-gradient
regressor. They execute one `20/2/8` pair-level pass with purge rows excluded
and a reversed pair-block training-target kill test. Results remain
non-promoting: no winner, PnL, Paper input, weights, or GPU appointment.

Full-session fixture evidence passed deterministically and kept all values,
targets, predictions, and model state out of artifacts. The real host and
Docker `local-cache-r4` result is
`sha256:0f7cb547a31a7d6e71418e1c5b9f8e454957cb1c87a7e56f4663d2fd87096b10`:
the inherited dataset is still zero pair, so no model was fitted and no GPU was
used. Claude timed out as `review_unavailable`, not a conclusion or a reason
to pause the next distinct Engine family.

## Profiled MTF Forward Ragged Sequence CPU Campaign (2026-08-01)

`profiled-mtf-forward-ragged-sequence-cpu-campaign-v1` is complete. Its
D:-only reader reattests the external supervised-dataset receipt, current Data
catalog, first-30 snapshot identities, chronological `20/2/8` pair split, and
canonical materialization before a target is opened. It builds five native
`short` sequences (`15/3/3/2/2`, width two) from completed 15:30 ET prefixes
only. Masks are explicit and all-available; timeframe rows are never aligned.

The one fixed CPU contract evaluates no-trade-zero beside per-timeframe GRU,
left-padded causal TCN, and availability-masked cross-timeframe attention. Each
family uses one seed, eight full-batch SGD epochs, MSE, an excluded pair-level
purge, and a reversed training-pair-block target counterpart. Fixture-only
execution ran deterministically inside the network-disabled Docker research
image without a GPU device. It selected no winner and persisted no features,
targets, predictions, weights, or checkpoints.

The actual host and CPU-only Docker reattachment produced the same external
`local-cache-r1` receipt
`sha256:6f317b1af3a01af4b40d88eb35675ef0dcb25e9fa263da92abd5c73d9015eff3`:
the inherited source is still zero pair, so no model was fitted and no GPU was
appointed. Claude's requested falsification-first check timed out and is
recorded as `review_unavailable`, not a hold. The next data-facing package is
an explicit local-cache capture-cycle runner for the existing 15:30 input and
15:45 outcome observers.

## Profiled MTF Forward Capture Cycle (2026-08-01)

`profiled-mtf-forward-capture-cycle-v1` is complete. It is one local-cache
dispatch point, not a scheduler: on a regular session it calls the existing
input observer only from 15:30 to before 15:45 ET, then the existing outcome
witness from 15:45 ET onward. Every other instant is an immediate no-op with no
cache load or terminal unavailable record. Existing D:-only raw-snapshot,
duplicate, mutation, conflict, and source-safe artifact semantics remain owned
by those two leaves.

Focused fixtures cover both due actions, idempotent retry, conflict and mutated
input containment, D:-only placement, and import isolation. A host invocation
and a matching network-disabled, read-only Docker invocation reattached the
current local cache as `input_unavailable`; neither called KIS, read a
credential, opened raw values, changed a cache, trained a model, used GPU, or
reached a broker route. Claude's required lifecycle check timed out and is
recorded as `review_unavailable`, not a verdict or a hold. The missing forward
pair is a Data fact only: Engine work continues on separately qualified input.

## Forward Capture And Chronos Probe (2026-08-03)

`forward-capture-and-pretrained-model-cadence-v1` is complete. The KIS
intraday-head schedule invokes the local network-disabled profile capture once
after a successful collection and records its categorical result in the
existing schedule receipt. A Docker invocation outside its ET slot returned
`outside_cycle_slot` without cache/KIS/credential/account/broker activity.
One direct intraday-head schedule invocation then completed its KIS market-data
collection, local `outside_cycle_slot` capture, pending data-only observation,
and source-safe terminal receipt with exit code `0`; it used no account,
position, order, or live endpoint.

Engine independently downloaded the official safe Chronos-T5 Tiny files to
`D:\thericher-v2\model-artifacts`, then completed a network-disabled Docker
CPU receipt and RTX 4090 CUDA receipt against the retained Norgate D1 source.
Chronos did not beat the frozen zero-return baseline on the CUDA diagnostic and
is rejected for this source. It is not a Paper input, ranking, ensemble,
profitability, or promotion result. The source's current-listing, non-PIT,
adjustment/corporate-action/availability, and unknown-pretraining limitations
remain unchanged. Claude timed out as `review_unavailable`.

## KIS Broad D1 Cursor Closure (2026-08-03)

An immediately started existing KIS Paper `dailyprice` broad-D1 worker
reattached its durable cursor and returned `complete` with zero remaining
targets. Source-safe totals are 2,119 attempted targets, 1,089 complete,
1,030 source-limited, 50,810 accepted pages, and 1,360 categorical target
failures. It made no account/position/order/quote/live request. This closes
only that current-listing cursor scope; raw KIS rows stay on D: and the
source remains non-PIT and non-promoting. The next objective materializes a
read-only canonical panel before Engine opens one new KIS-bar preflight.

## KIS Broad D1 Panel And Causal Preflight (2026-08-03)

`kis-broad-d1-panel-and-causal-candidate-v1` is complete. Data reattached the
immutable broad-D1 manifest
`sha256:89e2362e983e6c74e30d55260cb95d9f52749f3950b35887d454005f615fce73`
and its external materialization receipt
`sha256:f6714a062f6754923c9960e74a7bd6717db6df3b31b681745860dbb0103ebe0f`.
The panel identity is
`sha256:6f83952b101050f221032ee48f71d1dc70bb392aa3fa5e139dba1335c8659c08`.
It covers 2,119 current-listing targets; 1,643 have enough bars for the fixed
candidate geometry. A distinct, non-upcast selected-panel type reattested 129
raw target streams to form a 128-target, 800-session common grid from
2023-05-17 through 2026-07-27 UTC, with one terminal bar withheld. It records
1,991 excluded full-panel targets and never claims an all-target raw-byte
recheck during this consumer run.

Engine froze the source-local pooled L2-logistic preflight: completed-D1
within-bar geometry features, next-bar within-bar direction target, `520/20/260`
chronological development/purge/validation allocation, flat and causal
baselines, 2,000 session permutations, and 2,000 session bootstraps. Claude's
falsification-first review was `uncertain`, so the review conditions are part
of the frozen contract. The network-disabled Docker run wrote external receipt
`sha256:c3b6918d7dcb259d4bbb7282e19c08c70939a2f9818a6d8774108bf0a658143f`
with `input_unavailable: within_bar_geometry_integrity_failure` before model
fit. No model weights, predictions, raw values, KIS call, credential read,
account/order/broker route, Paper action, or GPU allocation occurred.

The range screen remains fixed. Its candidate-local failure is not a Data or
execution hold; the separately frozen event-censoring result is recorded below.

## KIS Broad D1 Geometry Audit And Event-Censored Candidate (2026-08-03)

`kis-broad-d1-geometry-audit-and-event-censored-candidate-v1` is complete.
The network-disabled, read-only Docker Data audit reattached the same selected
128-target panel lineage and wrote an aggregate-only external receipt
`sha256:8a8c0eef3d7036c595517b9bba4a08b2232ed3f712dc17da8507986f7150525a`.
It found 34 fixed `high / low > 2.0` events across 15 targets and 34 sessions;
the stricter `>3`, `>5`, and `>10` aggregate counts were `3`, `0`, and `0`.
The causal `t-19..t` feature-window mask left 63,455 development pairs and
30,451 validation pairs, with 126 to 128 available targets in every validation
session. No raw rows, prices, symbols, targets, credentials, KIS call, account,
broker, or GPU state was written or used.

Claude's falsification-first verdict was `supported-with-limits`: censoring is
hygiene rather than performance evidence, all controls must use the same mask,
and both session-block and per-target temporal nulls are required. The separate
Docker CPU candidate bound that audit and completed receipt
`sha256:b318491bb3b1e0f4c15f219c68b6423e8d0e4e66f4db92f53d104b9e2bd43e5e`.
Its pooled L2 logistic balanced accuracy was `0.4997425`, below the best fixed
baseline (`0.5105884`) and both 95th null quantiles (about `0.500338`); both
bootstrap advantages were negative. It is therefore closed as a non-promoting
no-signal result. No weights, predictions, PnL, ranking, ensemble, Paper input,
or CUDA appointment was created.

## KIS Broad D1 Adjustment-Semantics Capability Probe (2026-08-03)

`kis-broad-d1-adjustment-semantics-probe-v1` is complete. Data reattached the
same immutable selected-panel lineage and used a dedicated KIS Paper transport
limited to one in-memory token plus the preselected `dailyprice` witness scope.
The actual source run compared opaque request values `0 -> 1 -> 0` for at most
two anonymous range-event witnesses. It wrote only aggregate external receipt
`sha256:b5f2c1203e04fc0e8cd05d2ae67e1c6999abafaacc6a4bf7e4a788c50436fd4f`.

The result is `inconsistent/mixed_comparison_result`: one token attempt, six
accepted daily responses, zero categorical request errors, and no minute,
account, quote, order, or live route. No raw row, witness identity, value,
credential, URL, or broker payload was retained. This does not reinterpret
the existing `MODP=0` cache, prove adjusted/corporate-action semantics, or
qualify the source for PIT, model, ranking, Paper, or live use. The two prior
broad-D1 logistic lineages remain closed; no GPU appointment occurred.

## KIS Broad D1 Cross-Sectional Momentum CPU Baseline (2026-08-04)

`kis-broad-d1-cross-sectional-momentum-cpu-baseline-v1` completed against the
same immutable 128-target, 800-session `MODP=0` panel. The new read-only input
adapter binds the panel, materialization, and geometry-audit identities; it
does not call KIS, read credentials, alter the cache, or retain raw bars. The
fixed long-only top-10 `5/20/60` matrix uses completed-D1 decisions, the
`520/20/260` split, common event hygiene, naive controls, and a 5/10/20-bp
round-trip stress axis.

Claude's post-outcome review was `uncertain` and identified an initial
cost-accounting defect: standard turnover had been divided by two a second
time. The code now charges declared round-trip bps times standard turnover,
and the prior host receipt is superseded. Corrected host and network-disabled
Docker runs produced the same contract
`sha256:927278e5abd75052a3cfdc57720d86613bb67543646f438a7523662c7fb53098`
and receipt `sha256:bb5cb76248663e66424d8342f59bafbd9be9c25a4c41f3954a7b642bd9b01a91`.
The 5- and 60-session validation cells fail a fixed falsifier; the 20-session
cell survives the fixed equal-weight comparison and stress axis. This is only
a source-local observation: no winner, promotion, sealed holdout, GPU job,
ensemble, PnL claim, local-paper input, or KIS Paper action was created.

The next company objective is to connect the existing prospective SPY
completed-bar observation, frozen baseline, and virtual-Paper adapter in one
idempotent session-cycle. It must not reuse this historical result or wait in
the foreground for a market session. The optional Claude direction challenge
timed out as `review_unavailable`, not agreement or a hold.

## Prospective SPY Paper Session Cycle (2026-08-04)

`prospective-spy-paper-session-cycle-v1` is complete. The existing
Data-owned SPY completed-bar capture now feeds a separate, post-collector
cycle service. A capture that is missing, incomplete, stale, outside its time
window, or abstaining writes only a source-safe no-intent receipt and does not
load Paper configuration or touch account, quote, or order routes. A captured
immutable observation remains a distinct source reference. Once a session
reaches preparation, the cycle records its prepared-decision reference and the
actual durable canary identity returned by the existing virtual-Paper canary;
it never predicts a canary ID from the observation hash. The pre-existing
canary lock serializes retries and reconciles an uncertain prior submission
before another submit. The collector and the Paper-capable service remain
separate processes, and no new Windows task was introduced.

Host and isolated Docker smoke runs before the decision cutoff both completed
as `no_intent/before_decision_cutoff`; neither reached Execution nor made a
KIS account, quote, or order call. The final Claude route review timed out as
`review_unavailable`, which is evidence about that review only, not agreement
or a hold. No current eligible `enter`, Paper submission, live route, model
training, GPU appointment, PnL result, or historical broad-D1 reuse occurred.

The next objective is a bounded Data/Engine timing probe around the SPY 15:30
ET decision boundary. It must measure completed-bar availability and
end-to-end collector timing before changing the existing 04:31 KST trigger or
the strict one-minute execution-validity contract. It makes no Paper account,
quote, or order call, and the schedule continues independently.

Verification for this integration: the changed-path serial group passed
`62` tests, Ruff and all required Compose configurations passed, and the
clean-root parallel authority suite passed `2,373` tests with `23` skips in
188.50 seconds. A diagnostic full serial `pytest -q` attempt collected all
2,396 tests but exceeded the host's 15-minute command limit; it left no pytest
process behind. The last completed serial baseline is still within its weekly
diagnostic interval, so this is a test-throughput finding rather than a route
or product failure. Keep the clean-root parallel runner as the goal-boundary
authority and investigate the serial runtime only as a separately bounded
throughput package.

## Prospective SPY Completed-Bar Timing Probe (2026-08-04)

`kis-spy-completed-bar-decision-timing-probe-v1` now has an independent
Data-only receipt path. The existing intraday-head scheduler records its host
collector dispatch and return endpoints, extracts only the existing
kind-tagged SPY aggregate counts, and invokes a network-disabled container
after a successful collection. That container has no KIS environment values,
does not create a client, and uses the read-only head cache only to classify
whether the prefix exists *after* collection. Its receipt includes UTC and
America/New_York timestamps, offsets, DST state, collector wall-clock order,
and a categorical schedule relation; it never emits a decision-time
availability or feasibility verdict. The probe is deliberately absent from the
terminal scheduler receipt, so its own failure cannot turn a Data measurement
into a scheduled-task recovery result.

Claude's timing challenge was `supported-with-limits`: a post-collection cache
cannot be relabeled as 15:30 availability, Docker lifecycle time must stay
visible, and the fixed 04:31 KST trigger has different semantics across DST.
The static schedule relation is already clear: it is before the decision
cutoff in standard time and at or after the exclusive expiry boundary in
daylight time. The pending worker records lag magnitude and source state only;
it cannot justify a cadence or TTL change by itself.

Focused tests, host smoke, network-disabled Docker smoke, and the clean-root
parallel suite (`2,379 passed, 23 skipped` in 189.72 seconds) all passed. The
existing `thericher-kis-paper-intraday-head` task is `Ready` with its next
owned run at 02:31 KST; no foreground wait, new collector, KIS account/quote/
order call, Paper action, GPU appointment, or model change was created.
