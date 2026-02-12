"""
Async MonkAI Client for high-performance applications.
"""

import asyncio
import aiohttp
from typing import List, Dict, Any, Optional, Union
from pathlib import Path

from .models import ConversationRecord, LogEntry
from .exceptions import MonkAIAPIError, MonkAIValidationError, MonkAIAuthError
from .file_handlers import FileHandler


class AsyncMonkAIClient:
    """
    Asynchronous client for MonkAI API.
    
    Ideal for high-throughput applications and async frameworks.
    
    Example:
        async with AsyncMonkAIClient(tracer_token="tk_xxx") as client:
            await client.upload_record(
                namespace="my-agent",
                agent="support-bot",
                messages={"role": "assistant", "content": "Hello!"}
            )
    """
    
    def __init__(
        self,
        tracer_token: str,
        base_url: str = "https://monkai.ai/api",
        timeout: int = 30,
        max_retries: int = 3
    ):
        """
        Initialize async MonkAI client.
        
        Args:
            tracer_token: Your MonkAI tracer token (required)
            base_url: API base URL (default: https://monkai.ai/api)
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
        """
        if not tracer_token or not tracer_token.startswith("tk_"):
            raise MonkAIValidationError("Invalid tracer_token format. Must start with 'tk_'")
        
        self.tracer_token = tracer_token
        self.base_url = base_url.rstrip("/")
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.max_retries = max_retries
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self._ensure_session()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()
    
    async def _ensure_session(self):
        """Ensure aiohttp session exists"""
        if self._session is None or self._session.closed:
            headers = {
                "Authorization": f"Bearer {self.tracer_token}",
                "Content-Type": "application/json"
            }
            self._session = aiohttp.ClientSession(
                headers=headers,
                timeout=self.timeout
            )
    
    async def close(self):
        """Close the aiohttp session"""
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Make HTTP request with retry logic"""
        await self._ensure_session()
        url = f"{self.base_url}/{endpoint}"
        
        for attempt in range(self.max_retries):
            try:
                async with self._session.request(method, url, json=data) as response:
                    if response.status == 401:
                        raise MonkAIAuthError("Invalid tracer token")
                    
                    response.raise_for_status()
                    return await response.json()
                    
            except aiohttp.ClientError as e:
                if attempt == self.max_retries - 1:
                    raise MonkAIAPIError(f"API request failed after {self.max_retries} attempts: {str(e)}")
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
        
        raise MonkAIAPIError("Request failed")
    
    async def upload_record(
        self,
        namespace: str,
        agent: str,
        messages: Union[Dict, List[Dict]],
        session_id: Optional[str] = None,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        process_tokens: Optional[int] = None,
        memory_tokens: Optional[int] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Upload a single conversation record.
        
        Args:
            namespace: Agent namespace
            agent: Agent name
            messages: Message dict or list of message dicts
            session_id: Optional session identifier
            input_tokens: User input tokens
            output_tokens: Agent response tokens
            process_tokens: System/process tokens
            memory_tokens: Context/memory tokens
            **kwargs: Additional metadata
        
        Returns:
            API response dict
        """
        record = ConversationRecord(
            namespace=namespace,
            agent=agent,
            msg=messages,
            session_id=session_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            process_tokens=process_tokens,
            memory_tokens=memory_tokens,
            **kwargs
        )
        
        return await self._upload_single_record(record)
    
    async def _upload_single_record(self, record: ConversationRecord) -> Dict[str, Any]:
        """Upload a single record"""
        return await self._make_request(
            "POST",
            "record_query",
            data=record.model_dump(exclude_none=True, by_alias=True)
        )
    
    async def upload_records_batch(
        self,
        records: List[ConversationRecord],
        chunk_size: int = 100,
        parallel: bool = True
    ) -> Dict[str, Any]:
        """
        Upload multiple records in batches.
        
        Args:
            records: List of ConversationRecord objects
            chunk_size: Records per batch
            parallel: Upload chunks in parallel (faster)
        
        Returns:
            Summary dict with total_inserted, total_records, failures
        """
        chunks = [records[i:i + chunk_size] for i in range(0, len(records), chunk_size)]
        
        if parallel:
            # Upload all chunks in parallel
            tasks = [self._upload_records_chunk(chunk) for chunk in chunks]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        else:
            # Upload chunks sequentially
            results = []
            for chunk in chunks:
                try:
                    result = await self._upload_records_chunk(chunk)
                    results.append(result)
                except Exception as e:
                    results.append(e)
        
        # Aggregate results
        total_inserted = 0
        failures = []
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                failures.append({"chunk": i, "error": str(result)})
            else:
                total_inserted += result.get("total_inserted", 0)
        
        return {
            "total_inserted": total_inserted,
            "total_records": len(records),
            "failures": failures
        }
    
    async def _upload_records_chunk(self, records: List[ConversationRecord]) -> Dict[str, Any]:
        """Upload a chunk of records"""
        records_data = [r.model_dump(exclude_none=True, by_alias=True) for r in records]
        response = await self._make_request("POST", "record_query/batch", data={"records": records_data})
        return {"total_inserted": len(records)}
    
    async def upload_records_from_json(
        self,
        file_path: Union[str, Path],
        chunk_size: int = 100,
        parallel: bool = True
    ) -> Dict[str, Any]:
        """
        Upload conversation records from JSON file.
        
        Args:
            file_path: Path to JSON file
            chunk_size: Records per batch
            parallel: Upload in parallel
        
        Returns:
            Upload summary
        """
        records = FileHandler.load_records(file_path)
        return await self.upload_records_batch(records, chunk_size, parallel)
    
    async def upload_log(
        self,
        namespace: str,
        level: str,
        message: str,
        agent: Optional[str] = None,
        session_id: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Upload a single log entry.
        
        Args:
            namespace: Agent namespace
            level: Log level (info, warn, error)
            message: Log message
            agent: Optional agent name
            session_id: Optional session identifier
            **kwargs: Additional metadata
        
        Returns:
            API response
        """
        log = LogEntry(
            namespace=namespace,
            level=level,
            message=message,
            agent=agent,
            session_id=session_id,
            **kwargs
        )
        
        return await self._upload_single_log(log)
    
    async def _upload_single_log(self, log: LogEntry) -> Dict[str, Any]:
        """Upload a single log entry"""
        return await self._make_request(
            "POST",
            "logs",
            data=log.model_dump(exclude_none=True, by_alias=True)
        )
    
    async def upload_logs_batch(
        self,
        logs: List[LogEntry],
        chunk_size: int = 100,
        parallel: bool = True
    ) -> Dict[str, Any]:
        """
        Upload multiple log entries in batches.
        
        Args:
            logs: List of LogEntry objects
            chunk_size: Logs per batch
            parallel: Upload in parallel
        
        Returns:
            Summary dict
        """
        chunks = [logs[i:i + chunk_size] for i in range(0, len(logs), chunk_size)]
        
        if parallel:
            tasks = [self._upload_logs_chunk(chunk) for chunk in chunks]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        else:
            results = []
            for chunk in chunks:
                try:
                    result = await self._upload_logs_chunk(chunk)
                    results.append(result)
                except Exception as e:
                    results.append(e)
        
        total_inserted = 0
        failures = []
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                failures.append({"chunk": i, "error": str(result)})
            else:
                total_inserted += result.get("total_inserted", 0)
        
        return {
            "total_inserted": total_inserted,
            "total_logs": len(logs),
            "failures": failures
        }
    
    async def _upload_logs_chunk(self, logs: List[LogEntry]) -> Dict[str, Any]:
        """Upload a chunk of logs"""
        logs_data = [log.model_dump(exclude_none=True, by_alias=True) for log in logs]
        response = await self._make_request("POST", "logs/batch", data={"logs": logs_data})
        return {"total_inserted": len(logs)}
    
    async def upload_logs_from_json(
        self,
        file_path: Union[str, Path],
        namespace: str,
        chunk_size: int = 100,
        parallel: bool = True
    ) -> Dict[str, Any]:
        """
        Upload logs from JSON file.
        
        Args:
            file_path: Path to JSON file
            namespace: Namespace for all logs
            chunk_size: Logs per batch
            parallel: Upload in parallel
        
        Returns:
            Upload summary
        """
        logs = FileHandler.load_logs(file_path, namespace)
        return await self.upload_logs_batch(logs, chunk_size, parallel)
    
    # ==================== QUERY METHODS ====================
    
    async def query_records(
        self,
        namespace: str,
        agent: Optional[str] = None,
        session_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        Query conversation records with filters.
        
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
        query = {"limit": limit, "offset": offset}
        if agent:
            query["agent"] = agent
        if session_id:
            query["session_id"] = session_id
        if start_date:
            query["start_date"] = start_date
        if end_date:
            query["end_date"] = end_date
        
        return await self._make_request(
            "POST", "record_query",
            data={"namespace": namespace, "query": query}
        )
    
    async def query_logs(
        self,
        namespace: str,
        level: Optional[str] = None,
        resource_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        Query logs with filters.
        
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
        data = {"namespace": namespace, "limit": limit, "offset": offset}
        if level:
            data["level"] = level
        if resource_id:
            data["resource_id"] = resource_id
        if start_date:
            data["start_date"] = start_date
        if end_date:
            data["end_date"] = end_date
        
        return await self._make_request("POST", "logs/query", data=data)
    
    # ==================== EXPORT METHODS ====================
    
    async def export_records(
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
        Export all records matching filters (handles pagination server-side).
        
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
        await self._ensure_session()
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
        
        timeout = aiohttp.ClientTimeout(total=120)
        async with self._session.post(url, json=data, timeout=timeout) as response:
            if response.status == 401:
                raise MonkAIAuthError("Invalid tracer token")
            response.raise_for_status()
            
            if format == "csv":
                content = await response.text()
                if output_file:
                    with open(output_file, 'w', encoding='utf-8') as f:
                        f.write(content)
                return content
            else:
                result = await response.json()
                records = result.get("records", [])
                if output_file:
                    import json as json_mod
                    with open(output_file, 'w', encoding='utf-8') as f:
                        json_mod.dump(records, f, ensure_ascii=False, indent=2)
                return records
    
    async def export_logs(
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
        Export all logs matching filters (handles pagination server-side).
        
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
        await self._ensure_session()
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
        
        timeout = aiohttp.ClientTimeout(total=120)
        async with self._session.post(url, json=data, timeout=timeout) as response:
            if response.status == 401:
                raise MonkAIAuthError("Invalid tracer token")
            response.raise_for_status()
            
            if format == "csv":
                content = await response.text()
                if output_file:
                    with open(output_file, 'w', encoding='utf-8') as f:
                        f.write(content)
                return content
            else:
                result = await response.json()
                logs = result.get("logs", [])
                if output_file:
                    import json as json_mod
                    with open(output_file, 'w', encoding='utf-8') as f:
                        json_mod.dump(logs, f, ensure_ascii=False, indent=2)
                return logs
    
    # ==================== UTILITY METHODS ====================
    
    async def test_connection(self) -> bool:
        """
        Test API connection.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            await self.upload_log(
                namespace="test",
                level="info",
                message="Connection test"
            )
            return True
        except Exception:
            return False
