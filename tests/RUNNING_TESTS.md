# Running Tests

This document covers running the MonkAI Trace Python SDK tests.

## Test Structure

- **Unit tests**: Fast tests that mock external dependencies
- **E2E tests**: Integration tests that require MonkAI credentials

## Quick Start

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run all tests (skips E2E without credentials)
pytest

# Run with verbose output
pytest -v

# Run with coverage report
pytest --cov=monkai_trace --cov-report=html
```

## Unit Tests

Unit tests run quickly and don't require external services:

```bash
# Run only unit tests (exclude E2E)
pytest -m "not e2e" -v

# Run specific test file
pytest tests/test_client.py -v

# Run specific test
pytest tests/test_client.py::test_upload_record -v
```

## E2E Tests

E2E tests require MonkAI credentials:

```bash
# Set credentials
export MONKAI_TEST_TOKEN="tk_your_test_token"
export MONKAI_TEST_NAMESPACE="e2e-test-service"  # Optional

# Run E2E tests
pytest -m e2e -v -s

# Run specific E2E test file
pytest tests/test_service_logging_e2e.py -v -s
```

See [tests/README_E2E.md](tests/README_E2E.md) for detailed E2E test documentation.

## Test Markers

Tests are marked with pytest markers:

- `@pytest.mark.e2e`: End-to-end integration tests
- `@pytest.mark.slow`: Tests that take >5 seconds

```bash
# Run only E2E tests
pytest -m e2e

# Skip E2E tests
pytest -m "not e2e"

# Skip slow tests
pytest -m "not slow"
```

## Coverage

Generate coverage reports:

```bash
# Terminal report
pytest --cov=monkai_trace --cov-report=term-missing

# HTML report (opens in browser)
pytest --cov=monkai_trace --cov-report=html
open htmlcov/index.html
```

## Continuous Integration

For CI environments:

```bash
# Skip E2E tests (no credentials)
pytest -v -m "not e2e" --cov=monkai_trace

# With credentials (secure environment)
MONKAI_TEST_TOKEN=$SECRET_TOKEN pytest -v
## OpenAI Agents E2E Tests

OpenAI Agents E2E tests require additional setup and credentials.

### Prerequisites

```bash
# Install OpenAI agents library
pip install openai-agents-python

# Required environment variables
export OPENAI_API_KEY="sk-..."           # Your OpenAI API key
export MONKAI_TEST_TOKEN="tk_..."        # MonkAI test token
export MONKAI_TEST_NAMESPACE="e2e-test"  # Optional
```

⚠️ **Token Costs**: These tests make real OpenAI API calls and will consume tokens.

### Running OpenAI E2E Tests

```bash
# Run all OpenAI Agents E2E tests
pytest tests/test_openai_agents_e2e.py -v -m e2e

# Run specific test
pytest tests/test_openai_agents_e2e.py::test_basic_conversation_reaches_monkai -v

# Run with detailed output
pytest tests/test_openai_agents_e2e.py -v -m e2e -s
```

### Skipping OpenAI Tests

```bash
# Skip all E2E tests (including OpenAI)
pytest -v -m "not e2e"

# Run only service logging E2E tests (skip OpenAI)
pytest tests/test_service_logging_e2e.py -v -m e2e
```

### CI/CD with OpenAI Tests

**With OpenAI credentials:**
```yaml
- name: Run all E2E tests
  env:
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
    MONKAI_TEST_TOKEN: ${{ secrets.MONKAI_TEST_TOKEN }}
  run: pytest -v -m e2e
```

**Without OpenAI credentials:**
```yaml
- name: Run service logging E2E only
  env:
    MONKAI_TEST_TOKEN: ${{ secrets.MONKAI_TEST_TOKEN }}
  run: pytest tests/test_service_logging_e2e.py -v -m e2e
```



## Troubleshooting

**Import errors:**
```bash
pip install -e ".[dev]"
```

**E2E tests skipped:**
```bash
export MONKAI_TEST_TOKEN="your_token"
pytest -m e2e -v
```

**Tests hanging:**
- Check network connectivity
- Increase timeouts
- Use `-s` flag to see output

## Writing Tests

### Unit Test Example

```python
from unittest.mock import Mock, patch
import pytest

def test_my_feature(mock_client):
    # Use mocks for external dependencies
    with patch('module.dependency') as mock_dep:
        # Test logic
        assert result == expected
```

### E2E Test Example

```python
@pytest.mark.e2e
def test_integration(monkai_credentials, monkai_client):
    # Use real MonkAI client
    client = monkai_client
    
    # Test actual functionality
    result = client.upload_log(...)
    assert result.success
```

## Test Organization

```
tests/
├── README_E2E.md              # E2E test documentation
├── conftest.py                # Shared fixtures
├── test_client.py             # Client unit tests
├── test_logging_integration.py # Logging unit tests
├── test_service_logging_e2e.py # Service E2E tests
└── ...
```

## Running Specific Test Types

```bash
# Only logging tests
pytest tests/test_logging* -v

# Only service tests
pytest tests/*service* -v

# Fast tests only
pytest -m "not slow and not e2e" -v
```
