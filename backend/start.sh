#!/bin/sh
# Container entrypoint: bring the schema up to date, seed demo data (safe to repeat), then serve.
#
# UVICORN_ARGS picks the server mode:
#   default "--reload"   one process that restarts on code changes (development)
#   "--workers 4"        four processes, like production (used for the load test)
# Several workers are safe: every background job uses SKIP LOCKED and unique constraints.
set -e
alembic upgrade head
python -m app.seed
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 ${UVICORN_ARGS:---reload}
