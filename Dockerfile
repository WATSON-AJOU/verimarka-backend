FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY verimarka-BACKEND/requirements.txt /tmp/backend-requirements.txt
COPY WATSON_WM/img_guard/requirements.txt /tmp/ai-requirements.txt
RUN pip install --no-cache-dir -r /tmp/backend-requirements.txt \
    && pip install --no-cache-dir -r /tmp/ai-requirements.txt

COPY verimarka-BACKEND /app/verimarka-BACKEND
COPY WATSON_WM /app/WATSON_WM

WORKDIR /app/verimarka-BACKEND

ENV AI_MODEL_ROOT=/app/WATSON_WM/img_guard

RUN chmod +x /app/verimarka-BACKEND/entrypoint.sh

CMD ["/app/verimarka-BACKEND/entrypoint.sh"]
