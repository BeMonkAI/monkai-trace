"""
Claude Code integration for MonkAI Trace.

Parses Claude Code session JSONL logs and uploads conversations to MonkAI.

Claude Code stores sessions as JSONL files at:
    ~/.claude/projects/{encoded_path}/{session_uuid}.jsonl

Each line is a JSON object with a "type" field:
    - user: User message
    - assistant: Claude response (text, tool_use, thinking)
    - progress: Tool execution progress
    - file-history-snapshot: File state snapshots
    - system: System events

Example:
    >>> from monkai_trace.integrations.claude_code import ClaudeCodeTracer
    >>>
    >>> tracer = ClaudeCodeTracer(
    ...     tracer_token="tk_your_token",
    ...     namespace="dev-productivity"
    ... )
    >>>
    >>> # Parse and upload a specific session
    >>> tracer.upload_session("~/.claude/projects/-Users-me/abc123.jsonl")
    >>>
    >>> # Parse all sessions from a project
    >>> tracer.upload_project("~/.claude/projects/-Users-me/")
    >>>
    >>> # Watch for new sessions in real-time
    >>> tracer.watch("~/.claude/projects/-Users-me/")
"""

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..client import MonkAIClient
from ..models import ConversationRecord, Message, TokenUsage

logger = logging.getLogger(__name__)


