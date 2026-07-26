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
- Commit work that changes behavior, a contract, a test, or a measured fact.
  Do not substitute schedule reattestation or document repetition for engine
  progress.

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
- The 2026-07-26 bounded QQQ KIS Paper minute probe accepted two full terminal
  head pages through one in-memory client/token under the existing request
  gate. It observed a gap within one exchange date; it did not establish
  historical continuation or a complete 390-minute session. The probe retained
  no raw bars. Its source-safe external evidence is
  `20260726T123512436025Z-f1575006a7319021.json`.
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

### Engine Research

- The frozen QQQ KIS-private-daily CPU baseline completed with 4,756 sessions,
  an 80/20 chronological split and one-session purge. Both fixed naive
  candidates were after-cost negative in development and the descriptive
  holdout; all fills were `local_paper`. No candidate was selected.
- A Docker CUDA replication compared LSTM, causal TCN, and compact attention on
  the existing 20-session intraday scope. It wrote no checkpoint or raw data;
  it made no winner, ensemble, profitability, or Paper-authorization claim.
- No GPU job is active. The next bounded breadth screen uses the already
  qualified 4,756-session QQQ/SPY KIS-private-daily intersection instead of
  waiting for prospective intraday coverage. It remains development-only and
  local-paper-only.
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
  current shared request-start gate and cooldown are evidence-backed temporary
  controls, not approval gates.
- KIS documents a 24-hour access token and a six-hour renewal behavior. The
  current five-minute cross-process token-start guard prevents short-lived
  workers from colliding; it is not a token lifetime or a reason to idle a
  ready lane.
- The source-safe probe verified reuse of one in-memory token across two
  terminal-head requests under the current gate. It did not test a faster
  ceiling, historical continuation, or continuous-session collection. The
  current evidence-backed rate/cooldown controls remain active; do not use a
  parallel request flood.
- The measured single-client capture path now records capture-scoped coverage
  and is the existing head task's configured collection mode. A terminal page
  remains current-head evidence, not permission to invent a historical cursor.
  The next bounded Research screen uses the qualified daily cache; it does not
  change KIS pacing or wait for an intraday schedule.

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
the CLI OAuth session remained expired during the throughput-governance,
single-client-capture, and profile-integration drift-check attempts; no private
material was sent. This is a scoped tooling fault, not a hold on ready private
work.

## Recovery

At start, after interruption, and before trusting a checkpoint, inspect
durable evidence and classify a run as resume, restart, reconcile, complete,
unrecoverable, or operator. A failed source probe, a missing prospective pair,
or a scheduled wait affects only its own input or worker. It cannot become a
global permission or progress latch.

## Next Handoff

Follow NEXT_CODEX_GOAL.md. Build and run the first bounded KIS-native daily
sequence-model breadth screen from the already qualified QQQ/SPY daily cache,
then refresh this file only with current cross-lane facts after that bounded
objective completes.
