# Engine Research Agent

## Working Memory

Own hypotheses, campaign contracts, model work, walk-forward evaluation, and
model-side PnL attribution. Current priority is a KIS-native daily baseline,
not GPU occupancy.

## Ready Queue

1. The 595-session KIS panel completed a local-paper smoke through
   `daily-three-etf-relative-strength-v0`: 287 decisions, 65 abstentions, 444
   replayable `local_paper` fills, and a flat final account. Its external
   `run.json` fixes the strategy, costs, dataset, event hash, and code revision.
   It is execution evidence only, not a return or model-selection claim.
2. Consume the Data Agent's current 694-session hash-attested common
   `QQQ`/`SPY`/`IWM` cache. It is source-limited below IWM's lower boundary, so
   freeze the available panel rather than waiting for a non-permission target.
   After Claude's split review, freeze the
   `daily-three-etf-relative-strength-v0` contract: 20-session raw return,
   one positive ETF or cash, `t+1` entry, `t+2` exit, local-paper costs,
   chronological 60/20/20 split, and two-session purge/embargo.
3. Run the frozen CPU baseline and retain replayable `local_paper` attribution.
4. Use its result to populate a diverse breadth roster: naive/linear/tree,
   one compact sequence model, and at most one small attention or public
   time-series benchmark. Start a depth or ensemble candidate only after a
   concrete distinct hypothesis and proper upstream out-of-fold evidence.

## GPU Policy

One GPU job may run at a time. GPU time follows an eligible frozen dataset and
campaign contract; it is not a utilization quota. CPU preparation, data work,
and execution implementation continue in parallel. Store checkpoints, logs,
and generated artifacts only under `D:\thericher-v2\model-artifacts` or
`/app/model_artifacts`.

## Durable Knowledge

- Daily raw-price data has an explicit corporate-action limitation.
- The former daily 756-session target improved comparative validation; it never
  blocked KIS Paper connectivity or a deterministic paper canary. The active
  694-session panel is a documented source-limited input, not a repaired one.
- A learned node emits timestamped evidence and proposed target state, never a
  broker request.
- Validation evidence can reject a claim without becoming a manual approval
  process for other independent work.

## Recovery

Campaign artifacts must name dataset, code, split, cost, model, and result
identity. A missing checkpoint/summary is `restart`, not a partial model result.
Ask Claude only at the defined leakage, sealed-holdout, surprising-result,
ensemble, or promotion decision boundaries.

The pre-batch SQLite smoke artifact that stopped at a host timeout is
`restart` evidence only and must not be interpreted. The later completed smoke
under the same external artifact root is the usable local-paper replay.

## Next Handoff

Report the dataset contract, naive baseline, falsification result, and exactly
which model family is next. Keep breadth, depth, ensemble, and replication
queues current without creating a report family.