class ClaudeCodeTracer:
    """
    Parse Claude Code JSONL session logs and upload to MonkAI Trace.

    Args:
        tracer_token: MonkAI tracer token (starts with 'tk_')
        namespace: Namespace for organizing conversations
        agent_name: Agent name in MonkAI (default: "claude-code")
        auto_upload: Upload records immediately after parsing (default: True)
        base_url: Optional custom API base URL
    """

    # Claude Code stores projects with path separators replaced by hyphens
    CLAUDE_DIR = Path.home() / ".claude"
    PROJECTS_DIR = CLAUDE_DIR / "projects"

    def __init__(
        self,
        tracer_token: str,
        namespace: str,
        agent_name: str = "claude-code",
        auto_upload: bool = True,
        base_url: Optional[str] = None,
    ):
        self.client = MonkAIClient(tracer_token=tracer_token, base_url=base_url)
        self.namespace = namespace
        self.agent_name = agent_name
        self.auto_upload = auto_upload
        self._records: List[ConversationRecord] = []

    def upload_session(self, session_path: str) -> Dict:
        """
        Parse a single Claude Code session JSONL and upload to MonkAI.

        Args:
            session_path: Path to the .jsonl session file.

        Returns:
            Upload result dict with counts.
        """
        path = Path(session_path).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"Session file not found: {path}")

        records = self._parse_session(path)
        if not records:
            logger.info(f"No conversations found in {path.name}")
            return {"total_inserted": 0, "total_records": 0, "failures": []}

        if self.auto_upload:
            result = self.client.upload_records_batch(records)
            logger.info(f"Uploaded {result['total_inserted']} records from {path.name}")
            return result

        self._records.extend(records)
        return {"total_inserted": 0, "total_records": len(records), "failures": []}

    def upload_session_incremental(self, session_path: str) -> Dict:
        """Parse a session and upload only the turns not uploaded before.

        Uses a per-``session_id`` offset persisted on disk (see
        :func:`_load_offsets`) so the same growing transcript can be uploaded
        repeatedly — e.g. on every Claude Code ``Stop`` event — without
        duplicating turns. Also makes ``SessionEnd`` safe to re-fire (resumed
        sessions no longer re-upload in full).

        Args:
            session_path: Path to the .jsonl session file.

        Returns:
            Upload result dict with counts (``skipped`` = turns already sent).
        """
        path = Path(session_path).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"Session file not found: {path}")

        records = self._parse_session(path)
        session_id = path.stem
        already = _load_offsets().get(session_id, 0)
        new_records = records[already:]

        if not new_records:
            logger.info(
                "No new turns in %s (offset=%d, total=%d)",
                path.name,
                already,
                len(records),
            )
            return {
                "total_inserted": 0,
                "total_records": 0,
                "failures": [],
                "skipped": already,
            }

        if self.auto_upload:
            result = self.client.upload_records_batch(new_records)
            _save_offset(session_id, len(records))
            logger.info(
                "Uploaded %s new turns from %s (was %d, now %d)",
                result.get("total_inserted", 0),
                path.name,
                already,
                len(records),
            )
            result["skipped"] = already
            return result

        self._records.extend(new_records)
        return {
            "total_inserted": 0,
            "total_records": len(new_records),
            "failures": [],
            "skipped": already,
        }

    def watch(
        self,
        project_dir: str,
        interval: float = 5.0,
        max_iterations: Optional[int] = None,
    ) -> Dict:
        """Poll a project directory and incrementally upload sessions.

        For environments without a Claude Code hook. Every ``interval`` seconds
        it scans ``project_dir`` for ``*.jsonl`` sessions and uploads any new
        turns via :meth:`upload_session_incremental`. Runs until interrupted
        (or ``max_iterations`` is reached, used by tests).

        Args:
            project_dir: Claude Code project directory to watch.
            interval: Seconds between scans.
            max_iterations: Stop after this many scans (``None`` = forever).

        Returns:
            Aggregate counts across the watch run.
        """
        path = Path(project_dir).expanduser()
        if not path.is_dir():
            raise NotADirectoryError(f"Not a directory: {path}")

        total_inserted = 0
        iterations = 0
        try:
            while max_iterations is None or iterations < max_iterations:
                for jsonl_file in sorted(path.glob("*.jsonl")):
                    try:
                        result = self.upload_session_incremental(str(jsonl_file))
                        total_inserted += result.get("total_inserted", 0)
                    except Exception:  # noqa: BLE001 - keep watching on errors
                        logger.exception("watch: failed on %s", jsonl_file.name)
                iterations += 1
                if max_iterations is not None and iterations >= max_iterations:
                    break
                time.sleep(interval)
        except KeyboardInterrupt:
            logger.info("watch: stopped by user")
        return {"total_inserted": total_inserted, "iterations": iterations}

    def upload_project(self, project_dir: str) -> Dict:
        """
        Parse all sessions in a Claude Code project directory.

        Args:
            project_dir: Path to the project directory
                (e.g., ~/.claude/projects/-Users-me/)

        Returns:
            Aggregated upload result.
        """
        path = Path(project_dir).expanduser()
        if not path.is_dir():
            raise NotADirectoryError(f"Not a directory: {path}")

        all_records: List[ConversationRecord] = []
        for jsonl_file in sorted(path.glob("*.jsonl")):
            records = self._parse_session(jsonl_file)
            all_records.extend(records)

        if not all_records:
            logger.info(f"No conversations found in {path}")
            return {"total_inserted": 0, "total_records": 0, "failures": []}

        if self.auto_upload:
            result = self.client.upload_records_batch(all_records)
            logger.info(
                f"Uploaded {result['total_inserted']} records "
                f"from {len(list(path.glob('*.jsonl')))} sessions"
            )
            return result

        self._records.extend(all_records)
        return {
            "total_inserted": 0,
            "total_records": len(all_records),
            "failures": [],
        }

    def upload_all_projects(self) -> Dict:
        """Parse and upload all Claude Code projects found in ~/.claude/projects/."""
        if not self.PROJECTS_DIR.is_dir():
            raise FileNotFoundError(f"Claude projects dir not found: {self.PROJECTS_DIR}")

        total_inserted = 0
        total_records = 0
        failures = []

        for project_dir in sorted(self.PROJECTS_DIR.iterdir()):
            if not project_dir.is_dir():
                continue
            try:
                result = self.upload_project(str(project_dir))
                total_inserted += result.get("total_inserted", 0)
                total_records += result.get("total_records", 0)
                failures.extend(result.get("failures", []))
            except Exception as e:
                failures.append({"project": project_dir.name, "error": str(e)})

        return {
            "total_inserted": total_inserted,
            "total_records": total_records,
            "failures": failures,
        }

    def list_projects(self) -> List[Dict]:
        """List all Claude Code projects with session counts."""
        if not self.PROJECTS_DIR.is_dir():
            return []

        projects = []
        for project_dir in sorted(self.PROJECTS_DIR.iterdir()):
            if not project_dir.is_dir():
                continue
            sessions = list(project_dir.glob("*.jsonl"))
            # Decode project path: -Users-me-project -> /Users/me/project
            decoded_path = "/" + project_dir.name.lstrip("-").replace("-", "/")
            projects.append(
                {
                    "encoded_name": project_dir.name,
                    "decoded_path": decoded_path,
                    "session_count": len(sessions),
                    "dir": str(project_dir),
                }
            )
        return projects

    def flush(self) -> Dict:
        """Upload any buffered records."""
        if not self._records:
            return {"total_inserted": 0, "total_records": 0, "failures": []}

        result = self.client.upload_records_batch(self._records)
        self._records.clear()
        return result

    # ======================== PARSING ========================

    def _parse_session(self, path: Path) -> List[ConversationRecord]:
        """
        Parse a JSONL session file into ConversationRecords.

        Groups messages into conversation turns (user -> assistant).
        Each turn becomes one ConversationRecord.
        """
        lines = self._read_jsonl(path)
        if not lines:
            return []

        session_id = path.stem  # UUID filename without extension

        # Group into conversation turns
        turns = self._group_turns(lines)
        records = []

        for user_msg, assistant_msgs, usage in turns:
            messages = []

            # User message
            messages.append(
                Message(
                    role="user",
                    content=user_msg.get("content", ""),
                    sender="user",
                )
            )

            # Assistant messages (text, tool_use, etc.)
            for amsg in assistant_msgs:
                content_blocks = amsg.get("content", [])
                text_parts = []
                tool_calls = []

                for block in content_blocks:
                    if isinstance(block, str):
                        text_parts.append(block)
                    elif isinstance(block, dict):
                        btype = block.get("type", "")
                        if btype == "text":
                            text_parts.append(block.get("text", ""))
                        elif btype == "tool_use":
                            tool_calls.append(
                                {
                                    "name": block.get("name", ""),
                                    "arguments": block.get("input", {}),
                                    "id": block.get("id", ""),
                                }
                            )
                        # Skip thinking blocks

                content = "\n".join(text_parts) if text_parts else None
                model = amsg.get("model", "")

                msg = Message(
                    role="assistant",
                    content=content,
                    sender=model or self.agent_name,
                    tool_calls=tool_calls if tool_calls else None,
                )
                messages.append(msg)

                # Add tool messages for each tool call
                for tc in tool_calls:
                    messages.append(
                        Message(
                            role="tool",
                            content=f"Tool: {tc['name']}",
                            sender=self.agent_name,
                            tool_name=tc["name"],
                            tool_calls=[tc],
                        )
                    )

            # Build token usage
            token_usage = TokenUsage.from_anthropic_usage(usage) if usage else TokenUsage()

            # Extract model from the last assistant message
            model_name = None
            if assistant_msgs:
                model_name = assistant_msgs[-1].get("model", "") or None

            record = ConversationRecord(
                namespace=self.namespace,
                agent=self.agent_name,
                session_id=session_id,
                msg=messages,
                input_tokens=token_usage.input_tokens,
                output_tokens=token_usage.output_tokens,
                process_tokens=token_usage.process_tokens,
                memory_tokens=token_usage.memory_tokens,
                total_tokens=token_usage.total_tokens,
                source="claude-code",
                model=model_name,
            )
            records.append(record)

        logger.info(f"Parsed {len(records)} conversation turns from {path.name}")
        return records

    def _group_turns(self, lines: List[Dict]) -> List[Tuple[Dict, List[Dict], Dict]]:
        """
        Group JSONL lines into conversation turns.

        Each turn is: (user_message_content, [assistant_messages], aggregated_usage)

        Returns list of (user_msg, assistant_msgs, usage) tuples.
        """
        turns: List[Tuple[Dict, List[Dict], Dict]] = []
        current_user: Optional[Dict] = None
        current_assistants: List[Dict] = []
        current_usage: Dict = {}

        for line in lines:
            msg_type = line.get("type", "")

            if msg_type == "user":
                # New turn starts
                if current_user is not None and current_assistants:
                    turns.append(
                        (
                            current_user,
                            current_assistants,
                            current_usage,
                        )
                    )

                user_message = line.get("message", {})
                content = user_message.get("content", "")
                # Content can be string or list of content blocks
                if isinstance(content, list):
                    text_parts = []
                    for block in content:
                        if isinstance(block, str):
                            text_parts.append(block)
                        elif isinstance(block, dict) and block.get("type") == "text":
                            text_parts.append(block.get("text", ""))
                    content = "\n".join(text_parts)

                current_user = {"content": content}
                current_assistants = []
                current_usage = {}

            elif msg_type == "assistant":
                message = line.get("message", {})
                content = message.get("content", [])
                model = message.get("model", "")
                usage = message.get("usage", {})

                # Aggregate usage (take the last non-empty one)
                if usage and usage.get("output_tokens", 0) > 0:
                    current_usage = usage

                # Only add if has meaningful content (text or tool_use)
                has_content = False
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict):
                            btype = block.get("type", "")
                            if btype in ("text", "tool_use"):
                                has_content = True
                                break

                if has_content:
                    current_assistants.append(
                        {
                            "content": content,
                            "model": model,
                        }
                    )

        # Don't forget the last turn
        if current_user is not None and current_assistants:
            turns.append((current_user, current_assistants, current_usage))

        return turns

    @staticmethod
    def _read_jsonl(path: Path) -> List[Dict]:
        """Read a JSONL file, skipping invalid lines."""
        lines = []
        with open(path, "r", encoding="utf-8") as f:
            for line_num, raw in enumerate(f, 1):
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    lines.append(json.loads(raw))
                except json.JSONDecodeError:
                    logger.debug(f"Skipped invalid JSON at {path.name}:{line_num}")
        return lines

    @staticmethod
    def decode_project_path(encoded: str) -> str:
        """Decode Claude Code encoded project path.

        Example: '-Users-arthurvaz-Desktop' -> '/Users/arthurvaz/Desktop'
        """
        return "/" + encoded.lstrip("-").replace("-", "/")

    @staticmethod
    def encode_project_path(path: str) -> str:
        """Encode a filesystem path to Claude Code format.

        Example: '/Users/arthurvaz/Desktop' -> '-Users-arthurvaz-Desktop'
        """
        return path.replace("/", "-")


