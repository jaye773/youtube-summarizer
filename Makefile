.PHONY: help test test-worker test-js test-unit test-integration test-models test-state test-sse test-performance test-slow test-concurrent test-async-full quick-test coverage coverage-worker format lint quality fix clean install run docker-build docker-run all

# Default target
help:
	@echo "YouTube Summarizer - Development Commands"
	@echo "========================================"
	@echo ""
	@echo "Testing:"
	@echo "  make test          Run all tests with pytest"
	@echo "  make test-worker   Run async worker system tests"
	@echo "  make test-js       Run JavaScript/client-side tests" 
	@echo "  make test-unit     Run unit tests only (fast)"
	@echo "  make test-integration  Run integration tests only"
	@echo "  make quick-test    Run essential tests quickly"
	@echo "  make coverage      Run tests with coverage report"
	@echo "  make coverage-worker  Coverage for worker system only"
	@echo ""
	@echo "Specialized Tests:"
	@echo "  make test-models      Test job models and data structures"
	@echo "  make test-state       Test state management and persistence"
	@echo "  make test-sse         Test Server-Sent Events implementation"
	@echo "  make test-performance Test performance and benchmarks"
	@echo "  make test-concurrent  Test thread safety and concurrency"
	@echo "  make test-async-full  Run complete async system test suite"
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

quick-test:
	@export TESTING=true && python3 -m pytest tests/test_job_models.py tests/test_error_handler.py tests/test_app_integration.py -v --tb=short

# Run async worker system tests  
test-worker:
	@echo "Running async worker system tests..."
	@export TESTING=true && python3 -m pytest \
		tests/test_job_models.py \
		tests/test_job_queue.py \
		tests/test_worker_manager.py \
		tests/test_job_state.py \
		tests/test_error_handler.py \
		tests/test_sse_manager.py \
		-v --tb=short

# Run JavaScript/client-side tests
test-js:
	@echo "Running JavaScript tests..."
	@if [ -f "tests/client/run_tests.js" ]; then \
		cd tests/client && ./run_tests.js; \
	else \
		echo "JavaScript tests not available. Install Node.js and npm to run client tests."; \
	fi

# Run unit tests only (fast)
test-unit:
	@echo "Running unit tests only..."
	@export TESTING=true && python3 -m pytest \
		tests/test_job_models.py \
		tests/test_error_handler.py \
		tests/test_job_state.py \
		-v --tb=short -m "not slow and not integration"

# Run integration tests only
test-integration:
	@echo "Running integration tests..."
	@export TESTING=true && python3 -m pytest \
		tests/test_app_integration.py \
		tests/test_async_endpoints.py \
		tests/test_end_to_end.py \
		tests/test_fallback_scenarios.py \
		tests/test_integration.py \
		-v --tb=short

# Run tests with coverage
coverage:
	@export TESTING=true && python3 -m coverage run -m pytest
	@python3 -m coverage report -m
	@python3 -m coverage html
	@echo "Coverage report generated in htmlcov/"

# Coverage for worker system only
coverage-worker:
	@echo "Running coverage for async worker system..."
	@export TESTING=true && python3 -m coverage run --source=job_models,job_queue,worker_manager,job_state,error_handler,sse_manager -m pytest \
		tests/test_job_models.py \
		tests/test_job_queue.py \
		tests/test_worker_manager.py \
		tests/test_job_state.py \
		tests/test_error_handler.py \
		tests/test_sse_manager.py
	@python3 -m coverage report -m --include="job_models.py,job_queue.py,worker_manager.py,job_state.py,error_handler.py,sse_manager.py"
	@python3 -m coverage html --include="job_models.py,job_queue.py,worker_manager.py,job_state.py,error_handler.py,sse_manager.py"
	@echo "Worker system coverage report generated in htmlcov/"

# Specialized test targets
test-models:
	@echo "Running job models tests..."
	@export TESTING=true && python3 -m pytest tests/test_job_models.py -v

test-state:
	@echo "Running state management tests..."
	@export TESTING=true && python3 -m pytest tests/test_job_state.py tests/test_error_handler.py -v

test-sse:
	@echo "Running SSE implementation tests..."
	@export TESTING=true && python3 -m pytest tests/test_sse_manager.py -v

test-performance:
	@echo "Running performance tests..."
	@export TESTING=true && python3 -m pytest -v -m "performance" --tb=short

test-slow:
	@echo "Running slow/integration tests..."
	@export TESTING=true && python3 -m pytest -v -m "slow or integration" --tb=short

test-concurrent:
	@echo "Running concurrency/thread-safety tests..."
	@export TESTING=true && python3 -m pytest -v -k "concurrent or thread" --tb=short

# Run all new async tests with detailed reporting
test-async-full:
	@echo "Running complete async worker system test suite..."
	@echo "This includes unit, integration, performance, and JavaScript tests."
	@export TESTING=true && python3 -m pytest \
		tests/test_job_models.py \
		tests/test_job_queue.py \
		tests/test_worker_manager.py \
		tests/test_job_state.py \
		tests/test_error_handler.py \
		tests/test_sse_manager.py \
		tests/test_app_integration.py \
		tests/test_async_endpoints.py \
		tests/test_end_to_end.py \
		tests/test_fallback_scenarios.py \
		-v --tb=short --durations=10
	@make test-js

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
	@rm -rf tests/client/coverage/ 2>/dev/null || true
	@rm -rf tests/client/test-results/ 2>/dev/null || true
	@rm -rf data/job_state.json 2>/dev/null || true
	@rm -rf data/test_* 2>/dev/null || true
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