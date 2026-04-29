"""Synchronous client for MonkAI API"""

import re
import time
import logging
import requests
from typing import List, Optional, Union, Dict
from pathlib import Path
from .models import ConversationRecord, LogEntry, TokenUsage
from .file_handlers import FileHandler
from .anonymizer import BaselineAnonymizer, RulesClient
from .exceptions import (
    MonkAIAnonymizerNotReady,
    MonkAIAuthError,
    MonkAIValidationError,
    MonkAIServerError,
    MonkAINetworkError,
    MonkAIAPIError,
    MonkAIRecordDiscardedError,
)

logger = logging.getLogger(__name__)


def _compile_custom_rules(custom):
    """Compile custom rule patterns once per call. Skips invalid regex with a warning."""
    compiled = []
    for r in custom:
        if not isinstance(r, dict):
            continue
        pattern = r.get("pattern")
        replacement = r.get("replacement", "[REDACTED]")
        if not isinstance(pattern, str):
            continue
        try:
            compiled.append((re.compile(pattern), replacement))
        except re.error:
            logger.warning(
                "RulesClient: skipping invalid custom regex %r (%s)",
                r.get("name", pattern),
                pattern,
            )
    return compiled


def _apply_custom_to_text(text, compiled):
    if not isinstance(text, str) or not text:
        return text
    out = text
    for pattern, replacement in compiled:
        out = pattern.sub(replacement, out)
    return out


def _apply_custom_rules_to_message(msg, custom):
    """Apply custom rules over an already-baseline-redacted message."""
    compiled = _compile_custom_rules(custom)
    if not compiled or not isinstance(msg, dict) or "content" not in msg:
        return msg
    content = msg["content"]
    new_msg = dict(msg)
    if isinstance(content, str):
        new_msg["content"] = _apply_custom_to_text(content, compiled)
    elif isinstance(content, list):
        new_msg["content"] = [_apply_custom_to_block(b, compiled) for b in content]
    return new_msg


def _apply_custom_to_block(block, compiled):
    if not isinstance(block, dict):
        return block
    new_block = dict(block)
    block_type = new_block.get("type")
    if block_type == "text" and isinstance(new_block.get("text"), str):
        new_block["text"] = _apply_custom_to_text(new_block["text"], compiled)
    elif block_type == "tool_use" and isinstance(new_block.get("input"), dict):
        new_block["input"] = _apply_custom_to_dict(new_block["input"], compiled)
    elif block_type == "tool_result":
        inner = new_block.get("content")
        if isinstance(inner, str):
            new_block["content"] = _apply_custom_to_text(inner, compiled)
        elif isinstance(inner, list):
            new_block["content"] = [_apply_custom_to_block(b, compiled) for b in inner]
    return new_block


