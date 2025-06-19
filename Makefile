.PHONY: help test quick-test format lint coverage clean install run docker-build docker-run all quality fix

# Default target
help:
	@echo "YouTube Summarizer - Development Commands"
	@echo "========================================"
	@echo ""
	@echo "Testing:"
	@echo "  make test          Run all tests with pytest"
	@echo "  make quick-test    Run tests quickly (alias for test)"
	@echo "  make coverage      Run tests with coverage report"
	@echo ""
	@echo "Code Quality:"
	@echo "  make quality       Run all quality checks"
	@echo "  make format        Check code formatting"
	@echo "  make lint          Run linting checks (pylint, flake8)"
	@echo "  make fix           Auto-fix formatting issues"
	@echo ""
	@echo "Development:"
	@echo "  make install       Install all dependencies"
	@echo "  make run           Run the Flask app locally"
	@echo "  make clean         Clean up cache files"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-build  Build Docker image"
	@echo "  make docker-run    Run with docker-compose"
	@echo ""
	@echo "Combined:"
	@echo "  make all           Run format, lint, and test"

# Install dependencies
install:
	pip3 install -r requirements.txt
	pip3 install -r requirements-dev.txt

# Run tests
test:
	@export TESTING=true && python3 -m pytest -v

quick-test: test

# Run tests with coverage
coverage:
	@export TESTING=true && python3 -m coverage run -m pytest
	@python3 -m coverage report -m
	@python3 -m coverage html
	@echo "Coverage report generated in htmlcov/"

# Code formatting check
format:
	@./run_quality_checks.sh --format

# Linting
lint:
	@./run_quality_checks.sh --lint

# Run all quality checks
quality:
	@./run_quality_checks.sh

# Auto-fix formatting issues
fix:
	@./run_quality_checks.sh --fix

# Clean up cache files
clean:
	@echo "Cleaning up cache files..."
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@find . -type f -name "*.pyo" -delete 2>/dev/null || true
	@find . -type f -name ".coverage" -delete 2>/dev/null || true
	@rm -rf htmlcov/ 2>/dev/null || true
	@rm -rf .pytest_cache/ 2>/dev/null || true
	@rm -rf .mypy_cache/ 2>/dev/null || true
	@echo "Clean complete!"

# Run Flask app
run:
	@export FLASK_APP=app.py && export FLASK_ENV=development && python3 -m flask run --port 5001

# Docker commands
docker-build:
	docker-compose build

docker-run:
	docker-compose up

# Run everything
all: format lint test 