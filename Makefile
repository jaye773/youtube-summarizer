.PHONY: help venv install test quick-test test-browser coverage format lint quality fix clean run docker-build docker-run all

# Use the project's .venv (Python 3.13, created by `make venv`) when it exists
PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
PYTEST = TESTING=true $(PYTHON) -m pytest

help:
	@echo "YouTube Summarizer - Development Commands"
	@echo ""
	@echo "  make venv          Create .venv with Python 3.13 (needs uv) and install dependencies"
	@echo "  make install       Install runtime and dev dependencies"
	@echo "  make test          Run the test suite (browser tests skip without Playwright browsers)"
	@echo "  make quick-test    Run the core app tests only"
	@echo "  make test-browser  Run Playwright browser smoke tests (needs playwright + chromium)"
	@echo "  make coverage      Run tests with an HTML coverage report"
	@echo "  make quality       Run all quality checks (format + lint)"
	@echo "  make format        Check code formatting"
	@echo "  make lint          Run linters"
	@echo "  make fix           Auto-fix formatting"
	@echo "  make run           Run the Flask dev server on :5001"
	@echo "  make docker-build  Build the Docker image"
	@echo "  make docker-run    Run with docker compose"
	@echo "  make clean         Remove caches and generated files"
	@echo "  make all           format + lint + test"

venv:
	uv venv --python 3.13 .venv
	uv pip install --python .venv/bin/python -r requirements.txt -r requirements-dev.txt

install:
	$(PYTHON) -m pip install -r requirements.txt -r requirements-dev.txt

test:
	@$(PYTEST)

quick-test:
	@$(PYTEST) tests/test_app.py tests/test_cache.py tests/test_transcript_and_summary.py tests/test_pagination.py

test-browser:
	@$(PYTHON) -c "import playwright" 2>/dev/null || { echo "Install first: $(PYTHON) -m pip install playwright==1.64.1 && $(PYTHON) -m playwright install chromium"; exit 1; }
	@$(PYTEST) tests/test_browser_smoke.py -v

coverage:
	@TESTING=true $(PYTHON) -m coverage run -m pytest
	@$(PYTHON) -m coverage report -m
	@$(PYTHON) -m coverage html
	@echo "Coverage report generated in htmlcov/"

format:
	@./run_quality_checks.sh --format

lint:
	@./run_quality_checks.sh --lint

quality:
	@./run_quality_checks.sh

fix:
	@./run_quality_checks.sh --fix

clean:
	@find . -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.py[co]" -delete 2>/dev/null || true
	@rm -rf htmlcov/ .pytest_cache/ .mypy_cache/ .coverage coverage.xml 2>/dev/null || true
	@echo "Clean complete!"

run:
	@FLASK_APP=app.py FLASK_DEBUG=true $(PYTHON) -m flask run --port 5001

docker-build:
	docker compose build

docker-run:
	docker compose up

all: format lint test
