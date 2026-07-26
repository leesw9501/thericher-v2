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
  and worker waits. It keeps one measured reversible improvement in the
  orchestration board; it does not create a new approval gate or standing lane.
- Commit work that changes behavior, a contract, a test, or a measured fact.
  Do not substitute schedule reattestation or document repetition for engine
  progress.
- For KIS Data, distinguish token issuance, page pacing, and worker schedule
  facts. A token-start guard or an owned `next_due` is not a foreground delay;
  it is a reason to run another ready package while the owning worker yields.

## Current State

### Data

- D: is about 40.45 percent free. Keep data under D:\market_data and stop new
  large work before the 15 percent floor.
- The KIS private daily cache has a QQQ/SPY common historical intersection of
  4,756 sessions. The three-target QQQ/SPY/IWM intersection has 694 sessions;
  IWM remains source-limited at its qualified boundary.
- The private intraday cache has 21 complete QQQ and SPY regular sessions from
  the prior bounded historical scope. It is eligible only for scoped
  historical work, not a broad profitability claim.
- The prospective QQQ head is generation 10 with zero complete sessions out
  of five. The retained short-session evidence is a Data-local source fact. It
  is not a company hold.
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
  `session-capture` mode in its one existing Docker profile. Its triggers,
  page cap, worker lock, request gate, cooldown, collector exit authority, and
  network-disabled observer remain unchanged. The QQQ-only metadata
  preparation handoff also runs for eligible capture results. No scheduled
  capture has yet run under this new profile configuration; that future result
  is Data evidence, not a company hold.
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
- No GPU job is active. The completed daily evidence must not be promoted or
  used to choose a Paper order; prospective intraday coverage remains an
  independent Data concern.
- The prospective pair-bound observer remains isolated and local-paper-only.
  It becomes an additional observation input when its Data pair exists.

### Execution

- local_paper, kis_paper, and kis_live routes remain distinct. Simulated fills
  remain labeled source: local_paper.
- KIS Paper account/market/order work is standing-authorized for this private
  project. KIS_LIVE_* is never readable or callable.
- The local operations console is credential-free and reads sanitized
  projections only.
- Existing scheduled Paper facts are categorical. No current receipt proves a
  selected model, external fill, or realized PnL.
- A target-position binding now derives a deterministic local-paper delta
  intent or a scoped no-intent for an already-satisfied/mismatched target. It
  preserves route isolation and makes no KIS call.

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
  ready lane.
- The bounded calibration accepted a 1.0-second QQQ terminal-head candidate
  with one in-memory token, two full pages, and zero categorical errors. It is
  evidence for one end-to-end setting change, not a universal throughput claim;
  do not use a parallel request flood. The probe rejects unsupported intervals
  and cannot record success when its observed page-request starts are faster
  than the claimed tested interval.
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
ensemble, scheduler-widening, and execution-risk decisions. On 2026-07-26 KST
the CLI OAuth session remained expired during throughput-governance,
single-client-capture, profile-integration, and daily-campaign falsification
checks; no private material was sent. This is a scoped tooling fault, not a
hold on ready private work.

## Recovery

At start, after interruption, and before trusting a checkpoint, inspect
durable evidence and classify a run as resume, restart, reconcile, complete,
unrecoverable, or operator. A failed source probe, a missing prospective pair,
or a scheduled wait affects only its own input or worker. It cannot become a
global permission or progress latch.

## Next Handoff

Follow NEXT_CODEX_GOAL.md. Keep the weak QQQ/SPY controls as descriptive
evidence and establish whether a bounded KIS-native daily universe can support
the next stock-selection research contract. Refresh this file only with the
resulting current cross-lane facts after that bounded objective completes.
