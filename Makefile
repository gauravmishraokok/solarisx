.PHONY: dev test migrate seed

dev:
	docker-compose up -d
	poetry run uvicorn memora.api.app:app --reload --port 8000

migrate:
	poetry run alembic upgrade head

seed:
	poetry run python scripts/seed_demo_data.py

test:
	poetry run pytest tests/ -v

test-unit:
	poetry run pytest tests/unit/ -v

test-integration:
	poetry run pytest tests/integration/ -v

frontend:
	cd frontend && npm install && npm run dev