def _apply_custom_to_dict(d, compiled):
    out = {}
    for k, v in d.items():
        if isinstance(v, str):
            out[k] = _apply_custom_to_text(v, compiled)
        elif isinstance(v, dict):
            out[k] = _apply_custom_to_dict(v, compiled)
        elif isinstance(v, list):
            out[k] = [
                _apply_custom_to_text(item, compiled) if isinstance(item, str)
                else _apply_custom_to_dict(item, compiled) if isinstance(item, dict)
                else item
                for item in v
            ]
        else:
            out[k] = v
    return out


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
        max_retries: int = 3,
        strict_dedup: bool = False,
        rules_url: Optional[str] = None,
        rules_ttl_seconds: int = 300,
        rules_client: Optional[RulesClient] = None,
    ):
        """
        Initialize MonkAI client

        Args:
            tracer_token: Your MonkAI tracer token
            base_url: Optional custom API base URL
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
            strict_dedup: If True, raise MonkAIRecordDiscardedError when the server reports drops
            rules_url: Hub URL exposing ``/v1/anonymization-rules``. When set,
                the SDK fetches per-tenant custom rules and applies them on
                top of the baseline before transmission. Leave ``None`` to
                preserve Phase 1 behaviour (baseline only).
            rules_ttl_seconds: How long a successful rules fetch is reused
                before being refreshed. Defaults to 300s.
            rules_client: Optional pre-built ``RulesClient`` (overrides
                ``rules_url``/``rules_ttl_seconds`` for full control).
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
        self._anonymizer = BaselineAnonymizer()
        self._strict_dedup = strict_dedup
        if rules_client is not None:
            self._rules_client: Optional[RulesClient] = rules_client
        elif rules_url is not None:
            self._rules_client = RulesClient(
                tracer_token=tracer_token,
                hub_url=rules_url,
                ttl_seconds=rules_ttl_seconds,
            )
        else:
            self._rules_client = None
        self._last_anonymization_version: Optional[int] = None
    
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
        model: Optional[str] = None,
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
            model: LLM model used (e.g., gpt-4o, claude-sonnet-4-6-20250514)
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
            model=model,
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
            except MonkAIRecordDiscardedError:
                raise  # never swallow strict-mode signal
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
        logger.info(f"Loaded {len(records)} records from {file_path}")
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
        
        logger.info(f"Loaded {len(logs)} logs from {file_path}")
        return self.upload_logs_batch(logs, chunk_size=chunk_size)
    
    # ==================== INTERNAL METHODS ====================
    
    def _request_with_retry(self, method: str, url: str, **kwargs) -> requests.Response:
        """Execute HTTP request with exponential backoff retry."""
        kwargs.setdefault("timeout", self.timeout)
        for attempt in range(self.max_retries):
            try:
                response = self._session.request(method, url, **kwargs)
                if response.status_code == 401:
                    raise MonkAIAuthError("Invalid tracer token")
                if response.status_code >= 500 and attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                if response.status_code not in (200, 201):
                    error_msg = f"{response.status_code} {response.reason}"
                    try:
                        error_msg += f": {response.json()}"
                    except Exception:
                        error_msg += f": {response.text[:200]}"
                    raise MonkAIAPIError(error_msg)
                return response
            except (requests.ConnectionError, requests.Timeout) as e:
                if attempt == self.max_retries - 1:
                    raise MonkAINetworkError(f"Request failed after {self.max_retries} attempts: {e}")
                time.sleep(2 ** attempt)
        raise MonkAIAPIError("Request failed after all retries")
    
    def _anonymize_messages(self, messages):
        """Apply baseline + per-tenant custom rules to every message content.

        When a ``RulesClient`` is configured, ``self._last_anonymization_version``
        is updated as a side effect so the upload payload can stamp it.
        """
        disabled, custom = self._fetch_rules_state()
        out = self._anonymizer.apply_to_messages(messages, disabled_classes=disabled)
        if custom:
            out = [_apply_custom_rules_to_message(m, custom) for m in out]
        return out

    def _fetch_rules_state(self):
        """Return (disabled_classes, custom_rules). Updates ``_last_anonymization_version``.

        When ``RulesClient`` is not configured returns empty values and leaves
        ``_last_anonymization_version`` as None (no stamp on payload).
        """
        if self._rules_client is None:
            self._last_anonymization_version = None
            return set(), []
        rules_doc = self._rules_client.get()  # may raise MonkAIAnonymizerNotReady
        rules = rules_doc.get("rules", {})
        toggles = rules.get("toggles", {}) or {}
        disabled = {name for name, enabled in toggles.items() if enabled is False}
        custom = rules.get("custom") or []
        self._last_anonymization_version = int(rules_doc.get("version", 0))
        return disabled, custom

    def _serialize_record(self, record: ConversationRecord) -> Dict:
        """Serialize a record and anonymize its message content before transmission."""
        payload = record.to_api_format()
        if "msg" in payload and payload["msg"] is not None:
            payload["msg"] = self._anonymize_messages(payload["msg"])
        if self._last_anonymization_version is not None:
            payload["anonymization_version"] = self._last_anonymization_version
        return payload

    def _check_dedup_response(self, response_dict: Dict, total_records: int) -> Dict:
        """Inspect upload response for server-side dedup drops.

        Logs a warning whenever the server reports drops. In strict_dedup mode,
        raises MonkAIRecordDiscardedError. Returns the response_dict unchanged.
        """
        inserted = response_dict.get("inserted_count", total_records)
        skipped = response_dict.get("duplicates_skipped", 0)
        is_all_dup = response_dict.get("duplicate") is True

        if is_all_dup:
            dropped = total_records
        else:
            dropped = skipped

        if dropped > 0:
            logger.warning(
                f"MonkAI dropped {dropped}/{total_records} records as duplicates within 60s window"
            )
            if self._strict_dedup:
                raise MonkAIRecordDiscardedError(
                    f"Server discarded {dropped}/{total_records} records as duplicates",
                    dropped_count=dropped,
                    inserted_count=inserted,
                    total_received=total_records,
                )

        return response_dict

    def _upload_single_record(self, record: ConversationRecord) -> Dict:
        """Internal: Upload single record"""
        url = f"{self.base_url}/records/upload"
        data = {"records": [self._serialize_record(record)]}
        response = self._request_with_retry("POST", url, json=data)
        return self._check_dedup_response(response.json(), total_records=1)

    def _upload_records_chunk(self, records: List[ConversationRecord]) -> Dict:
        """Internal: Upload chunk of records"""
        url = f"{self.base_url}/records/upload"
        data = {"records": [self._serialize_record(r) for r in records]}
        response = self._request_with_retry("POST", url, json=data)
        return self._check_dedup_response(response.json(), total_records=len(records))
    
    def _upload_single_log(self, log: LogEntry) -> Dict:
        """Internal: Upload single log"""
        url = f"{self.base_url}/logs/upload"
        data = {"logs": [log.to_api_format()]}
        response = self._request_with_retry("POST", url, json=data)
        return response.json()
    
    def _upload_logs_chunk(self, logs: List[LogEntry]) -> Dict:
        """Internal: Upload chunk of logs"""
        url = f"{self.base_url}/logs/upload"
        data = {"logs": [l.to_api_format() for l in logs]}
        response = self._request_with_retry("POST", url, json=data)
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
        response = self._request_with_retry("POST", url, json=data)
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
        
        response = self._request_with_retry("POST", url, json=data)
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
        
        response = self._request_with_retry("POST", url, json=data, timeout=max(self.timeout, 120))
        
        if format == "csv":
            content = response.text
            if output_file:
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                logger.info(f"Exported CSV to {output_file}")
            return content
        else:
            result = response.json()
            records = result.get("records", [])
            if output_file:
                import json
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(records, f, ensure_ascii=False, indent=2)
                logger.info(f"Exported {len(records)} records to {output_file}")
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
        
        response = self._request_with_retry("POST", url, json=data, timeout=max(self.timeout, 120))
        
        if format == "csv":
            content = response.text
            if output_file:
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                logger.info(f"Exported CSV to {output_file}")
            return content
        else:
            result = response.json()
            logs = result.get("logs", [])
            if output_file:
                import json
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(logs, f, ensure_ascii=False, indent=2)
                logger.info(f"Exported {len(logs)} logs to {output_file}")
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
        response = self._request_with_retry("POST", url, json=data)
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
