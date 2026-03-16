#!/bin/sh
set -eu

echo "[entrypoint] Applying database migrations..."
python manage.py migrate --settings=config.settings.prod --noinput

echo "[entrypoint] Starting gunicorn..."
exec gunicorn config.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers 3 \
  --timeout 120
