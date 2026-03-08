.PHONY: help install-core run-core test-core lint-core format-core precommit-install

help:
	@echo "Targets:"
	@echo "  install-core        Install Python dependencies for nasri-core"
	@echo "  run-core            Run FastAPI app"
	@echo "  test-core           Run tests"
	@echo "  lint-core           Run lint checks"
	@echo "  format-core         Format code"
	@echo "  precommit-install   Install git pre-commit hook"

install-core:
	pip install -r nasri-core/requirements.txt

run-core:
	uvicorn app.main:app --app-dir nasri-core --reload --host 0.0.0.0 --port 8000

test-core:
	pytest -q nasri-core/tests

lint-core:
	ruff check nasri-core/app nasri-core/tests

format-core:
	ruff format nasri-core/app nasri-core/tests

precommit-install:
	pre-commit install