# Default public base URL for the hook (Vercel proxy → Supabase).
DEFAULT_HOOK_BASE_URL = "https://api.monkai.com.br/trace/v1"

# Where per-session upload offsets and (default) the token file live.
DEFAULT_STATE_DIR = Path.home() / ".monkai_trace"
DEFAULT_TOKEN_FILE = Path.home() / ".monkai_trace_token"


def _state_dir() -> Path:
    return Path(os.environ.get("MONKAI_TRACE_STATE_DIR", str(DEFAULT_STATE_DIR))).expanduser()


def _offsets_path() -> Path:
    return _state_dir() / "offsets.json"


def _load_offsets() -> Dict[str, int]:
    """Load the per-session upload offsets; tolerant of missing/corrupt files."""
    path = _offsets_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {k: int(v) for k, v in data.items()} if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError, ValueError, TypeError):
        logger.warning("Could not read offsets at %s; starting fresh", path)
        return {}


def _save_offset(session_id: str, count: int) -> None:
    """Persist the uploaded-turn count for a session (best-effort)."""
    offsets = _load_offsets()
    offsets[session_id] = count
    path = _offsets_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(offsets), encoding="utf-8")
    except OSError:
        logger.warning("Could not persist offset for %s at %s", session_id, path)


def resolve_token() -> Optional[str]:
    """Resolve the tracer token from the environment or a token file.

    Order: ``MONKAI_TRACE_TOKEN`` env var, then the token file pointed to by
    ``MONKAI_TRACE_TOKEN_FILE`` (default ``~/.monkai_trace_token``). The file
    fallback makes the hook robust even when the shell profile that exports the
    env var is not sourced by the hook runner.
    """
    token = os.environ.get("MONKAI_TRACE_TOKEN")
    if token:
        return token.strip()
    token_file = Path(
        os.environ.get("MONKAI_TRACE_TOKEN_FILE", str(DEFAULT_TOKEN_FILE))
    ).expanduser()
    if token_file.exists():
        try:
            value = token_file.read_text(encoding="utf-8").strip()
            if value:
                return value
        except OSError:
            logger.warning("Could not read token file at %s", token_file)
    return None


