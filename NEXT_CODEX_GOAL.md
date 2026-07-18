# Next Codex Goal

## Objective

Resolve one operator decision before beginning the next data-collection task:
whether to use a free Norgate US Stocks Platinum trial to validate a potential
US daily point-in-time research source.

This advances the data-collection and backtest-validation loop. It is not a
provider implementation, model task, trading milestone, or data purchase.

## Operator Decision Required

Approve or reject this exact action:

> Approve a free three-week Norgate US Stocks Platinum trial, using my own
> identity and accepting Norgate's EULA, solely to verify the Windows-Python
> research boundary, PIT membership/delisting access, no-adjustment OHLCV, and
> corporate-action fields. Do not purchase the USD 346.50 six-month subscription
> or download data into the project until I approve a later scoped step.

The operator must create the vendor account and accept the external terms. On
approval, report only that the trial is ready; do not share credentials.

## Boundaries

- Do not create an account, log in, enter identity, payment, or credential
  details, accept external terms, purchase, download, query an API, or read
  `.env` until the operator explicitly approves the trial.
- Do not add a provider, cache, data artifact, dependency, campaign, model,
  GPU job, paper order, KIS access, or live behavior.
- Keep `THERICHER_MODE=off`; no broker submission or capital allocation.
- Do not represent a trial, Norgate, Sharadar, Tiingo IEX r1, or existing Yahoo
  data as independent validation or profitability evidence.

## After Approval

Start one new bounded Data objective to assess only the operator-created trial:
Windows-Python connectivity, the documented no-adjustment price/volume mode,
event fields, per-date membership/delisting semantics, export constraints,
license-compliant `D:\market_data` placement, and the local/Docker boundary.
The trial has only two years of price history and cannot itself open long-period
model validation or authorize a paid subscription.

## Verification

Before ending any subsequent bounded objective, run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
```

## Suggested Commit Message

`Evaluate approved Norgate Platinum trial`
