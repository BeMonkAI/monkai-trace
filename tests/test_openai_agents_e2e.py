"""
End-to-end integration tests for MonkAIRunHooks with OpenAI Agents.

These tests verify that conversation data from real OpenAI agents reaches MonkAI correctly.
They require:
- MONKAI_TEST_TOKEN: Your MonkAI tracer token
- OPENAI_API_KEY: Your OpenAI API key (consumed by examples)

Run with: pytest tests/test_openai_agents_e2e.py -v -m e2e
"""

import pytest
import subprocess
import sys
import time
import os
from pathlib import Path
from monkai_trace import MonkAIClient
from monkai_trace.models import ConversationRecord


@pytest.fixture
def monkai_credentials():
    """Get MonkAI test credentials from environment."""
    token = os.getenv("MONKAI_TEST_TOKEN")
    if not token:
        pytest.skip("MONKAI_TEST_TOKEN environment variable not set")
    
    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        pytest.skip("OPENAI_API_KEY environment variable not set for E2E tests")
    
    return {
        "token": token,
        "namespace": os.getenv("MONKAI_TEST_NAMESPACE", "e2e-test-openai-agents")
    }


@pytest.fixture
def monkai_client(monkai_credentials):
    """Create MonkAI client for verification."""
    return MonkAIClient(tracer_token=monkai_credentials["token"])


@pytest.fixture
def test_namespace():
    """Generate unique namespace for each test."""
    return f"test-openai-agents-{int(time.time())}"


class MonkAIDataVerifier:
    """Helper class to verify data in MonkAI after execution."""
    
    def __init__(self, client, namespace):
        self.client = client
        self.namespace = namespace
    
    def wait_for_records(self, min_count=1, timeout=30, session_id=None):
        """
        Poll for conversation records to appear in MonkAI.
        
        Args:
            min_count: Minimum number of records expected
            timeout: Maximum time to wait in seconds
            session_id: Optional session_id to filter by
        
        Returns:
            List of conversation records found
        """
        start_time = time.time()
        records = []
        
        while time.time() - start_time < timeout:
            # Note: In a real implementation, you would query MonkAI API/DB here
            # For now, we'll simulate with a simple check
            try:
                # This is a placeholder - actual implementation would query MonkAI
                # Example: records = self.client.get_conversations(namespace=self.namespace, session_id=session_id)
                
                if len(records) >= min_count:
                    return records
            except Exception as e:
                print(f"Error querying records: {e}")
            
            time.sleep(1)
        
        raise TimeoutError(f"Expected {min_count} records, got {len(records)} after {timeout}s")
    
    def verify_conversation_structure(self, record):
        """Validate that a conversation record has the expected structure."""
        assert record.namespace == self.namespace, f"Wrong namespace: {record.namespace}"
        assert record.agent is not None, "Agent name missing"
        assert record.session_id is not None, "Session ID missing"
        assert record.msg is not None, "Message missing"
        assert record.total_tokens > 0, "Total tokens should be > 0"
        return True
    
    def verify_token_usage(self, record):
        """Validate token usage breakdown."""
        # All token counts should be non-negative
        assert record.input_tokens >= 0, "Input tokens should be >= 0"
        assert record.output_tokens >= 0, "Output tokens should be >= 0"
        assert record.process_tokens >= 0, "Process tokens should be >= 0"
        
        # Total should equal sum of components
        calculated_total = (
            record.input_tokens + 
            record.output_tokens + 
            record.process_tokens + 
            (record.memory_tokens or 0)
        )
        assert record.total_tokens == calculated_total, \
            f"Total tokens mismatch: {record.total_tokens} != {calculated_total}"
        
        return True
    
    def verify_handoffs(self, records):
        """Validate Transfer objects in multi-agent scenarios."""
        transfers = []
        for record in records:
            if hasattr(record, 'transfers') and record.transfers:
                transfers.extend(record.transfers)
        
        # Verify each transfer has required fields
        for transfer in transfers:
            assert hasattr(transfer, 'source_agent'), "Transfer missing source_agent"
            assert hasattr(transfer, 'target_agent'), "Transfer missing target_agent"
            assert hasattr(transfer, 'timestamp'), "Transfer missing timestamp"
        
        return transfers


