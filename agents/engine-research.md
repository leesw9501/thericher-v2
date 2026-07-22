# Engine Research Agent

## Working Memory

Own hypotheses, campaign contracts, model work, walk-forward evaluation, and
model-side PnL attribution. Current priority is a KIS-native daily baseline and
the first honest intraday input contract, not GPU occupancy.

## Intraday Input Contract

The KIS-native minute cache now supports one bounded chronological CPU baseline,
not an eligible model-promotion campaign. Its original 239-bar extended-session
pages remain hash-attested and KIS-reconstructible, and the reattested cache now
has 21 complete regular sessions each for QQQ/NAS and SPY/AMS. The 2026 calendar
window is explicit, but KIS bar open/close semantics remain unqualified and the
first nine-session validation region is too small for model selection.

The first QQQ run fixed the latest 20 complete sessions (2026-06-23 through
2026-07-21) into a 10 development / 1 unused-session purge / 9 validation split.
It ran `flat`, `always_long`, and `previous_bar_direction` through replayable
`local_paper` only. The external manifest is
`D:\\thericher-v2\\model-artifacts\\kis-intraday-cpu-campaign\\qqq-20260623-20260721-r1\\summary.json`.
All costed non-flat references were negative in both phases. This establishes a
baseline to beat, not an edge, model score, GPU qualification, or promotion.

When those source facts are established, freeze this initial contract before any
model comparison:

- decision timestamp: end of the latest completed 1m bar only;
- feature windows: 90 x 1m, 18 x 5m, and 9 x 10m completed bars from the same
  KIS cache, with no provider mixing or gap filling. Keep 1h and 3h inactive
  until their required same-session contiguous coverage and session semantics
  are available;
- target: decide at a completed 1m close, enter at the next 1m open, and exit
  at the following 1m open, long-only. No target may look through a session
  boundary;
- session behavior: abstain outside a Data-declared regular session or whenever
  any required source/resample bucket is missing, incomplete, or stale;
- cost model: 1 bp per-side fee plus 2 bps per-side slippage for the initial
  screen. Use a separately recorded stress pass later; these are research
  assumptions, not KIS fee claims;
- naive comparators: `flat`, `always_long`, and `previous_bar_direction`, all
  through the existing `local_paper` target contract only.

The original 239-bar observed cache cannot provide the 3h context window or a
chronological validation split. One complete 390-minute session can exercise
all resampling and local-paper replay cells, but it is still not sufficient for
GPU, candidate ranking, PnL claims, ensemble selection, or model promotion.

## Ready Queue

1. The current KIS-native comparative baseline is at
   `D:\thericher-v2\model-artifacts\kis-daily-comparative-validation-v1\kis-daily-comparative-20260722T100000Z`.
   It fixes the 694-session panel to 414 development sessions, two purge
   sessions, 138 validation sessions, two embargo sessions, and a 138-session
   final region. Each development/validation consumer receives an independent
   hash-bound Data slice; it cannot read purge, embargo, or holdout bars.
2. The final historical region is `burned_precontract`, not sealed: the prior
   595-session relative-strength smoke observed dates through the current panel
   end. The new comparative output is therefore historical execution evidence
   only, not a return, model-selection, or promotion claim. This does not block
   paper operation or new research; fresh paper/prospective observations become
   the next honest out-of-sample evidence.
3. The CPU run contains fixed relative-strength, cash, and fixed-quantity
   buy-and-hold comparators for each ETF. All fills are replayable
   `source: local_paper`; `run.json`, event hash, data hash, costs, and code
   revision are retained outside Git.
4. The first fixed CPU L2-logistic trade-quality gate is complete and retired.
   Its post-commit artifact is
   `D:\thericher-v2\model-artifacts\daily-three-etf-l2-trade-quality-gate-v1\kis-daily-trade-quality-20260722T170000Z`.
   It used 155 development selector entries (85 positive, 70 negative), and 58
   validation decisions. The candidate accepted 50 trades versus the selector's
   53, improved observed mean return (`0.0001684` versus `-0.0004646`), Brier
   (`0.252925` versus `0.253254` prevalence), and maximum drawdown (`0.06447`
   versus `0.07098`), but both the primary and 2 bp/side stress bootstrap lower
   bounds were `0.0`. Do not retune, promote, or ensemble this candidate.
