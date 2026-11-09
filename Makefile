# Convenience targets (needs `make`; on Windows, run the commands directly instead).
.PHONY: up down test lint reset

up:
	docker compose up --build

down:
	docker compose down

test:
	docker compose run --rm api pytest -q

lint:
	docker compose run --rm api sh -c "ruff check . && mypy app"

# Wipes the database volume and re-seeds from scratch.
reset:
	docker compose down -v && docker compose up --build
