#!/bin/sh
# API container entrypoint: smart migration + server start.
set -e

echo "▶ Applying database migrations..."
python scripts/migrate.py

echo "▶ Starting FastAPI..."
exec fastapi run api/main.py --host 0.0.0.0 --port 8000
