.PHONY: setup dev test lint typecheck demo clean

# ── Setup ──────────────────────────────────────────────────────────────────────
setup:
	@echo "▶ Setting up Python environment..."
	uv venv
	uv pip install -e ".[dev]"
	@echo "▶ Setting up JS environment..."
	pnpm install
	@echo "▶ Copying .env.example → .env (if not present)..."
	cp -n .env.example .env || true
	@echo "▶ Installing pre-commit hooks..."
	pre-commit install
	@echo "✅ Setup complete. Edit .env before running 'make dev'."

# ── Development servers ────────────────────────────────────────────────────────
dev:
	docker-compose up --build

dev-api:
	uvicorn services.api.main:app --reload --host 0.0.0.0 --port 8000

dev-worker:
	celery -A services.worker.celery_app worker --loglevel=info

dev-web:
	pnpm --filter web dev

# ── Database ───────────────────────────────────────────────────────────────────
db-migrate:
	alembic upgrade head

db-rollback:
	alembic downgrade -1

db-revision:
	alembic revision --autogenerate -m "$(msg)"

# ── Tests ──────────────────────────────────────────────────────────────────────
test:
	pytest -x --tb=short

test-engine:
	pytest engine/ -x --tb=short

test-api:
	pytest services/api/ -x --tb=short

test-cov:
	pytest --cov=. --cov-report=html

# ── Lint & Typecheck ──────────────────────────────────────────────────────────
lint:
	ruff check .
	ruff format --check .
	pnpm --filter web lint

format:
	ruff check --fix .
	ruff format .

typecheck:
	mypy services/ engine/
	pnpm --filter web typecheck

# ── Demo ───────────────────────────────────────────────────────────────────────
demo:
	@echo "▶ Running smoke test on staged fixture..."
	python scripts/smoke_demo.py fixtures/staged/junction_nearMiss_01/

integrity-check:
	@echo "▶ Verifying all fixture hashes..."
	python scripts/verify_integrity.py fixtures/

# ── Clean ─────────────────────────────────────────────────────────────────────
clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -name "*.pyc" -delete
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
	rm -rf apps/web/.next apps/web/node_modules