def run_hook(stdin=None) -> int:
    """Entrypoint for the Claude Code ``SessionEnd``/``Stop`` hook.

    Reads the hook payload as JSON from stdin (Claude Code provides
    ``{session_id, transcript_path, cwd, reason, ...}``), then uploads only the
    turns not uploaded before (incremental), so the same growing transcript can
    fire on every ``Stop`` without duplicating, and resumed ``SessionEnd`` is
    safe too.

    Configuration is resolved with zero arguments:

    - token: ``MONKAI_TRACE_TOKEN`` env, else ``MONKAI_TRACE_TOKEN_FILE``
      (default ``~/.monkai_trace_token``). See :func:`resolve_token`.
    - ``MONKAI_TRACE_NAMESPACE`` (optional, default ``claude-code``).
    - ``MONKAI_TRACE_BASE_URL`` (optional, default the public proxy).

    This function NEVER raises: a hook that fails must not break the user's
    Claude Code session. All failures are logged and swallowed, returning 0.

    Returns:
        Always 0 (success exit code for the hook runner).
    """
    try:
        raw = (stdin or sys.stdin).read()
        payload = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, ValueError, OSError) as exc:
        logger.warning("Could not read Claude Code hook payload: %s", exc)
        return 0

    transcript = payload.get("transcript_path")
    if not transcript:
        logger.info("Hook payload has no transcript_path; nothing to upload")
        return 0

    token = resolve_token()
    if not token:
        logger.warning(
            "No tracer token (MONKAI_TRACE_TOKEN env or token file); "
            "skipping Claude Code trace upload"
        )
        return 0

    try:
        tracer = ClaudeCodeTracer(
            tracer_token=token,
            namespace=os.environ.get("MONKAI_TRACE_NAMESPACE", "claude-code"),
            base_url=os.environ.get("MONKAI_TRACE_BASE_URL", DEFAULT_HOOK_BASE_URL),
        )
        result = tracer.upload_session_incremental(transcript)
        logger.info(
            "Claude Code trace: %s new turns uploaded",
            result.get("total_inserted", 0),
        )
    except Exception:  # noqa: BLE001 - hook must never crash the session
        logger.exception("Failed to upload Claude Code session trace")

    return 0
