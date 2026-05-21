.DEFAULT_GOAL := help
PYTHON        := uv run python
PYTEST        := uv run pytest
MYPY          := uv run mypy
RUFF          := uv run ruff

.PHONY: help install test test-fast test-unit test-integration lint lint-full type format clean coverage coverage-check coverage-unit coverage-integration docs docs-serve build check publish-test publish-test-upload publish release-check release-check-testpypi

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

install: ## Install all dependencies (dev + docs)
	uv sync --all-extras

test: ## Run full test suite with coverage
	$(PYTEST) tests/

test-fast: ## Run tests without coverage (faster feedback loop)
	$(PYTEST) tests/ --no-cov -q

test-unit: ## Run unit tests only
	$(PYTEST) tests/unit/ --no-cov -q

test-integration: ## Run integration tests only
	$(PYTEST) tests/integration/ --no-cov -q

lint: ## Lint with ruff using CI rule-set (F,E9,W,E,I,B,UP) — matches CI
	$(RUFF) check src tests --select F,E9,W,E,I,B,UP --ignore E501 --fix
	$(RUFF) format src tests

lint-full: ## Lint with all configured ruff rules (informational, may surface existing issues)
	$(RUFF) check src tests --fix || true
	$(RUFF) format src tests

type: ## Static type check with mypy (strict)
	$(MYPY) src/robot_optimizer_core

format: ## Format code with ruff
	$(RUFF) format src tests

coverage: ## Run full test suite with HTML coverage report
	$(PYTEST) tests/ --cov-report=html
	@echo "Coverage report: htmlcov/index.html"

coverage-check: ## Enforce per-file coverage minimums (reads coverage.xml)
	$(PYTHON) ci/check_per_file_coverage.py

coverage-unit: ## Unit-tier coverage report (no aggregate threshold enforced)
	$(PYTEST) -m unit --cov-report=term-missing:skip-covered --cov-report=html:htmlcov-unit --no-cov-on-fail --override-ini="addopts=--cov=robot_optimizer_core --cov-branch --cov-report=term-missing:skip-covered --cov-report=html:htmlcov-unit --cov-report=xml:coverage-unit.xml" -q
	@echo "Unit coverage report: htmlcov-unit/index.html"

coverage-integration: ## Integration-tier coverage report (no aggregate threshold enforced)
	$(PYTEST) -m integration --cov-report=term-missing:skip-covered --cov-report=html:htmlcov-integration --no-cov-on-fail --override-ini="addopts=--cov=robot_optimizer_core --cov-branch --cov-report=term-missing:skip-covered --cov-report=html:htmlcov-integration --cov-report=xml:coverage-integration.xml" -q
	@echo "Integration coverage report: htmlcov-integration/index.html"

clean: ## Remove build artefacts, caches, and coverage files
	rm -rf build dist *.egg-info
	rm -rf htmlcov .coverage coverage.xml
	rm -rf .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

docs: ## Build documentation
	uv run mkdocs build --clean --strict

docs-serve: ## Serve documentation locally
	uv run mkdocs serve

build: ## Build sdist and wheel
	uv run python -m build

publish-test: clean build ## Build and validate package metadata (true dry-run)
	uv run python -m twine check dist/*
	@echo "Dry-run OK. TestPyPI URL (post-upload): https://test.pypi.org/project/robot-framework-optimizer-core/"

publish-test-upload: clean build ## Build and upload to TestPyPI
	uv run twine upload --repository testpypi dist/*
	@echo "TestPyPI URL: https://test.pypi.org/project/robot-framework-optimizer-core/"

publish: ## Build and upload to PyPI (requires confirmation)
	@read -p "Publish to PyPI? [y/N] " ans; \
	  if [ "$$ans" = "y" ] || [ "$$ans" = "Y" ]; then \
	    $(MAKE) clean build && uv run twine upload dist/*; \
	    echo "Published: https://pypi.org/project/robot-framework-optimizer-core/"; \
	  else \
	    echo "Aborted."; \
	  fi

check: lint type test-fast ## Run lint + type + fast tests (pre-PR sanity check)


release-check: ## Validate distribution metadata locally
	uv run python -m build
	uv run python -m twine check dist/*

release-check-testpypi: release-check ## Show TestPyPI project URL after validation
	@echo "TestPyPI URL: https://test.pypi.org/project/robot-framework-optimizer-core/"
