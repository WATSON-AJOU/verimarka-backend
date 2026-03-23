FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        g++ \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY verimarka-BACKEND/requirements.txt /tmp/backend-requirements.txt
COPY WATSON_WM/img_guard/requirements.gpu.txt /tmp/ai-requirements.txt
RUN pip install --no-cache-dir -r /tmp/backend-requirements.txt \
    && pip install --no-cache-dir -r /tmp/ai-requirements.txt

COPY verimarka-BACKEND /app/verimarka-BACKEND
COPY WATSON_WM /app/WATSON_WM
COPY Blockchain /app/Blockchain

WORKDIR /app/verimarka-BACKEND

ENV AI_MODEL_ROOT=/app/WATSON_WM/img_guard \
    BLOCKCHAIN_INTEGRATION_ROOT=/app/Blockchain/backend_integration

RUN chmod +x /app/verimarka-BACKEND/entrypoint.sh

CMD ["/app/verimarka-BACKEND/entrypoint.sh"]
