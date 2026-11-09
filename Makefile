# Convenience targets (needs `make`; on Windows, run the commands directly instead).
.PHONY: up down test lint demo loadtest reset

up:
	docker compose up --build

down:
	docker compose down

test:
	docker compose run --rm api pytest -q

lint:
	docker compose run --rm api sh -c "ruff check . && mypy app"
	cd frontend && npm run lint

# Play the scripted Money in Flight story against the running stack and narrate it.
demo:
	docker compose exec api python scripts/demo.py

# k6 load test against the API running with 4 workers (results go in the README).
loadtest:
	UVICORN_ARGS="--workers 4" DB_POOL_SIZE=10 DB_MAX_OVERFLOW=10 docker compose up -d api
	sleep 8
	docker run --rm -i --network tracepay_default -e BASE_URL=http://api:8000 \
		grafana/k6:0.57.0 run - < loadtest/pay.js

# Wipes the database volume and re-seeds from scratch.
reset:
	docker compose down -v && docker compose up --build
