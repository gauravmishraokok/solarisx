.PHONY: dev test seed atlas-ping

atlas-ping:
	python -c "import asyncio; from memora.storage.mongo.connection import init_motor, dispose_motor; from memora.core.config import get_settings; s=get_settings(); asyncio.run(init_motor(s.mongodb_url, s.mongodb_db_name)); print('Atlas connection: OK'); asyncio.run(dispose_motor())"

dev:
	poetry run uvicorn memora.api.app:app --reload --port 8000

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