5. Choose the next breadth campaign only from a data contract with a materially
   broader eligible universe or genuinely new prospective KIS Paper evidence.
   A later depth or ensemble candidate needs a distinct hypothesis and upstream
   out-of-fold evidence; do not use GPU merely to revisit this retired gate.
   The existing Norgate static 523-symbol trial panel is development-training
   preparation only, not a candidate for selector, model, GPU, PnL, or paper
   work under its current manifest scope.
6. Prepare the next KIS-only intraday candidate from the frozen 20-session
   contract: breadth starts with deterministic features, regularized linear,
   and tree baselines; depth compares TCN, GRU/LSTM, and a compact attention
   model only after the feature/target artifact and CPU comparator are frozen;
   ensemble work requires independently generated out-of-fold predictions;
   replication reruns the selected contract unchanged.
7. The first source-windowed CPU baseline is complete at
   `D:\\thericher-v2\\model-artifacts\\intraday-multitimeframe-baseline\\kis-private-intraday-2026-07-21-qqq-r1\\summary.json`.
   It exercised 390/78/39/6/2 bars at 1m/5m/10m/1h/3h and emitted only
   replayable local-paper fills. Treat it as interface evidence, not a score or
   model result; accumulate prospective sessions before freezing a campaign.

## GPU Policy

One GPU job may run at a time. GPU time follows an eligible frozen dataset and
campaign contract; it is not a utilization quota. CPU preparation, data work,
and execution implementation continue in parallel. Store checkpoints, logs,
and generated artifacts only under `D:\thericher-v2\model-artifacts` or
`/app/model_artifacts`.

Runtime checked 2026-07-22: `thericher-v2-research:latest` exposes one RTX 4090
to PyTorch `2.7.0+cu128` (CUDA 12.8, cuDNN 90701). The host `uv` environment has
no `torch`, so an eligible GPU campaign uses the research container until a host
runtime is intentionally added.

## Durable Knowledge

- Daily raw-price data has an explicit corporate-action limitation.
- The former daily 756-session target improved comparative validation; it never
  blocked KIS Paper connectivity or a deterministic paper canary. The active
  694-session panel is a documented source-limited input, not a repaired one.
- A split label must record historical exposure honestly. `burned_precontract`
  constrains only the interpretation of that historical suffix; it is never a
  KIS Paper, scheduler, or operator-approval gate.
- A learned node emits timestamped evidence and proposed target state, never a
  broker request.
- Validation evidence can reject a claim without becoming a manual approval
  process for other independent work.
- The first KIS paper canary takes a deterministic explicit buy decision only;
  it is deliberately independent of learned-model or GPU readiness.
- The L2 gate is intentionally CPU-only: this small daily panel cannot justify
  GPU training. A later GPU sequence candidate needs its own frozen prospective
  campaign rather than widening this candidate after seeing results.
- The L2 gate core accepts only the hash-bound prefix through the post-validation
  embargo. Its loader re-attests complete raw source files but does not
  materialize the later burned suffix as `Bar` objects. That boundary is a
  leakage control, not a KIS Paper or research-queue approval gate.
- The KIS intraday contract uses the provider's Korea timestamp as the UTC
  conversion basis and keeps exchange timestamp semantics visibly unqualified.
  This avoids silently inventing a US daylight-saving calendar from an observed
  source field.
- Multi-session validation accepts overnight gaps only at the exact close/open
  pair of consecutive declared `SessionWindow` values. A caller cannot nominate
  a bare timestamp to hide a missing intraday minute, and no target may cross a
  declared boundary.
- Campaign attempt labels create separate immutable work/artifact paths after an
  interrupted run. They are recovery identities, not a scheduler, approval, or
  model-selection mechanism.

## Recovery

Campaign artifacts must name dataset, code, split, cost, model, and result
identity. A missing checkpoint/summary is `restart`, not a partial model result.
Ask Claude only at the defined leakage, sealed-holdout, surprising-result,
ensemble, or promotion decision boundaries.

The pre-batch SQLite smoke artifact that stopped at a host timeout is
`restart` evidence only and must not be interpreted. The later completed smoke
under the same external artifact root is the usable local-paper replay.

## Next Handoff

Keep KIS regular-session minute coverage accumulating while building the first
bounded KIS-only intraday feature/target artifact and CPU breadth comparison.
Keep breadth, depth, ensemble, and replication queues current without creating a
report family; treat any next CUDA work as descriptive until the tiny validation
region is replicated or expanded.