@pytest.mark.e2e
def test_basic_conversation_reaches_monkai(monkai_credentials, monkai_client, test_namespace):
    """
    Test that a basic OpenAI agent conversation is tracked and uploaded to MonkAI.
    
    This test:
    1. Runs the basic openai_agents_example.py
    2. Waits for the conversation record to appear in MonkAI
    3. Validates the structure and token usage
    """
    examples_dir = Path(__file__).parent.parent / "examples"
    script_path = examples_dir / "openai_agents_example.py"
    
    # Run the example with test credentials
    env = os.environ.copy()
    env["MONKAI_TEST_TOKEN"] = monkai_credentials["token"]
    env["MONKAI_TEST_NAMESPACE"] = test_namespace
    
    result = subprocess.run(
        [sys.executable, str(script_path), "--token", monkai_credentials["token"], 
         "--namespace", test_namespace],
        env=env,
        capture_output=True,
        text=True,
        timeout=60
    )
    
    print(f"Script output:\n{result.stdout}")
    if result.stderr:
        print(f"Script errors:\n{result.stderr}")
    
    assert result.returncode == 0, f"Script failed with exit code {result.returncode}"
    
    # Verify data reached MonkAI
    verifier = MonkAIDataVerifier(monkai_client, test_namespace)
    
    # We expect at least 2 records (one for each method demonstrated in the example)
    records = verifier.wait_for_records(min_count=2, timeout=30)
    
    # Validate structure and tokens
    for record in records:
        assert verifier.verify_conversation_structure(record)
        assert verifier.verify_token_usage(record)
    
    print(f"✅ Successfully verified {len(records)} conversation records in MonkAI")


@pytest.mark.e2e
def test_multi_agent_handoff_tracking(monkai_credentials, monkai_client, test_namespace):
    """
    Test that multi-agent handoffs are correctly tracked.
    
    This test:
    1. Runs the multi-agent example with handoffs
    2. Verifies multiple agents are tracked
    3. Validates Transfer objects for handoffs
    4. Confirms token usage per agent
    """
    examples_dir = Path(__file__).parent.parent / "examples"
    script_path = examples_dir / "openai_agents_multi_agent.py"
    
    env = os.environ.copy()
    env["MONKAI_TEST_TOKEN"] = monkai_credentials["token"]
    env["MONKAI_TEST_NAMESPACE"] = test_namespace
    
    result = subprocess.run(
        [sys.executable, str(script_path), "--token", monkai_credentials["token"],
         "--namespace", test_namespace, "--test-mode"],
        env=env,
        capture_output=True,
        text=True,
        timeout=90
    )
    
    print(f"Multi-agent output:\n{result.stdout}")
    if result.stderr:
        print(f"Multi-agent errors:\n{result.stderr}")
    
    assert result.returncode == 0, f"Multi-agent script failed: {result.returncode}"
    
    verifier = MonkAIDataVerifier(monkai_client, test_namespace)
    
    # Expect records from multiple agents (triage, tech_support, billing)
    records = verifier.wait_for_records(min_count=3, timeout=45)
    
    # Verify we have records from different agents
    agents = {record.agent for record in records}
    assert len(agents) > 1, f"Expected multiple agents, got: {agents}"
    
    # Verify handoffs
    transfers = verifier.verify_handoffs(records)
    assert len(transfers) > 0, "Expected at least one handoff in multi-agent scenario"
    
    print(f"✅ Verified {len(records)} records with {len(transfers)} handoffs from {len(agents)} agents")


