# Next Codex Goal

## Objective

Produce one source-safe `prospective-spy-observation-receipt-v1` from the next
eligible completed SPY regular-session cache window, using the already prepared
Data-owned capture runner. This advances prospective observation collection;
it is not model promotion, a Paper order, or a profitability claim.

## Fixed Boundaries

- Run only `scripts/capture_kis_paper_prospective_spy_observation.py` against
  the existing verified `SPY/AMS/1m` local cache after its 15:30 ET cutoff and
  on the same America/New_York date. The head collector alone owns cache
  mutation and any KIS market-data activity.
- The runner reads no `.env`, creates no client, performs no network call, and
  may write exactly one source-safe receipt under
  `D:\thericher-v2\model-artifacts`. Raw bars stay on `D:`.
- A missing, stale, incomplete, or non-regular session returns only its scoped
  categorical observation result. It must not make Codex wait, alter the
  collector, or block independent work.
- Do not read accounts, private intents, broker bodies, credentials, or
  `KIS_LIVE_*`; do not create a local/Paper/live order, dashboard, public
  service, model result, GPU appointment, or PnL claim.

## Completion

- One immutable receipt records only structural/session identities, source and
  record commitments, and the fixed baseline's categorical `enter` or
  `abstain` decision; no raw OHLCV, account, order, or fill data is retained.
- If no eligible window exists, preserve the exact categorical result and
  continue the next non-conflicting ready package without foreground waiting.
- Refresh this file with exactly one next objective, verify changed paths,
  commit, and push the bounded objective.

## Verification

```powershell
uv run --extra dev pytest -q tests/test_kis_paper_prospective_spy_capture.py
uv run --extra dev ruff check .
```
