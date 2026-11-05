# SPDX-License-Identifier: Apache-2.0
# models-aux (M0.4): CPU-only torch from the PyTorch CPU index (via uv.lock). Model weights are
# not in the image; they are mounted read-only at /models (make models-download), and the
# service runs offline, so it never downloads anything itself. Images pinned by digest (SEC-13).
FROM ghcr.io/astral-sh/uv:0.12.24@sha256:3af4716e991d6956a41e573eab705d0ee08500cd829ed30293eb8472f372c65a AS uv

FROM python:3.12-slim@sha256:b18b261e1b4974b4f321451ad5251ded85abb22c2b8b262da527dda1d031ab30
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH=/app/.venv/bin:$PATH \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    HF_HUB_DISABLE_TELEMETRY=1 \
    MODELS_AUX_CACHE_DIR=/models \
    MODELS_AUX_HOST=0.0.0.0
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages packages
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package models-aux --no-editable
COPY configs/models_aux.yaml configs/models_aux.yaml
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app
USER 10001
EXPOSE 8070
CMD ["python", "-m", "models_aux"]
