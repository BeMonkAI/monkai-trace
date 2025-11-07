"""Tests for SessionManager"""

import pytest
import time
from monkai_trace.session_manager import SessionManager


def test_session_creation():
    """Test session creation"""
    manager = SessionManager(inactivity_timeout=60)
    
    session1 = manager.get_or_create_session("user1", "test-ns")
    assert session1.startswith("test-ns-user1-")
    
    # Same user within timeout should return same session
    session2 = manager.get_or_create_session("user1", "test-ns")
    assert session1 == session2


def test_session_timeout():
    """Test session expires after timeout"""
    manager = SessionManager(inactivity_timeout=1)  # 1 segundo
    
    session1 = manager.get_or_create_session("user1", "test-ns")
    time.sleep(2)  # Esperar expirar
    
    session2 = manager.get_or_create_session("user1", "test-ns")
    assert session1 != session2  # Nova sessão criada


def test_activity_update():
    """Test activity update extends session"""
    manager = SessionManager(inactivity_timeout=2)
    
    session1 = manager.get_or_create_session("user1", "test-ns")
    time.sleep(1)
    manager.update_activity("user1")
    time.sleep(1)
    
    # Ainda dentro do timeout devido ao update_activity
    session2 = manager.get_or_create_session("user1", "test-ns")
    assert session1 == session2


def test_force_new_session():
    """Test force_new parameter"""
    manager = SessionManager(inactivity_timeout=60)
    
    session1 = manager.get_or_create_session("user1", "test-ns")
    session2 = manager.get_or_create_session("user1", "test-ns", force_new=True)
    
    assert session1 != session2


def test_multi_user_isolation():
    """Test multiple users have separate sessions"""
    manager = SessionManager(inactivity_timeout=60)
    
    session1 = manager.get_or_create_session("user1", "test-ns")
    session2 = manager.get_or_create_session("user2", "test-ns")
    
    assert session1 != session2
    assert "user1" in session1
    assert "user2" in session2


def test_close_session():
    """Test explicit session closure"""
    manager = SessionManager(inactivity_timeout=60)
    
    session1 = manager.get_or_create_session("user1", "test-ns")
    manager.close_session("user1")
    
    # Should create new session after closing
    session2 = manager.get_or_create_session("user1", "test-ns")
    assert session1 != session2


def test_cleanup_expired():
    """Test automatic cleanup of expired sessions"""
    manager = SessionManager(inactivity_timeout=1)
    
    # Create multiple sessions
    manager.get_or_create_session("user1", "test-ns")
    manager.get_or_create_session("user2", "test-ns")
    manager.get_or_create_session("user3", "test-ns")
    
    time.sleep(2)  # Wait for expiration
    
    # Cleanup should remove all expired sessions
    removed = manager.cleanup_expired()
    assert removed == 3


def test_get_session_info():
    """Test session info retrieval"""
    manager = SessionManager(inactivity_timeout=60)
    
    session_id = manager.get_or_create_session("user1", "test-ns")
    
    info = manager.get_session_info("user1")
    assert info is not None
    assert info['session_id'] == session_id
    assert info['duration'] >= 0
    assert info['inactive_for'] >= 0
    
    # Non-existent user
    info = manager.get_session_info("nonexistent")
    assert info is None


def test_session_id_format():
    """Test session ID format"""
    manager = SessionManager(inactivity_timeout=60)
    
    session_id = manager.get_or_create_session("user123", "my-namespace")
    
    # Format: {namespace}-{user_id}-{timestamp}
    assert session_id.startswith("my-namespace-user123-")
    
    # Should have timestamp in format YYYYMMDD-HHMMSS
    timestamp_part = session_id.split("-", 2)[2]
    assert len(timestamp_part) == 15  # YYYYMMDD-HHMMSS