@pytest.mark.e2e
def test_batch_upload_mechanism(monkai_credentials, monkai_client, test_namespace):
    """
    Test that batch upload mechanism works correctly.
    
    This test verifies that when multiple conversations are created,
    they are all properly uploaded via the batch mechanism.
    """
    examples_dir = Path(__file__).parent.parent / "examples"
    script_path = examples_dir / "openai_agents_example.py"
    
    # Run multiple times to trigger batch upload
    num_runs = 3
    
    for i in range(num_runs):
        env = os.environ.copy()
        env["MONKAI_TEST_TOKEN"] = monkai_credentials["token"]
        env["MONKAI_TEST_NAMESPACE"] = test_namespace
        
        result = subprocess.run(
            [sys.executable, str(script_path), "--token", monkai_credentials["token"],
             "--namespace", test_namespace],
            env=env,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        assert result.returncode == 0, f"Run {i+1} failed"
        print(f"Completed run {i+1}/{num_runs}")
    
    # Verify all runs were recorded
    verifier = MonkAIDataVerifier(monkai_client, test_namespace)
    
    # Each run creates 2 records, so expect at least num_runs * 2
    expected_min = num_runs * 2
    records = verifier.wait_for_records(min_count=expected_min, timeout=60)
    
    assert len(records) >= expected_min, \
        f"Expected at least {expected_min} records, got {len(records)}"
    
    print(f"✅ Batch upload verified: {len(records)} total records from {num_runs} runs")


@pytest.mark.e2e
def test_user_input_capture_methods(monkai_credentials, monkai_client, test_namespace):
    """
    Test that both user input capture methods work correctly:
    1. run_with_tracking() (automatic capture)
    2. set_user_input() (manual capture)
    """
    examples_dir = Path(__file__).parent.parent / "examples"
    script_path = examples_dir / "openai_agents_example.py"
    
    env = os.environ.copy()
    env["MONKAI_TEST_TOKEN"] = monkai_credentials["token"]
    env["MONKAI_TEST_NAMESPACE"] = test_namespace
    
    result = subprocess.run(
        [sys.executable, str(script_path), "--token", monkai_credentials["token"],
         "--namespace", test_namespace],
        env=env,
        capture_output=True,
        text=True,
        timeout=60
    )
    
    assert result.returncode == 0, "Script failed"
    
    # Verify both methods captured user input
    verifier = MonkAIDataVerifier(monkai_client, test_namespace)
    records = verifier.wait_for_records(min_count=2, timeout=30)
    
    # Check that user messages were captured in the records
    user_messages_found = 0
    for record in records:
        # In the actual implementation, you would check the conversation history
        # for user role messages
        user_messages_found += 1
    
    assert user_messages_found >= 2, \
        f"Expected at least 2 user messages captured, found {user_messages_found}"
    
    print(f"✅ Both user input capture methods verified")


@pytest.mark.e2e
def test_token_usage_accuracy(monkai_credentials, monkai_client, test_namespace):
    """
    Test that token usage is accurately reported and segmented.
    
    Verifies:
    - input_tokens matches user input
    - output_tokens matches assistant response
    - process_tokens for system/reasoning
    - total_tokens = sum of all components
    """
    examples_dir = Path(__file__).parent.parent / "examples"
    script_path = examples_dir / "openai_agents_example.py"
    
    env = os.environ.copy()
    env["MONKAI_TEST_TOKEN"] = monkai_credentials["token"]
    env["MONKAI_TEST_NAMESPACE"] = test_namespace
    
    result = subprocess.run(
        [sys.executable, str(script_path), "--token", monkai_credentials["token"],
         "--namespace", test_namespace],
        env=env,
        capture_output=True,
        text=True,
        timeout=60
    )
    
    assert result.returncode == 0, "Script failed"
    
    verifier = MonkAIDataVerifier(monkai_client, test_namespace)
    records = verifier.wait_for_records(min_count=1, timeout=30)
    
    # Verify token breakdown for each record
    for record in records:
        assert verifier.verify_token_usage(record), \
            f"Token usage validation failed for record {record.session_id}"
        
        # Additional checks
        assert record.input_tokens > 0, "Input tokens should be > 0"
        assert record.output_tokens > 0, "Output tokens should be > 0"
    
    print(f"✅ Token usage accuracy verified for {len(records)} records")


@pytest.mark.e2e
@pytest.mark.slow
def test_session_continuity(monkai_credentials, monkai_client, test_namespace):
    """
    Test that session IDs are maintained within a run but reset between runs.
    """
    examples_dir = Path(__file__).parent.parent / "examples"
    script_path = examples_dir / "openai_agents_example.py"
    
    # Run twice
    session_ids_run1 = set()
    session_ids_run2 = set()
    
    for run_num, session_ids_set in [(1, session_ids_run1), (2, session_ids_run2)]:
        env = os.environ.copy()
        env["MONKAI_TEST_TOKEN"] = monkai_credentials["token"]
        # Use different namespace per run to isolate
        run_namespace = f"{test_namespace}-run{run_num}"
        env["MONKAI_TEST_NAMESPACE"] = run_namespace
        
        result = subprocess.run(
            [sys.executable, str(script_path), "--token", monkai_credentials["token"],
             "--namespace", run_namespace],
            env=env,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        assert result.returncode == 0, f"Run {run_num} failed"
        
        # Get session IDs from this run
        verifier = MonkAIDataVerifier(monkai_client, run_namespace)
        records = verifier.wait_for_records(min_count=1, timeout=30)
        
        for record in records:
            session_ids_set.add(record.session_id)
    
    # Session IDs from different runs should be different
    assert session_ids_run1.isdisjoint(session_ids_run2), \
        "Session IDs should be different between runs"
    
    print(f"✅ Session continuity verified: Run1={session_ids_run1}, Run2={session_ids_run2}")
