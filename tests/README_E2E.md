# End-to-End Integration Tests

This directory contains E2E tests that verify the service logging functionality works end-to-end with MonkAI.

## Running E2E Tests

E2E tests require actual MonkAI credentials and network connectivity. They are marked with `@pytest.mark.e2e`.

### Setup

Set the following environment variables:

```bash
export MONKAI_TEST_TOKEN="tk_your_test_token"
export MONKAI_TEST_NAMESPACE="e2e-test-service"  # Optional, defaults to this
```

### Run All Tests

```bash
# Run all tests including E2E
pytest tests/ -v

# Run only E2E tests
pytest tests/ -v -m e2e

# Skip E2E tests (useful for CI without credentials)
pytest tests/ -v -m "not e2e"
```

### Run Specific E2E Tests

```bash
# Run only service logging E2E tests
pytest tests/test_service_logging_e2e.py -v -s

# Run specific test
pytest tests/test_service_logging_e2e.py::test_service_logging_basic_execution -v -s
```

## E2E Test Coverage

The E2E tests verify:

1. **Basic Execution** (`test_service_logging_basic_execution`)
   - Service can start and run
   - Graceful shutdown works
   - Output contains expected messages

2. **SIGTERM Handling** (`test_service_logging_sigterm_handling`)
   - Service responds to SIGTERM (systemd/docker stop)
   - Logs are flushed on shutdown
   - Exit code is clean

3. **Periodic Flush** (`test_service_logging_periodic_flush`)
   - Logs are uploaded even with low volume (< batch_size)
   - Periodic flush mechanism works
   - Verifies logs reach MonkAI

4. **ServiceLogger Integration** (`test_service_logger_class_integration`)
   - Direct usage of ServiceLogger class
   - Multiple log levels work
   - Exception logging works
   - Manual flush works

5. **Multiple Shutdown Signals** (`test_service_multiple_shutdown_signals`)
   - Service handles repeated signals gracefully
   - No hanging or zombie processes

6. **Exception Handling** (`test_service_logging_with_exception_handling`)
   - Exceptions are properly logged
   - Service continues after exceptions
   - Full tracebacks are captured

## CI/CD Integration

In CI environments without MonkAI credentials:

```yaml
# GitHub Actions example
- name: Run tests (skip E2E)
  run: pytest -v -m "not e2e"
```

With credentials (secure environment):

```yaml
- name: Run all tests including E2E
  env:
    MONKAI_TEST_TOKEN: ${{ secrets.MONKAI_TEST_TOKEN }}
  run: pytest -v
```

## Troubleshooting

**Tests are skipped:**
- Ensure `MONKAI_TEST_TOKEN` environment variable is set
- Check token is valid

**Tests timeout:**
- Check network connectivity to MonkAI API
- Increase timeout values if network is slow

**Logs not found in MonkAI:**
- Wait a few seconds after test completion
- Check the correct namespace in MonkAI dashboard
- Verify token has write permissions

## Writing New E2E Tests

When adding new E2E tests:

1. **Mark with `@pytest.mark.e2e`**
   ```python
   @pytest.mark.e2e
   def test_my_feature(monkai_credentials, monkai_client):
       ...
## OpenAI Agents E2E Tests

### Overview

E2E tests for `MonkAIRunHooks` verify that OpenAI agent conversations are tracked and uploaded to MonkAI correctly.

### Additional Requirements

- `openai-agents-python` library installed
- Valid OpenAI API key in `OPENAI_API_KEY` environment variable
- MonkAI test token in `MONKAI_TEST_TOKEN` environment variable

⚠️ **Warning**: These tests make real API calls to OpenAI and will consume tokens.

### Setup

```bash
# Install OpenAI agents library
pip install openai-agents-python

# Set credentials
export OPENAI_API_KEY="sk-..."
export MONKAI_TEST_TOKEN="tk_your_test_token"
export MONKAI_TEST_NAMESPACE="e2e-test-openai-agents"  # Optional
```

### Running Tests

```bash
# Run all OpenAI Agents E2E tests
pytest tests/test_openai_agents_e2e.py -v -m e2e

# Run specific test
pytest tests/test_openai_agents_e2e.py::test_basic_conversation_reaches_monkai -v

