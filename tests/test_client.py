"""Tests for MonkAIClient"""

import pytest
from unittest.mock import Mock, patch, mock_open
from monkai_trace import MonkAIClient
from monkai_trace.models import ConversationRecord, Message, LogEntry
from monkai_trace.exceptions import MonkAIError, MonkAIValidationError


def test_client_initialization():
    """Test client initialization"""
    client = MonkAIClient(tracer_token="tk_test_token")
    assert client.tracer_token == "tk_test_token"
    assert client.base_url == "https://monkai.ai/api"


def test_client_custom_base_url():
    """Test client with custom base URL"""
    client = MonkAIClient(
        tracer_token="tk_test",
        base_url="https://custom.api.com"
    )
    assert client.base_url == "https://custom.api.com"


@patch('requests.Session.post')
def test_upload_record_success(mock_post, sample_conversation_record):
    """Test successful record upload"""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"success": True}
    mock_post.return_value = mock_response
    
    client = MonkAIClient(tracer_token="tk_test")
    result = client.upload_record(
        namespace="test",
        agent="test-agent",
        messages={"role": "assistant", "content": "Hello"}
    )
    
    assert result["success"] == True
    mock_post.assert_called_once()


@patch('requests.Session.post')
def test_upload_record_api_error(mock_post):
    """Test upload record API error handling"""
    mock_response = Mock()
    mock_response.status_code = 500
    mock_response.raise_for_status.side_effect = Exception("API Error")
    mock_post.return_value = mock_response
    
    client = MonkAIClient(tracer_token="tk_test", max_retries=1)
    
    with pytest.raises(MonkAIAPIError):
        client.upload_record(
            namespace="test",
            agent="test-agent",
            messages={"role": "user", "content": "Test"}
        )


@patch('requests.Session.post')
def test_upload_records_batch(mock_post, sample_conversation_record):
    """Test batch record upload"""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"total_inserted": 2}
    mock_post.return_value = mock_response
    
    client = MonkAIClient(tracer_token="tk_test")
    records = [sample_conversation_record, sample_conversation_record]
    
    result = client.upload_records_batch(records, chunk_size=2)
    
    assert result["total_inserted"] == 2
    assert result["total_records"] == 2
    assert len(result["failures"]) == 0


@patch('requests.Session.post')
def test_upload_log_success(mock_post):
    """Test successful log upload"""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"success": True}
    mock_post.return_value = mock_response
    
    client = MonkAIClient(tracer_token="tk_test")
    result = client.upload_log(
        namespace="test",
        level="info",
        message="Test log message"
    )
    
    assert result["success"] == True


@patch('builtins.open', new_callable=mock_open, read_data='[{"namespace": "test", "agent": "test-agent", "msg": {"role": "user", "content": "Hi"}}]')
@patch('requests.Session.post')
def test_upload_records_from_json(mock_post, mock_file):
    """Test uploading records from JSON file"""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"total_inserted": 1}
    mock_post.return_value = mock_response
    
    client = MonkAIClient(tracer_token="tk_test")
    result = client.upload_records_from_json("test.json")
    
    assert result["total_records"] >= 0


@patch('requests.Session.post')
def test_test_connection_success(mock_post):
    """Test connection test"""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_post.return_value = mock_response
    
    client = MonkAIClient(tracer_token="tk_test")
    assert client.test_connection() == True


@patch('requests.Session.post')
def test_test_connection_failure(mock_post):
    """Test connection test failure"""
    mock_post.side_effect = Exception("Connection failed")
    
    client = MonkAIClient(tracer_token="tk_test")
    assert client.test_connection() == False
