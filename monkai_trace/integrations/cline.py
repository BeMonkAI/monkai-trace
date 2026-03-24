"""
Cline (formerly Claude Dev / OpenClaw) integration for MonkAI Trace.

Parses Cline VS Code extension task history and uploads to MonkAI.

Cline stores task data at (macOS):
    ~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/tasks/

Each task is a directory with:
    - api_conversation_history.json: Full API message history
    - ui_messages.json: UI-facing messages
    - <task_id>/: Subtask directories

The api_conversation_history.json format:
    [
        {"role": "user", "content": [{"type": "text", "text": "..."}]},
        {"role": "assistant", "content": [{"type": "text", "text": "..."}, {"type": "tool_use", ...}]},
        {"role": "user", "content": [{"type": "tool_result", ...}]},
        ...
    ]

Example:
    >>> from monkai_trace.integrations.cline import ClineTracer
    >>>
    >>> tracer = ClineTracer(
    ...     tracer_token="tk_your_token",
    ...     namespace="dev-productivity"
    ... )
    >>>
    >>> # Upload all Cline tasks
    >>> tracer.upload_all_tasks()
    >>>
    >>> # Upload a specific task
    >>> tracer.upload_task("/path/to/tasks/1234567890/")
    >>>
    >>> # Custom storage path (e.g., Cursor, Windsurf)
    >>> tracer = ClineTracer(
    ...     tracer_token="tk_your_token",
    ...     namespace="dev-productivity",
    ...     storage_dir="~/Library/Application Support/Cursor/User/globalStorage/saoudrizwan.claude-dev/tasks/"
    ... )
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..client import MonkAIClient
from ..models import ConversationRecord, Message, TokenUsage

logger = logging.getLogger(__name__)

# Known Cline storage paths by editor (macOS)
CLINE_STORAGE_PATHS = {
    "vscode": Path.home()
    / "Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/tasks",
    "cursor": Path.home()
    / "Library/Application Support/Cursor/User/globalStorage/saoudrizwan.claude-dev/tasks",
    "windsurf": Path.home()
    / "Library/Application Support/Windsurf/User/globalStorage/saoudrizwan.claude-dev/tasks",
}

# Linux paths
if os.name != "nt" and not str(Path.home()).startswith("/Users"):
    CLINE_STORAGE_PATHS.update({
        "vscode": Path.home()
        / ".config/Code/User/globalStorage/saoudrizwan.claude-dev/tasks",
        "cursor": Path.home()
        / ".config/Cursor/User/globalStorage/saoudrizwan.claude-dev/tasks",
    })

# Cline tool types
CLINE_TOOL_TYPES = {
    "execute_command": "terminal",
    "read_file": "file_read",
    "write_to_file": "file_write",
    "replace_in_file": "file_edit",
    "search_files": "file_search",
    "list_files": "file_list",
    "list_code_definition_names": "code_search",
    "browser_action": "browser",
    "ask_followup_question": "user_interaction",
    "attempt_completion": "completion",
    "use_mcp_tool": "mcp_tool",
    "access_mcp_resource": "mcp_resource",
}


class ClineTracer:
    """
    Parse Cline task history and upload to MonkAI Trace.

    Args:
        tracer_token: MonkAI tracer token (starts with 'tk_')
        namespace: Namespace for organizing conversations
        agent_name: Agent name in MonkAI (default: "cline")
        storage_dir: Custom path to Cline tasks directory (auto-detected if None)
        auto_upload: Upload records immediately (default: True)
        base_url: Optional custom API base URL
    """

    def __init__(
        self,
        tracer_token: str,
        namespace: str,
        agent_name: str = "cline",
        storage_dir: Optional[str] = None,
        auto_upload: bool = True,
        base_url: Optional[str] = None,
    ):
        self.client = MonkAIClient(tracer_token=tracer_token, base_url=base_url)
        self.namespace = namespace
        self.agent_name = agent_name
        self.auto_upload = auto_upload
        self._records: List[ConversationRecord] = []

        if storage_dir:
            self.storage_dir = Path(storage_dir).expanduser()
        else:
            self.storage_dir = self._detect_storage_dir()

    @staticmethod
    def _detect_storage_dir() -> Optional[Path]:
        """Auto-detect Cline storage directory."""
        for name, path in CLINE_STORAGE_PATHS.items():
            if path.is_dir():
                logger.info(f"Detected Cline storage ({name}): {path}")
                return path
        return None

    def upload_all_tasks(self) -> Dict:
        """
        Parse and upload all Cline tasks.

        Returns:
            Upload result dict.
        """
        if not self.storage_dir or not self.storage_dir.is_dir():
            raise FileNotFoundError(
                f"Cline tasks directory not found. "
                f"Checked: {list(CLINE_STORAGE_PATHS.values())}. "
                f"Pass storage_dir= to specify manually."
            )

        all_records: List[ConversationRecord] = []
        task_dirs = sorted(
            [d for d in self.storage_dir.iterdir() if d.is_dir()],
            key=lambda d: d.name,
        )

        for task_dir in task_dirs:
            records = self._parse_task(task_dir)
            all_records.extend(records)

        if not all_records:
            return {"total_inserted": 0, "total_records": 0, "failures": []}

        if self.auto_upload:
            result = self.client.upload_records_batch(all_records)
            logger.info(
                f"Uploaded {result['total_inserted']} records from "
                f"{len(task_dirs)} Cline tasks"
            )
            return result

        self._records.extend(all_records)
        return {"total_inserted": 0, "total_records": len(all_records), "failures": []}

    def upload_task(self, task_dir: str) -> Dict:
        """
        Parse and upload a specific Cline task.

        Args:
            task_dir: Path to the task directory.

        Returns:
            Upload result dict.
        """
        path = Path(task_dir).expanduser()
        if not path.is_dir():
            raise NotADirectoryError(f"Not a directory: {path}")

        records = self._parse_task(path)
        if not records:
            return {"total_inserted": 0, "total_records": 0, "failures": []}

        if self.auto_upload:
            result = self.client.upload_records_batch(records)
            logger.info(f"Uploaded {result['total_inserted']} records from task {path.name}")
            return result

        self._records.extend(records)
        return {"total_inserted": 0, "total_records": len(records), "failures": []}

    def list_tasks(self) -> List[Dict]:
        """List all Cline tasks with metadata."""
        if not self.storage_dir or not self.storage_dir.is_dir():
            return []

        tasks = []
        for task_dir in sorted(self.storage_dir.iterdir()):
            if not task_dir.is_dir():
                continue

            api_history = task_dir / "api_conversation_history.json"
            ui_messages = task_dir / "ui_messages.json"

            info = {
                "task_id": task_dir.name,
                "has_api_history": api_history.exists(),
                "has_ui_messages": ui_messages.exists(),
                "dir": str(task_dir),
            }

            # Try to get message count
            if api_history.exists():
                try:
                    data = json.loads(api_history.read_text(encoding="utf-8"))
                    info["message_count"] = len(data) if isinstance(data, list) else 0
                except Exception:
                    info["message_count"] = 0

            tasks.append(info)
        return tasks

    def flush(self) -> Dict:
        """Upload any buffered records."""
        if not self._records:
            return {"total_inserted": 0, "total_records": 0, "failures": []}
        result = self.client.upload_records_batch(self._records)
        self._records.clear()
        return result

    # ======================== PARSING ========================

    def _parse_task(self, task_dir: Path) -> List[ConversationRecord]:
        """Parse a Cline task directory into ConversationRecords."""
        api_history = task_dir / "api_conversation_history.json"
        if not api_history.exists():
            logger.debug(f"No api_conversation_history.json in {task_dir.name}")
            return []

        try:
            data = json.loads(api_history.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to read {api_history}: {e}")
            return []

        if not isinstance(data, list) or not data:
            return []

        task_id = task_dir.name
        return self._group_conversations(data, task_id)

    def _group_conversations(
        self, messages: List[Dict], task_id: str
    ) -> List[ConversationRecord]:
        """
        Group Cline API messages into conversation records.

        Each user->assistant exchange becomes one record.
        Tool results (role=user with tool_result content) are grouped
        with the preceding assistant tool_use.
        """
        records: List[ConversationRecord] = []
        current_messages: List[Message] = []
        token_counts = {"input": 0, "output": 0, "process": 0}

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "user":
                # Check if this is a tool_result (continuation of tool use)
                if isinstance(content, list) and any(
                    isinstance(b, dict) and b.get("type") == "tool_result"
                    for b in content
                ):
                    # Tool result — add as tool message
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_result":
                            result_content = block.get("content", "")
                            if isinstance(result_content, list):
                                result_content = " ".join(
                                    b.get("text", "") for b in result_content
                                    if isinstance(b, dict)
                                )
                            current_messages.append(Message(
                                role="tool",
                                content=str(result_content)[:500],
                                sender="cline",
                                tool_call_id=block.get("tool_use_id"),
                            ))
                            token_counts["process"] += len(str(result_content)) // 4
                    continue

                # Regular user message — start new turn if we have accumulated messages
                if current_messages:
                    record = self._build_record(current_messages, token_counts, task_id)
                    if record:
                        records.append(record)
                    current_messages = []
                    token_counts = {"input": 0, "output": 0, "process": 0}

                # Extract text content
                text = self._extract_text(content)
                if text:
                    current_messages.append(Message(
                        role="user", content=text, sender="user"
                    ))
                    token_counts["input"] += len(text) // 4

            elif role == "assistant":
                parsed = self._parse_assistant_content(content)
                for m in parsed["messages"]:
                    current_messages.append(m)
                token_counts["output"] += parsed["output_tokens"]
                token_counts["process"] += parsed["process_tokens"]

        # Last turn
        if current_messages:
            record = self._build_record(current_messages, token_counts, task_id)
            if record:
                records.append(record)

        logger.info(f"Parsed {len(records)} turns from Cline task {task_id}")
        return records

    def _parse_assistant_content(self, content: Any) -> Dict:
        """Parse assistant content blocks into Messages."""
        messages: List[Message] = []
        output_tokens = 0
        process_tokens = 0

        if isinstance(content, str):
            messages.append(Message(
                role="assistant", content=content, sender=self.agent_name
            ))
            output_tokens += len(content) // 4
            return {"messages": messages, "output_tokens": output_tokens, "process_tokens": process_tokens}

        if not isinstance(content, list):
            return {"messages": messages, "output_tokens": 0, "process_tokens": 0}

        text_parts = []
        tool_calls = []

        for block in content:
            if not isinstance(block, dict):
                continue

            btype = block.get("type", "")
            if btype == "text":
                text_parts.append(block.get("text", ""))
            elif btype == "tool_use":
                tool_name = block.get("name", "")
                tool_calls.append({
                    "name": tool_name,
                    "arguments": block.get("input", {}),
                    "id": block.get("id", ""),
                })
                process_tokens += len(str(block.get("input", {}))) // 4

        if text_parts:
            text = "\n".join(text_parts)
            messages.append(Message(
                role="assistant",
                content=text,
                sender=self.agent_name,
                tool_calls=tool_calls if tool_calls else None,
            ))
            output_tokens += len(text) // 4

        # Add tool messages
        for tc in tool_calls:
            tool_type = CLINE_TOOL_TYPES.get(tc["name"], tc["name"])
            messages.append(Message(
                role="tool",
                content=f"Tool: {tc['name']}",
                sender=self.agent_name,
                tool_name=tc["name"],
                internal_tool_type=tool_type,
                tool_calls=[tc],
            ))

        return {
            "messages": messages,
            "output_tokens": output_tokens,
            "process_tokens": process_tokens,
        }

    def _build_record(
        self,
        messages: List[Message],
        token_counts: Dict,
        task_id: str,
    ) -> Optional[ConversationRecord]:
        """Build a ConversationRecord from accumulated messages."""
        if not messages:
            return None

        return ConversationRecord(
            namespace=self.namespace,
            agent=self.agent_name,
            session_id=f"cline-{task_id}",
            msg=messages,
            input_tokens=token_counts.get("input", 0),
            output_tokens=token_counts.get("output", 0),
            process_tokens=token_counts.get("process", 0),
            total_tokens=sum(token_counts.values()),
            source="cline",
        )

    @staticmethod
    def _extract_text(content: Any) -> str:
        """Extract text from content (string or list of content blocks)."""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, str):
                    parts.append(block)
                elif isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
            return "\n".join(parts)
        return ""
