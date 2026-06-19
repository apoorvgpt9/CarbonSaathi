PYTHON := python3
APP := app.main:app
IMAGE := carbonsaathi:local
PORT := 8080

.PHONY: help install run test lint format typecheck security all clean docker-build docker-run

help:
	@echo "Available targets:"
	@echo "  install       Install the package with dev extras and pre-commit hooks"
	@echo "  run           Run the uvicorn dev server on :$(PORT)"
	@echo "  test          Run the test suite with coverage"
	@echo "  lint          Run ruff checks"
	@echo "  format        Auto-format with ruff and black"
	@echo "  typecheck     Run mypy --strict"
	@echo "  security      Run bandit and pip-audit"
	@echo "  all           Run lint, typecheck, test, and security"
	@echo "  clean         Remove caches and build artifacts"
	@echo "  docker-build  Build the container image"
	@echo "  docker-run    Run the container image locally"

install:
	$(PYTHON) -m pip install -e ".[dev]"
	pre-commit install

run:
	$(PYTHON) -m uvicorn $(APP) --reload --host 0.0.0.0 --port $(PORT)

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check .

format:
	$(PYTHON) -m ruff check --fix .
	$(PYTHON) -m black .

typecheck:
	$(PYTHON) -m mypy app

security:
	$(PYTHON) -m bandit -c pyproject.toml -r app
	$(PYTHON) -m pip_audit

all: lint typecheck test security

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage .coverage.* \
		build dist *.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +

docker-build:
	docker build -t $(IMAGE) .

docker-run:
	docker run --rm -p $(PORT):$(PORT) --env-file .env $(IMAGE)
