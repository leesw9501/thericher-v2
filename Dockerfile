FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN python -m pip install --no-cache-dir --upgrade pip && \
    python -m pip install --no-cache-dir -e .

CMD ["python", "-m", "thericher_v2.ops.daily_report", "--print-summary"]

FROM base AS research

RUN python -m pip install --no-cache-dir -e ".[research]"

FROM base AS runtime
