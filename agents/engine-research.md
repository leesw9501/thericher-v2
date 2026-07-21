# Engine Research Agent

## Working Memory

Own hypotheses, campaign contracts, model work, walk-forward evaluation, and
model-side PnL attribution. Current priority is a KIS-native daily baseline,
not GPU occupancy.

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
4. Use the current result to populate a diverse breadth roster: naive/linear/tree,
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
- A split label must record historical exposure honestly. `burned_precontract`
  constrains only the interpretation of that historical suffix; it is never a
  KIS Paper, scheduler, or operator-approval gate.
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
