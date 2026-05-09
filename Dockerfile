# syntax=docker/dockerfile:1.7

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean \
    && echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        fontconfig \
        fonts-noto-cjk \
        gcc \
        g++ \
        libgl1 \
        libglib2.0-0 \
        libreoffice-writer

COPY verimarka-BACKEND/requirements.txt /tmp/backend-requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    pip install -r /tmp/backend-requirements.txt

COPY WATSON_WM/img_guard/requirements.cpu.txt /tmp/img_guard/requirements.cpu.txt
COPY WATSON_WM/img_guard/requirements.txt /tmp/img_guard/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    pip install -r /tmp/img_guard/requirements.cpu.txt

COPY WATSON_WM/img_guard/third_party/watermark-anything/requirements.txt /tmp/watermark-anything/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    pip install -r /tmp/watermark-anything/requirements.txt

COPY verimarka-BACKEND /app/verimarka-BACKEND
COPY WATSON_WM /app/WATSON_WM
COPY Blockchain /app/Blockchain
COPY --chmod=755 verimarka-BACKEND/entrypoint.sh /app/verimarka-BACKEND/entrypoint.sh

WORKDIR /app/verimarka-BACKEND

ENV AI_MODEL_ROOT=/app/WATSON_WM/img_guard \
    BLOCKCHAIN_INTEGRATION_ROOT=/app/Blockchain/backend_integration

CMD ["/app/verimarka-BACKEND/entrypoint.sh"]
