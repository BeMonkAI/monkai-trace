"""
OpenClaw integration for MonkAI Trace.

Parses OpenClaw session transcripts (JSONL) and uploads to MonkAI.

OpenClaw (https://github.com/openclaw/openclaw) is a personal AI assistant
that runs on your own devices, integrating with WhatsApp, Telegram, Slack,
Discord, and more.

Session transcripts are stored at:
    ~/.openclaw/agents/{agent_id}/sessions/{session_id}.jsonl

Each line is a JSON object with:
    {"message": {"role": "user|assistant|system|tool", "content": [...]}, "id": "..."}
    {"type": "compaction", "timestamp": "...", "id": "..."}

Usage and cost data is tracked per-session in the transcript.

Example:
    >>> from monkai_trace.integrations.openclaw import OpenClawTracer
    >>>
    >>> tracer = OpenClawTracer(
    ...     tracer_token="tk_your_token",
    ...     namespace="dev-productivity"
    ... )
    >>>
    >>> # Upload all sessions from default agent
    >>> tracer.upload_all_sessions()
    >>>
    >>> # Upload sessions from a specific agent
    >>> tracer.upload_agent_sessions("my-agent")
    >>>
    >>> # Upload a single session file
    >>> tracer.upload_session("~/.openclaw/agents/default/sessions/abc123.jsonl")
    >>>
    >>> # List available agents and sessions
    >>> tracer.list_agents()
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..client import MonkAIClient
from ..models import ConversationRecord, Message, TokenUsage

logger = logging.getLogger(__name__)


class OpenClawTracer:
    """
    Parse OpenClaw session transcripts and upload to MonkAI Trace.

    Args:
        tracer_token: MonkAI tracer token (starts with 'tk_')
        namespace: Namespace for organizing conversations
        agent_name: Agent name in MonkAI (default: "openclaw")
        state_dir: Custom OpenClaw state directory (default: ~/.openclaw)
        auto_upload: Upload immediately (default: True)
        base_url: Optional custom API base URL
    """

    DEFAULT_STATE_DIR = Path.home() / ".openclaw"

    def __init__(
        self,
        tracer_token: str,
        namespace: str,
        agent_name: str = "openclaw",
        state_dir: Optional[str] = None,
        auto_upload: bool = True,
        base_url: Optional[str] = None,
    ):
        self.client = MonkAIClient(tracer_token=tracer_token, base_url=base_url)
        self.namespace = namespace
        self.agent_name = agent_name
        self.auto_upload = auto_upload
        self._records: List[ConversationRecord] = []

        env_dir = os.environ.get("OPENCLAW_STATE_DIR")
        if state_dir:
            self.state_dir = Path(state_dir).expanduser()
        elif env_dir:
            self.state_dir = Path(env_dir).expanduser()
        else:
            self.state_dir = self.DEFAULT_STATE_DIR

    def upload_all_sessions(self) -> Dict:
        """
        Upload all sessions from all agents.

        Returns:
            Upload result dict.
        """
        agents_dir = self.state_dir / "agents"
        if not agents_dir.is_dir():
            raise FileNotFoundError(
                f"OpenClaw agents directory not found: {agents_dir}. "
                f"Is OpenClaw installed? Set state_dir= or OPENCLAW_STATE_DIR."
            )

        all_records: List[ConversationRecord] = []
        for agent_dir in sorted(agents_dir.iterdir()):
            if not agent_dir.is_dir():
                continue
            sessions_dir = agent_dir / "sessions"
            if not sessions_dir.is_dir():
                continue
            for jsonl in sorted(sessions_dir.glob("*.jsonl")):
                records = self._parse_session(jsonl, agent_dir.name)
                all_records.extend(records)

        if not all_records:
            return {"total_inserted": 0, "total_records": 0, "failures": []}

        if self.auto_upload:
            result = self.client.upload_records_batch(all_records)
            logger.info(f"Uploaded {result['total_inserted']} OpenClaw records")
            return result

        self._records.extend(all_records)
        return {"total_inserted": 0, "total_records": len(all_records), "failures": []}

    def upload_agent_sessions(self, agent_id: str = "default") -> Dict:
        """
        Upload all sessions from a specific OpenClaw agent.

        Args:
            agent_id: Agent ID (default: "default")

        Returns:
            Upload result dict.
        """
        sessions_dir = self.state_dir / "agents" / agent_id / "sessions"
        if not sessions_dir.is_dir():
            raise FileNotFoundError(f"Sessions directory not found: {sessions_dir}")

        all_records: List[ConversationRecord] = []
        for jsonl in sorted(sessions_dir.glob("*.jsonl")):
            records = self._parse_session(jsonl, agent_id)
            all_records.extend(records)

        if not all_records:
            return {"total_inserted": 0, "total_records": 0, "failures": []}

        if self.auto_upload:
            result = self.client.upload_records_batch(all_records)
            logger.info(
                f"Uploaded {result['total_inserted']} records from agent '{agent_id}'"
            )
            return result

        self._records.extend(all_records)
        return {"total_inserted": 0, "total_records": len(all_records), "failures": []}

    def upload_session(self, session_path: str) -> Dict:
        """
        Upload a single session JSONL file.

        Args:
            session_path: Path to the .jsonl session file.

        Returns:
            Upload result dict.
        """
        path = Path(session_path).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"Session file not found: {path}")

        # Infer agent_id from path: .../agents/{agent_id}/sessions/{file}.jsonl
        parts = path.parts
        agent_id = "unknown"
        for i, part in enumerate(parts):
            if part == "agents" and i + 1 < len(parts):
                agent_id = parts[i + 1]
                break

        records = self._parse_session(path, agent_id)
        if not records:
            return {"total_inserted": 0, "total_records": 0, "failures": []}

        if self.auto_upload:
            result = self.client.upload_records_batch(records)
            logger.info(f"Uploaded {result['total_inserted']} records from {path.name}")
            return result

        self._records.extend(records)
        return {"total_inserted": 0, "total_records": len(records), "failures": []}

    def list_agents(self) -> List[Dict]:
        """List all OpenClaw agents with session counts."""
        agents_dir = self.state_dir / "agents"
        if not agents_dir.is_dir():
            return []

        agents = []
        for agent_dir in sorted(agents_dir.iterdir()):
            if not agent_dir.is_dir():
                continue
            sessions_dir = agent_dir / "sessions"
            session_count = len(list(sessions_dir.glob("*.jsonl"))) if sessions_dir.is_dir() else 0
            agents.append({
                "agent_id": agent_dir.name,
                "session_count": session_count,
                "dir": str(agent_dir),
            })
        return agents

    def flush(self) -> Dict:
        """Upload any buffered records."""
        if not self._records:
            return {"total_inserted": 0, "total_records": 0, "failures": []}
        result = self.client.upload_records_batch(self._records)
        self._records.clear()
        return result

    # ======================== PARSING ========================

    def _parse_session(self, path: Path, agent_id: str) -> List[ConversationRecord]:
        """Parse an OpenClaw session JSONL into ConversationRecords."""
        lines = self._read_jsonl(path)
        if not lines:
            return []

        session_id = path.stem
        turns = self._group_turns(lines)
        records = []

        for user_content, assistant_contents in turns:
            messages = []

            # User message
            messages.append(Message(
                role="user",
                content=user_content,
                sender="user",
            ))

            # Assistant messages
            for acontent, tools in assistant_contents:
                messages.append(Message(
                    role="assistant",
                    content=acontent,
                    sender=f"openclaw/{agent_id}",
                    tool_calls=tools if tools else None,
                ))
                for tc in (tools or []):
                    messages.append(Message(
                        role="tool",
                        content=f"Tool: {tc.get('name', 'unknown')}",
                        sender=self.agent_name,
                        tool_name=tc.get("name"),
                        tool_calls=[tc],
                    ))

            # Estimate tokens from content
            total_input = sum(len(str(m.content or "")) // 4 for m in messages if m.role == "user")
            total_output = sum(len(str(m.content or "")) // 4 for m in messages if m.role == "assistant")
            total_process = sum(len(str(m.content or "")) // 4 for m in messages if m.role == "tool")

            record = ConversationRecord(
                namespace=self.namespace,
                agent=f"{self.agent_name}/{agent_id}" if agent_id != "default" else self.agent_name,
                session_id=f"openclaw-{session_id}",
                msg=messages,
                input_tokens=total_input,
                output_tokens=total_output,
                process_tokens=total_process,
                total_tokens=total_input + total_output + total_process,
                source="openclaw",
            )
            records.append(record)

        logger.info(f"Parsed {len(records)} turns from OpenClaw session {path.name}")
        return records

    def _group_turns(
        self, lines: List[Dict]
    ) -> List[Tuple[str, List[Tuple[str, List[Dict]]]]]:
        """
        Group JSONL lines into conversation turns.

        Returns list of (user_text, [(assistant_text, tool_calls), ...]) tuples.
        """
        turns: List[Tuple[str, List[Tuple[str, List[Dict]]]]] = []
        current_user: Optional[str] = None
        current_assistants: List[Tuple[str, List[Dict]]] = []

        for line in lines:
            message = line.get("message")
            if not message:
                continue

            role = message.get("role", "")
            content = message.get("content", "")

            if role == "user":
                if current_user is not None and current_assistants:
                    turns.append((current_user, current_assistants))

                current_user = self._extract_text(content)
                current_assistants = []

            elif role == "assistant":
                text = self._extract_text(content)
                tools = self._extract_tool_calls(content)
                if text or tools:
                    current_assistants.append((text, tools))

        # Last turn
        if current_user is not None and current_assistants:
            turns.append((current_user, current_assistants))

        return turns

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
                elif isinstance(block, dict):
                    if block.get("type") == "text":
                        parts.append(block.get("text", ""))
            return "\n".join(parts)
        return ""

    @staticmethod
    def _extract_tool_calls(content: Any) -> List[Dict]:
        """Extract tool_use blocks from content."""
        if not isinstance(content, list):
            return []
        tools = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                tools.append({
                    "name": block.get("name", ""),
                    "arguments": block.get("input", {}),
                    "id": block.get("id", ""),
                })
        return tools

    @staticmethod
    def _read_jsonl(path: Path) -> List[Dict]:
        """Read a JSONL file, skipping invalid lines."""
        lines = []
        with open(path, "r", encoding="utf-8") as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    lines.append(json.loads(raw))
                except json.JSONDecodeError:
                    continue
        return lines
