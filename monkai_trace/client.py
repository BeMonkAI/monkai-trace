"""Synchronous client for MonkAI API"""

import requests
from typing import List, Optional, Union, Dict
from pathlib import Path
from .models import ConversationRecord, LogEntry, TokenUsage
from .file_handlers import FileHandler
from .exceptions import (
    MonkAIAuthError,
    MonkAIValidationError,
    MonkAIServerError,
    MonkAINetworkError
)


class MonkAIClient:
    """
    Synchronous client for MonkAI API
    
    Features:
    - Upload individual records/logs
    - Upload from JSON files
    - Batch uploads with automatic chunking
    - Token segmentation support
    - Retry logic with exponential backoff
    """
    
    BASE_URL = "https://lpvbvnqrozlwalnkvrgk.supabase.co/functions/v1/monkai-api"
    
    def __init__(
        self,
        tracer_token: str,
        base_url: Optional[str] = None,
        timeout: int = 30,
        max_retries: int = 3
    ):
        """
        Initialize MonkAI client
        
        Args:
            tracer_token: Your MonkAI tracer token
            base_url: Optional custom API base URL
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
        """
        self.tracer_token = tracer_token
        self.base_url = base_url or self.BASE_URL
        self.timeout = timeout
        self.max_retries = max_retries
        self._session = requests.Session()
        self._session.headers.update({
            "tracer_token": tracer_token,
            "Content-Type": "application/json"
        })
    
    # ==================== RECORD METHODS ====================
    
    def upload_record(
        self,
        namespace: str,
        agent: str,
        messages: Union[Dict, List[Dict]],
        input_tokens: int = 0,
        output_tokens: int = 0,
        process_tokens: int = 0,
        memory_tokens: int = 0,
        session_id: Optional[str] = None,
        transfers: Optional[List[Dict]] = None,
        external_user_id: Optional[str] = None,
        external_user_name: Optional[str] = None,
        external_user_channel: Optional[str] = None,
        **kwargs
    ) -> Dict:
        """
        Upload a single conversation record
        
        Args:
            namespace: Agent namespace
            agent: Agent name
            messages: Message dict or list of message dicts
            input_tokens: User input tokens
            output_tokens: Agent output tokens
            process_tokens: System/processing tokens
            memory_tokens: Context/memory tokens
            session_id: Optional session identifier
            transfers: Optional list of agent transfers
            external_user_id: End-user identifier (e.g., +5511999999999 for WhatsApp)
            external_user_name: Human-readable name of the end user (e.g., João Silva)
            external_user_channel: Channel of origin (whatsapp, teams, telegram, web, etc.)
            **kwargs: Additional fields (user_id, user_whatsapp, etc.)
        
        Returns:
            API response dict
        """
        record = ConversationRecord(
            namespace=namespace,
            agent=agent,
            msg=messages,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            process_tokens=process_tokens,
            memory_tokens=memory_tokens,
            session_id=session_id,
            transfers=transfers,
            external_user_id=external_user_id,
            external_user_name=external_user_name,
            external_user_channel=external_user_channel,
            **kwargs
        )
        
        return self._upload_single_record(record)
    
    def upload_records_batch(
        self,
        records: List[ConversationRecord],
        chunk_size: int = 100
    ) -> Dict:
        """
        Upload multiple records in batches
        
        Args:
            records: List of ConversationRecord objects
            chunk_size: Number of records per request
        
        Returns:
            Summary dict with success/failure counts
        """
        total_inserted = 0
        failures = []
        
        for i in range(0, len(records), chunk_size):
            chunk = records[i:i + chunk_size]
            try:
                response = self._upload_records_chunk(chunk)
                total_inserted += response.get('inserted_count', 0)
            except Exception as e:
                failures.append({
                    'chunk_index': i // chunk_size,
                    'error': str(e)
                })
        
        return {
            'total_inserted': total_inserted,
            'total_records': len(records),
            'failures': failures
        }
    
    def upload_records_from_json(
        self,
        file_path: Union[str, Path],
        chunk_size: int = 100
    ) -> Dict:
        """
        Upload conversation records from JSON file
        
        Args:
            file_path: Path to JSON file (format: {"records": [...]})
            chunk_size: Number of records per batch request
        
        Returns:
            Upload summary dict
        """
        records = FileHandler.load_records_from_json(file_path)
        print(f"Loaded {len(records)} records from {file_path}")
        return self.upload_records_batch(records, chunk_size=chunk_size)
    
    # ==================== LOG METHODS ====================
    
    def upload_log(
        self,
        namespace: str,
        level: str,
        message: str,
        resource_id: Optional[str] = None,
        custom_object: Optional[Dict] = None,
        timestamp: Optional[str] = None
    ) -> Dict:
        """
        Upload a single log entry
        
        Args:
            namespace: Namespace for this log
            level: Log level (info, warn, error, debug)
            message: Log message
            resource_id: Optional resource identifier
            custom_object: Optional custom data
            timestamp: Optional ISO-8601 timestamp
        
        Returns:
            API response dict
        """
        log = LogEntry(
            namespace=namespace,
            level=level,
            message=message,
            resource_id=resource_id,
            custom_object=custom_object,
            timestamp=timestamp
        )
        
        return self._upload_single_log(log)
    
    def upload_logs_batch(
        self,
        logs: List[LogEntry],
        chunk_size: int = 100
    ) -> Dict:
        """
        Upload multiple logs in batches
        
        Args:
            logs: List of LogEntry objects
            chunk_size: Number of logs per request
        
        Returns:
            Summary dict with success/failure counts
        """
        total_inserted = 0
        failures = []
        
        for i in range(0, len(logs), chunk_size):
            chunk = logs[i:i + chunk_size]
            try:
                response = self._upload_logs_chunk(chunk)
                total_inserted += response.get('inserted_count', 0)
            except Exception as e:
                failures.append({
                    'chunk_index': i // chunk_size,
                    'error': str(e)
                })
        
        return {
            'total_inserted': total_inserted,
            'total_logs': len(logs),
            'failures': failures
        }
    
    def upload_logs_from_json(
        self,
        file_path: Union[str, Path],
        namespace: str,
        chunk_size: int = 100
    ) -> Dict:
        """
        Upload logs from JSON file
        
        Args:
            file_path: Path to JSON file (format: {"logs": [...]})
            namespace: Namespace to assign to logs (if not in JSON)
            chunk_size: Number of logs per batch request
        
        Returns:
            Upload summary dict
        """
        logs = FileHandler.load_logs_from_json(file_path)
        
        # Set namespace if not already present
        for log in logs:
            if not log.namespace:
                log.namespace = namespace
        
        print(f"Loaded {len(logs)} logs from {file_path}")
        return self.upload_logs_batch(logs, chunk_size=chunk_size)
    
    # ==================== INTERNAL METHODS ====================
    
    def _upload_single_record(self, record: ConversationRecord) -> Dict:
        """Internal: Upload single record"""
        url = f"{self.base_url}/records/upload"
        data = {"records": [record.to_api_format()]}
        response = self._session.post(url, json=data, timeout=self.timeout)
        response.raise_for_status()
        return response.json()
    
    def _upload_records_chunk(self, records: List[ConversationRecord]) -> Dict:
        """Internal: Upload chunk of records"""
        url = f"{self.base_url}/records/upload"
        data = {"records": [r.to_api_format() for r in records]}
        response = self._session.post(url, json=data, timeout=self.timeout)
        
        # Better error handling
        if response.status_code != 200 and response.status_code != 201:
            error_msg = f"{response.status_code} {response.reason}"
            try:
                error_detail = response.json()
                error_msg += f": {error_detail}"
            except:
                error_msg += f": {response.text[:200]}"
            raise requests.HTTPError(error_msg, response=response)
        
        return response.json()
    
    def _upload_single_log(self, log: LogEntry) -> Dict:
        """Internal: Upload single log"""
        url = f"{self.base_url}/logs/upload"
        data = {"logs": [log.to_api_format()]}
        response = self._session.post(url, json=data, timeout=self.timeout)
        response.raise_for_status()
        return response.json()
    
    def _upload_logs_chunk(self, logs: List[LogEntry]) -> Dict:
        """Internal: Upload chunk of logs"""
        url = f"{self.base_url}/logs/upload"
        data = {"logs": [l.to_api_format() for l in logs]}
        response = self._session.post(url, json=data, timeout=self.timeout)
        response.raise_for_status()
        return response.json()
    
    # ==================== QUERY METHODS ====================
    
    def query_records(
        self,
        namespace: str,
        agent: Optional[str] = None,
        session_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Dict:
        """
        Query conversation records with filters
        
        Args:
            namespace: Namespace to query
            agent: Filter by agent name
            session_id: Filter by session ID
            start_date: Filter records after this date (ISO-8601)
            end_date: Filter records before this date (ISO-8601)
            limit: Maximum records to return (default: 100)
            offset: Number of records to skip (default: 0)
        
        Returns:
            Dict with 'records' list and 'count' total
        """
        url = f"{self.base_url}/record_query"
        query = {"limit": limit, "offset": offset}
        if agent:
            query["agent"] = agent
        if session_id:
            query["session_id"] = session_id
        if start_date:
            query["start_date"] = start_date
        if end_date:
            query["end_date"] = end_date
        
        data = {"namespace": namespace, "query": query}
        response = self._session.post(url, json=data, timeout=self.timeout)
        response.raise_for_status()
        return response.json()
    
    def query_logs(
        self,
        namespace: str,
        level: Optional[str] = None,
        resource_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Dict:
        """
        Query logs with filters
        
        Args:
            namespace: Namespace to query
            level: Filter by log level (info, warn, error)
            resource_id: Filter by resource ID
            start_date: Filter logs after this date (ISO-8601)
            end_date: Filter logs before this date (ISO-8601)
            limit: Maximum logs to return (default: 100)
            offset: Number of logs to skip (default: 0)
        
        Returns:
            Dict with 'logs' list and 'count' total
        """
        url = f"{self.base_url}/logs/query"
        data = {"namespace": namespace, "limit": limit, "offset": offset}
        if level:
            data["level"] = level
        if resource_id:
            data["resource_id"] = resource_id
        if start_date:
            data["start_date"] = start_date
        if end_date:
            data["end_date"] = end_date
        
        response = self._session.post(url, json=data, timeout=self.timeout)
        response.raise_for_status()
        return response.json()
    
    # ==================== EXPORT METHODS ====================
    
    def export_records(
        self,
        namespace: str,
        agent: Optional[str] = None,
        session_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        format: str = "json",
        output_file: Optional[str] = None
    ) -> Union[List[Dict], str]:
        """
        Export all records matching filters (handles pagination server-side)
        
        Args:
            namespace: Namespace to export
            agent: Filter by agent name
            session_id: Filter by session ID
            start_date: Filter records after this date (ISO-8601)
            end_date: Filter records before this date (ISO-8601)
            format: Output format ('json' or 'csv')
            output_file: Optional file path to save export
        
        Returns:
            List of record dicts (json) or CSV string (csv)
        """
        url = f"{self.base_url}/records/export"
        data = {"namespace": namespace, "format": format}
        if agent:
            data["agent"] = agent
        if session_id:
            data["session_id"] = session_id
        if start_date:
            data["start_date"] = start_date
        if end_date:
            data["end_date"] = end_date
        
        response = self._session.post(url, json=data, timeout=max(self.timeout, 120))
        response.raise_for_status()
        
        if format == "csv":
            content = response.text
            if output_file:
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"Exported CSV to {output_file}")
            return content
        else:
            result = response.json()
            records = result.get("records", [])
            if output_file:
                import json
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(records, f, ensure_ascii=False, indent=2)
                print(f"Exported {len(records)} records to {output_file}")
            return records
    
    def export_logs(
        self,
        namespace: str,
        level: Optional[str] = None,
        resource_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        format: str = "json",
        output_file: Optional[str] = None
    ) -> Union[List[Dict], str]:
        """
        Export all logs matching filters (handles pagination server-side)
        
        Args:
            namespace: Namespace to export
            level: Filter by log level
            resource_id: Filter by resource ID
            start_date: Filter logs after this date (ISO-8601)
            end_date: Filter logs before this date (ISO-8601)
            format: Output format ('json' or 'csv')
            output_file: Optional file path to save export
        
        Returns:
            List of log dicts (json) or CSV string (csv)
        """
        url = f"{self.base_url}/logs/export"
        data = {"namespace": namespace, "format": format}
        if level:
            data["level"] = level
        if resource_id:
            data["resource_id"] = resource_id
        if start_date:
            data["start_date"] = start_date
        if end_date:
            data["end_date"] = end_date
        
        response = self._session.post(url, json=data, timeout=max(self.timeout, 120))
        response.raise_for_status()
        
        if format == "csv":
            content = response.text
            if output_file:
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"Exported CSV to {output_file}")
            return content
        else:
            result = response.json()
            logs = result.get("logs", [])
            if output_file:
                import json
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(logs, f, ensure_ascii=False, indent=2)
                print(f"Exported {len(logs)} logs to {output_file}")
            return logs
    
    # ==================== SESSION METHODS ====================
    
    def get_or_create_session(
        self,
        namespace: str,
        user_id: str,
        inactivity_timeout: int = 120,
        force_new: bool = False
    ) -> Dict:
        """
        Get an existing active session or create a new one (server-side persistent).
        
        This queries the backend database for recent activity within the
        inactivity_timeout window, ensuring session continuity across
        stateless environments (REST APIs, serverless, etc.).
        
        Args:
            namespace: Agent namespace
            user_id: External user identifier
            inactivity_timeout: Seconds of inactivity before new session
            force_new: Force creation of a new session
        
        Returns:
            Dict with session_id, reused (bool), and metadata
        """
        url = f"{self.base_url}/sessions/get-or-create"
        data = {
            "namespace": namespace,
            "user_id": user_id,
            "inactivity_timeout": inactivity_timeout,
            "force_new": force_new
        }
        response = self._session.post(url, json=data, timeout=self.timeout)
        response.raise_for_status()
        return response.json()
    
    # ==================== UTILITY METHODS ====================
    
    def test_connection(self) -> bool:
        """Test if token and connection are valid"""
        try:
            # Try to upload a minimal log
            self.upload_log(
                namespace="test",
                level="info",
                message="Connection test"
            )
            return True
        except Exception:
            return False
