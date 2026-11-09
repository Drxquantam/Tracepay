#!/bin/sh
# Container entrypoint: bring the schema up to date, seed demo data (safe to repeat), then serve.
set -e
alembic upgrade head
python -m app.seed
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
