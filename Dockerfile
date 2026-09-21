# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src

WORKDIR /app

COPY pyproject.toml README.md uv.lock ./
COPY requirements/runtime.lock /tmp/runtime.lock

RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --require-hashes -r /tmp/runtime.lock

COPY src ./src
COPY scripts ./scripts

RUN python -c "import pandas_market_calendars; import thericher_v2"

CMD ["python", "-m", "thericher_v2.ops.daily_report", "--print-summary"]

FROM base AS research

ARG PYTORCH_VERSION=2.7.0+cu128
ARG PYTORCH_CUDA_INDEX_URL=https://download.pytorch.org/whl/cu128

RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install \
        "torch==${PYTORCH_VERSION}" \
        --index-url "${PYTORCH_CUDA_INDEX_URL}" && \
    python -m pip install -e ".[research]"

FROM research AS granite-ttm-runtime

COPY requirements/granite-ttm-runtime.lock /tmp/granite-ttm-runtime.lock

RUN --mount=type=cache,target=/root/.cache/pip \
    python -m venv --system-site-packages /opt/granite-venv && \
    /opt/granite-venv/bin/python -m pip install --no-deps \
        -r /tmp/granite-ttm-runtime.lock && \
    /opt/granite-venv/bin/python -m pip check && \
    /opt/granite-venv/bin/python -c "import sys; import torch; assert sys.version_info[:2] == (3, 12), sys.version; assert torch.__version__ == '2.7.0+cu128', torch.__version__; assert torch.version.cuda == '12.8', torch.version.cuda; from tsfm_public.models.tinytimemixer import TinyTimeMixerForPrediction"

ENV PATH="/opt/granite-venv/bin:${PATH}"

FROM base AS runtime
