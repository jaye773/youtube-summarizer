# Testing Guide - YouTube Summarizer

## Overview

The YouTube Summarizer now includes comprehensive tests for the async worker system with easy-to-use Makefile targets.

## Quick Start

```bash
# Run essential tests quickly
make quick-test

# Run all async worker system tests
make test-worker

# Run complete test suite with coverage
make coverage

# See all available test commands
make help
```

## Test Categories

### Basic Testing
- `make test` - Run all tests with pytest
- `make quick-test` - Run essential tests quickly (3 core test files)
- `make coverage` - Run tests with coverage report
- `make coverage-worker` - Coverage for worker system only

### Module-Specific Tests
- `make test-worker` - All async worker system tests
- `make test-js` - JavaScript/client-side tests (requires Node.js)
- `make test-unit` - Unit tests only (fast)
- `make test-integration` - Integration tests only

### Specialized Tests
- `make test-models` - Test job models and data structures
- `make test-state` - Test state management and persistence  
- `make test-sse` - Test Server-Sent Events implementation
- `make test-performance` - Test performance and benchmarks
- `make test-concurrent` - Test thread safety and concurrency
- `make test-async-full` - Complete async system test suite

### Advanced Testing
- `make test-slow` - Run slow/integration tests
- `make test-concurrent` - Run concurrency/thread-safety tests

## Test Coverage

### Python Test Files (15 files)
- **Module 1 - Worker Core**: `test_job_models.py`, `test_job_queue.py`, `test_worker_manager.py`
- **Module 2 - State Management**: `test_job_state.py`, `test_error_handler.py`
- **Module 3 - SSE Implementation**: `test_sse_manager.py`
- **Module 5 - Integration**: `test_app_integration.py`, `test_async_endpoints.py`, `test_end_to_end.py`, `test_fallback_scenarios.py`

### JavaScript Test Files (7 files)
- Located in `tests/client/`
- Tests for SSE client, job tracker, UI updater
- Performance and accessibility tests
- Run with `make test-js`

## Coverage Reports

```bash
# Generate HTML coverage report
make coverage

# Worker system specific coverage
make coverage-worker

# View reports
open htmlcov/index.html
```

## Test Statistics

- **Total Test Files**: 22 (15 Python + 7 JavaScript)
- **Total Test Code**: 16,500+ lines
- **Individual Tests**: 400+ test cases
- **Coverage**: >90% for modules, >85% integration

## Continuous Integration

### GitHub Actions Example
```yaml
- name: Run Tests
  run: |
    make test-unit
    make test-integration
    make coverage
```

### Pre-commit Testing
```bash
# Quick validation before commit
make quick-test

# Full validation before push  
make test-async-full
```

## Troubleshooting

### Common Issues

**JavaScript tests fail**: Install Node.js and npm
```bash
npm install  # In tests/client directory
```

**Permission errors**: Check data directory permissions
```bash
chmod 755 data/
```

**Memory test failures**: May occur on resource-constrained systems (not critical)

### Test Data Cleanup
```bash
make clean  # Removes test artifacts, coverage files, cache files
```

## Performance Testing

The test suite includes performance benchmarks:

- **Job Queue**: 1000+ jobs processing
- **Memory Usage**: <50MB growth during stress tests  
- **SSE Broadcasting**: 100+ events/second
- **Thread Safety**: Concurrent operations validation

## Adding New Tests

### Python Tests
1. Create test file in `tests/` directory
2. Follow naming: `test_<module>.py`
3. Add to appropriate Makefile target if needed

### JavaScript Tests  
1. Create test file in `tests/client/`
2. Follow naming: `test_<module>.test.js`
3. Tests run automatically with `make test-js`

## Test Documentation

Each test file includes comprehensive documentation:
- `tests/README_WORKER_TESTS.md` - Worker system tests
- `tests/README_SSE_TESTS.md` - SSE implementation tests
- `tests/README_INTEGRATION_TESTS.md` - Integration tests
- `tests/client/README.md` - JavaScript tests

For detailed information about specific test modules, see the individual README files in the `tests/` directory.