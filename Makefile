.PHONY: setup dev test lint typecheck demo clean

# ── Setup ──────────────────────────────────────────────────────────────────────
setup:
	@echo "▶ Setting up Python environment..."
	uv venv
	uv pip install --python .venv/bin/python -e ".[dev]"
	@echo "▶ Setting up JS environment..."
	npm ci
	@echo "▶ Copying .env.example → .env (if not present)..."
	cp -n .env.example .env || true
	@echo "▶ Installing pre-commit hooks..."
	.venv/bin/pre-commit install
	@echo "✅ Setup complete. Edit .env before running 'make dev'."

# ── Development servers ────────────────────────────────────────────────────────
dev:
	docker compose up --build

dev-api:
	.venv/bin/uvicorn services.api.main:app --reload --host 0.0.0.0 --port 8000

dev-worker:
	.venv/bin/celery -A services.worker.celery_app worker --loglevel=info

dev-web:
	npm run dev --workspace=apps/web

# ── Database ───────────────────────────────────────────────────────────────────
db-migrate:
	.venv/bin/alembic upgrade head

db-rollback:
	.venv/bin/alembic downgrade -1

db-revision:
	.venv/bin/alembic revision --autogenerate -m "$(msg)"

# ── Tests ──────────────────────────────────────────────────────────────────────
test:
	.venv/bin/pytest -x --tb=short

test-engine:
	.venv/bin/pytest engine/ -x --tb=short

test-api:
	.venv/bin/pytest services/api/ -x --tb=short

test-cov:
	.venv/bin/pytest --cov=. --cov-report=html

# ── Lint & Typecheck ──────────────────────────────────────────────────────────
lint:
	.venv/bin/ruff check .
	.venv/bin/ruff format --check .
	npm run lint --workspace=apps/web

format:
	.venv/bin/ruff check --fix .
	.venv/bin/ruff format .

typecheck:
	mypy services/ engine/
	npm run typecheck --workspace=apps/web

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