# Skip OpenAI tests (if no API key)
pytest tests/ -v -m "not e2e"

# Run only OpenAI tests (skip service logging tests)
pytest tests/test_openai_agents_e2e.py -v -m e2e
```

### Test Coverage

The OpenAI Agents E2E tests verify:

1. **Basic Conversation** (`test_basic_conversation_reaches_monkai`)
   - Single agent Q&A tracked correctly
   - User messages captured automatically
   - Token usage reported accurately
   - Data reaches MonkAI

2. **Multi-Agent Handoffs** (`test_multi_agent_handoff_tracking`)
   - Triage → Specialist agent routing
   - Transfer objects created correctly
   - Multiple agents tracked separately
   - Token usage per agent

3. **Batch Upload** (`test_batch_upload_mechanism`)
   - Multiple conversations batched correctly
   - All records uploaded when threshold met
   - Data integrity maintained

4. **User Input Capture** (`test_user_input_capture_methods`)
   - `run_with_tracking()` method works
   - `set_user_input()` method works
   - Both methods capture user messages

5. **Token Accuracy** (`test_token_usage_accuracy`)
   - Input/output tokens segmented correctly
   - Process tokens calculated
   - Total tokens = sum of components

6. **Session Continuity** (`test_session_continuity`)
   - Session IDs maintained within run
   - Session IDs reset between runs

### Test Data Verification

The tests use a `MonkAIDataVerifier` helper class to:
- Poll MonkAI for conversation records
- Validate conversation structure
- Verify token usage breakdown
- Check Transfer objects for handoffs

### CI/CD Integration

In CI environments with OpenAI API key:

```yaml
- name: Run OpenAI E2E tests
  env:
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
    MONKAI_TEST_TOKEN: ${{ secrets.MONKAI_TEST_TOKEN }}
  run: pytest tests/test_openai_agents_e2e.py -v -m e2e
```

Without OpenAI API key (skip these tests):

```yaml
- name: Run tests (skip OpenAI E2E)
  run: pytest -v -m "not e2e"
```

### Troubleshooting

**Tests are skipped:**
- Ensure both `OPENAI_API_KEY` and `MONKAI_TEST_TOKEN` are set
- Verify OpenAI API key is valid and has credits

**Tests timeout:**
- Check network connectivity
- Verify OpenAI API is accessible
- Check MonkAI API endpoint

**No records found in MonkAI:**
- Wait longer (increase timeout in test)
- Check namespace matches
- Verify token has write permissions
- Check MonkAI dashboard for errors

**OpenAI API errors:**
- Check API key validity
- Verify account has sufficient credits
- Check rate limits

### Writing New OpenAI E2E Tests

When adding new E2E tests:

1. **Mark with `@pytest.mark.e2e`**
   ```python
   @pytest.mark.e2e
   def test_my_feature(monkai_credentials, monkai_client):
       ...
   ```

2. **Use provided fixtures**
   - `monkai_credentials`: Test credentials from environment
   - `monkai_client`: Configured MonkAIClient instance
   - `test_namespace`: Unique namespace per test

3. **Use MonkAIDataVerifier for validation**
   ```python
   verifier = MonkAIDataVerifier(monkai_client, test_namespace)
   records = verifier.wait_for_records(min_count=1, timeout=30)
   verifier.verify_conversation_structure(records[0])
   ```

4. **Handle timeouts gracefully**
   - Set reasonable timeouts
   - Clean up resources on failure
   - Log output for debugging

5. **Consider token costs**
   - Use simple prompts where possible
   - Don't run unnecessary conversations
   - Mark expensive tests with `@pytest.mark.slow`


2. **Use provided fixtures**
   - `monkai_credentials`: Test credentials from environment
   - `monkai_client`: Configured MonkAIClient instance
   - `service_process`: Manages subprocess lifecycle

3. **Clean up resources**
   - Use fixtures for automatic cleanup
   - Ensure no orphaned processes

4. **Keep tests independent**
   - Each test should be runnable alone
   - Don't depend on execution order

5. **Handle timeouts**
   - Set reasonable timeouts
   - Clean up on timeout/failure
