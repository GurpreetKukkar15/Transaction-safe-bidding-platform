.PHONY: setup db-up app-up down migrate lint test test-unit test-integration benchmark-smoke

setup:
	python3 -m venv .venv
	.venv/bin/python -m pip install -r requirements/dev.lock
	.venv/bin/python -m pip install --no-deps -e .

db-up:
	docker compose up -d --wait db

app-up:
	docker compose up -d --build --wait app

down:
	docker compose down

migrate:
	.venv/bin/bidding-migrate

lint:
	.venv/bin/ruff format --check .
	.venv/bin/ruff check .

test: lint
	TEST_DATABASE_URL=postgresql://bidding:bidding@localhost:54329/bidding_test .venv/bin/python -m pytest

test-unit:
	.venv/bin/python -m pytest -m 'not integration'

test-integration:
	TEST_DATABASE_URL=postgresql://bidding:bidding@localhost:54329/bidding_test .venv/bin/python -m pytest -m integration

benchmark-smoke:
	.venv/bin/bidding-benchmark --database-url postgresql://bidding:bidding@localhost:54329/bidding_test --concurrency 8 --requests 30 --repetitions 3 --warmup-requests 8 --output benchmark-results/smoke.json
