# Next Codex Goal

## Objective

Build and run one small, offline coverage audit for the two immutable Tiingo
standard-EOD raw-daily snapshots:

- `snapshot=2026-07-18-tiingo-standard-eod-pilot-r1`
- `snapshot=2026-07-18-tiingo-standard-eod-pilot-r2`

The audit must distinguish the useful r2 501-session descriptive panel from
the r1/r2 combined 18-session overlap. It advances the data-quality and
research-readiness loop by deciding whether a later, separate bounded shard
would materially improve coverage. It must not turn either snapshot into a
historical tradable universe, point-in-time data, or a model input.

## Ownership

- **Data Agent:** owns exact snapshot re-attestation, aggregate coverage
  measurement, external summary provenance, and one bounded recommendation.
- **Review/Claude:** provides a concise falsification-first check before a
  coverage result is used to propose another acquisition or research boundary.
- **Engine Research Agent:** is an observer. It must not consume, train, rank,
  ensemble, or schedule GPU work from the audit.

## Boundaries

- Do not read `.env`, credentials, or any token. Do not call Tiingo, KIS, or
  any network source. Do not acquire more data in this objective.
- Re-attest both exact canonical/manifest hashes and Tiingo rights markers
  offline before calculating any fact. Keep raw responses and candidate symbols
  external; the audit summary may contain only aggregate counts, date ranges,
  hashes, row-count distributions, overlap counts, scope, and limitations.
- Write one immutable audit summary only under
  `D:\thericher-v2\model-artifacts\data-agent`; never copy data into Git.
  Do not create a report family, dashboard, scheduler, provider/catalog,
  feature, strategy, model, GPU job, Docker work, broker call, KIS use, or
  public service.
- Keep all audit outputs `pit=false`, `ranking=false`, `holdout=false`,
  `campaign=false`, `model=false`, `gpu=false`, and `paper=false`.
- The audit may recommend one later bounded acquisition only when it names the
  expected data-loop value, unique-symbol budget effect, storage effect, stop
  rule, and the fact that would reverse the recommendation. It must not start
  that acquisition itself.

## Required Work

1. Read both manifests through their offline verifiers and ask Claude to
   challenge survivorship, selection bias, shared-session interpretation, and
   any proposal for another shard. Do not send raw rows, symbols, or secrets.
2. Implement the smallest mock-tested offline audit helper and CLI. Tests must
   prove hash/rights-marker tampering fails, no network/token/broker/Docker
   access is needed, raw values and symbols do not enter the summary, and r2
   panel facts are not misrepresented as combined-panel or PIT eligibility.
3. Run the audit once against the two external snapshots. Report only aggregate
   evidence and the external summary path/hash. Update the Data and Engine
   stateboards with the resulting next acquisition recommendation or stop rule.
4. Refresh `HANDOFF.md`, `DECISIONS.md`, and this goal, then continue while no
   real operator approval boundary remains.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
```

Report the Claude verdict, audit result, external artifact hash/path, next
acquisition recommendation, and any genuine operator action required.

## Suggested Commit Message

`Add Tiingo disjoint daily shard`
