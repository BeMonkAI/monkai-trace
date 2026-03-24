"""
GitHub Copilot integration for MonkAI Trace.

Parses Copilot usage data from multiple sources:
1. VS Code Copilot Chat history (local)
2. GitHub Copilot Business/Enterprise audit logs (API)
3. Copilot usage metrics API (org-level)

Copilot Chat stores conversation history at (macOS):
    ~/Library/Application Support/Code/User/workspaceStorage/<hash>/
        github.copilot-chat/conversations.json

GitHub API endpoints:
    GET /orgs/{org}/copilot/usage  — Usage metrics
    GET /orgs/{org}/audit-log?action=copilot  — Audit log (Business/Enterprise)

Example:
    >>> from monkai_trace.integrations.copilot import CopilotTracer
    >>>
    >>> tracer = CopilotTracer(
    ...     tracer_token="tk_your_token",
    ...     namespace="dev-productivity"
    ... )
    >>>
    >>> # Parse local Copilot Chat conversations
    >>> tracer.upload_chat_history()
    >>>
    >>> # Fetch org usage via GitHub API
    >>> tracer.upload_org_usage(
    ...     github_token="ghp_xxx",
    ...     org="BeMonkAI"
    ... )
    >>>
    >>> # Parse exported Copilot metrics CSV
    >>> tracer.upload_from_csv("copilot_usage.csv")
"""

import csv
import json
import logging
import os
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..client import MonkAIClient
from ..models import ConversationRecord, LogEntry, Message, TokenUsage

logger = logging.getLogger(__name__)

# VS Code workspace storage base paths
_VSCODE_STORAGE_PATHS = {
    "darwin": Path.home() / "Library/Application Support/Code/User/workspaceStorage",
    "linux": Path.home() / ".config/Code/User/workspaceStorage",
    "win32": Path.home() / "AppData/Roaming/Code/User/workspaceStorage",
}


class CopilotTracer:
    """
    Parse GitHub Copilot data and upload to MonkAI Trace.

    Supports:
    - VS Code Copilot Chat conversations (local files)
    - GitHub Copilot usage API (org-level metrics)
    - CSV export parsing (from GitHub admin dashboard)

    Args:
        tracer_token: MonkAI tracer token (starts with 'tk_')
        namespace: Namespace for organizing data
        agent_name: Agent name in MonkAI (default: "copilot")
        auto_upload: Upload immediately (default: True)
        base_url: Optional custom API base URL
    """

    def __init__(
        self,
        tracer_token: str,
        namespace: str,
        agent_name: str = "copilot",
        auto_upload: bool = True,
        base_url: Optional[str] = None,
    ):
        self.client = MonkAIClient(tracer_token=tracer_token, base_url=base_url)
        self.namespace = namespace
        self.agent_name = agent_name
        self.auto_upload = auto_upload
        self._records: List[ConversationRecord] = []

    # ======================== CHAT HISTORY ========================

    def upload_chat_history(
        self, storage_dir: Optional[str] = None
    ) -> Dict:
        """
        Parse VS Code Copilot Chat conversation history and upload.

        Searches all VS Code workspace storage directories for
        github.copilot-chat/conversations.json files.

        Args:
            storage_dir: Custom workspace storage path (auto-detected if None)

        Returns:
            Upload result dict.
        """
        base = self._get_storage_dir(storage_dir)
        if not base or not base.is_dir():
            raise FileNotFoundError(
                f"VS Code workspace storage not found. "
                f"Checked: {list(_VSCODE_STORAGE_PATHS.values())}"
            )

        all_records: List[ConversationRecord] = []
        conversation_files = list(base.rglob("github.copilot-chat/conversations.json"))

        if not conversation_files:
            logger.info("No Copilot Chat conversations found")
            return {"total_inserted": 0, "total_records": 0, "failures": []}

        for conv_file in conversation_files:
            records = self._parse_conversations_file(conv_file)
            all_records.extend(records)

        if not all_records:
            return {"total_inserted": 0, "total_records": 0, "failures": []}

        if self.auto_upload:
            result = self.client.upload_records_batch(all_records)
            logger.info(
                f"Uploaded {result['total_inserted']} Copilot Chat records "
                f"from {len(conversation_files)} workspace(s)"
            )
            return result

        self._records.extend(all_records)
        return {"total_inserted": 0, "total_records": len(all_records), "failures": []}

    # ======================== GITHUB API ========================

    def upload_org_usage(
        self,
        github_token: str,
        org: str,
        since: Optional[str] = None,
        until: Optional[str] = None,
    ) -> Dict:
        """
        Fetch Copilot usage metrics from GitHub API and upload as logs.

        Requires GitHub org admin access and Copilot Business/Enterprise.

        Args:
            github_token: GitHub personal access token with org:read scope
            org: GitHub organization name
            since: Start date (YYYY-MM-DD), default: 28 days ago
            until: End date (YYYY-MM-DD), default: today

        Returns:
            Upload result dict.
        """
        try:
            import requests
        except ImportError:
            raise ImportError("requests is required: pip install requests")

        headers = {
            "Authorization": f"Bearer {github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        url = f"https://api.github.com/orgs/{org}/copilot/usage"
        params = {}
        if since:
            params["since"] = since
        if until:
            params["until"] = until

        response = requests.get(url, headers=headers, params=params, timeout=30)

        if response.status_code == 404:
            raise ValueError(
                f"Copilot usage API not available for org '{org}'. "
                "Requires Copilot Business or Enterprise."
            )
        if response.status_code == 401:
            raise ValueError("Invalid GitHub token or insufficient permissions")

        response.raise_for_status()
        data = response.json()

        usage_days = data if isinstance(data, list) else data.get("usage", [])
        if not usage_days:
            return {"total_inserted": 0, "total_logs": 0, "failures": []}

        logs = self._usage_to_logs(usage_days, org)

        if self.auto_upload:
            result = self.client.upload_logs_batch(logs)
            logger.info(f"Uploaded {len(logs)} Copilot usage logs for {org}")
            return result

        return {"total_inserted": 0, "total_logs": len(logs), "failures": []}

    # ======================== CSV IMPORT ========================

    def upload_from_csv(self, csv_path: str) -> Dict:
        """
        Parse a Copilot usage CSV export and upload as logs.

        Expected CSV columns (from GitHub admin export):
            date, user, editor, language, suggestions_shown,
            suggestions_accepted, lines_suggested, lines_accepted

        Args:
            csv_path: Path to the CSV file

        Returns:
            Upload result dict.
        """
        path = Path(csv_path).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"CSV not found: {path}")

        text = path.read_text(encoding="utf-8")
        reader = csv.DictReader(StringIO(text))

        logs = []
        for row in reader:
            date = row.get("date", row.get("day", ""))
            user = row.get("user", row.get("login", "unknown"))
            editor = row.get("editor", row.get("ide", "unknown"))
            language = row.get("language", "")
            suggestions_shown = int(row.get("suggestions_shown", row.get("shown", 0)) or 0)
            suggestions_accepted = int(row.get("suggestions_accepted", row.get("accepted", 0)) or 0)
            lines_suggested = int(row.get("lines_suggested", 0) or 0)
            lines_accepted = int(row.get("lines_accepted", 0) or 0)

            acceptance_rate = (
                round(suggestions_accepted / suggestions_shown * 100, 1)
                if suggestions_shown > 0
                else 0
            )

            log = LogEntry(
                namespace=self.namespace,
                level="info",
                message=f"Copilot usage: {user} ({editor}) - {acceptance_rate}% acceptance",
                timestamp=date,
                resource_id=f"copilot-{user}-{date}",
                custom_object={
                    "source": "copilot",
                    "user": user,
                    "editor": editor,
                    "language": language,
                    "suggestions_shown": suggestions_shown,
                    "suggestions_accepted": suggestions_accepted,
                    "lines_suggested": lines_suggested,
                    "lines_accepted": lines_accepted,
                    "acceptance_rate": acceptance_rate,
                },
            )
            logs.append(log)

        if not logs:
            return {"total_inserted": 0, "total_logs": 0, "failures": []}

        if self.auto_upload:
            result = self.client.upload_logs_batch(logs)
            logger.info(f"Uploaded {len(logs)} Copilot usage entries from CSV")
            return result

        return {"total_inserted": 0, "total_logs": len(logs), "failures": []}

    def flush(self) -> Dict:
        """Upload any buffered records."""
        if not self._records:
            return {"total_inserted": 0, "total_records": 0, "failures": []}
        result = self.client.upload_records_batch(self._records)
        self._records.clear()
        return result

    # ======================== INTERNAL ========================

    def _parse_conversations_file(self, path: Path) -> List[ConversationRecord]:
        """Parse a Copilot Chat conversations.json file."""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to read {path}: {e}")
            return []

        # conversations.json can be a list or dict with "conversations" key
        conversations = data if isinstance(data, list) else data.get("conversations", [])
        records = []

        for conv in conversations:
            record = self._parse_conversation(conv)
            if record:
                records.append(record)

        logger.info(f"Parsed {len(records)} Copilot conversations from {path}")
        return records

    def _parse_conversation(self, conv: Dict) -> Optional[ConversationRecord]:
        """Parse a single Copilot Chat conversation."""
        turns = conv.get("turns", conv.get("messages", []))
        if not turns:
            return None

        conv_id = conv.get("id", conv.get("conversationId", ""))
        messages: List[Message] = []
        total_input = 0
        total_output = 0

        for turn in turns:
            role = turn.get("role", turn.get("type", ""))
            content = turn.get("content", turn.get("text", turn.get("message", "")))

            # Normalize role
            if role in ("human", "user", "question"):
                role = "user"
            elif role in ("bot", "assistant", "answer", "model"):
                role = "assistant"

            if isinstance(content, list):
                content = "\n".join(
                    b.get("text", str(b)) if isinstance(b, dict) else str(b)
                    for b in content
                )

            if not content:
                continue

            messages.append(Message(
                role=role,
                content=content,
                sender="user" if role == "user" else self.agent_name,
            ))

            # Estimate tokens
            tokens = len(str(content)) // 4
            if role == "user":
                total_input += tokens
            else:
                total_output += tokens

        if not messages:
            return None

        return ConversationRecord(
            namespace=self.namespace,
            agent=self.agent_name,
            session_id=f"copilot-{conv_id}" if conv_id else None,
            msg=messages,
            input_tokens=total_input,
            output_tokens=total_output,
            total_tokens=total_input + total_output,
            source="copilot",
        )

    def _usage_to_logs(self, usage_days: List[Dict], org: str) -> List[LogEntry]:
        """Convert GitHub Copilot usage API response to LogEntries."""
        logs = []
        for day in usage_days:
            date = day.get("day", day.get("date", ""))
            total_suggestions = day.get("total_suggestions_count", 0)
            total_acceptances = day.get("total_acceptances_count", 0)
            total_lines_suggested = day.get("total_lines_suggested", 0)
            total_lines_accepted = day.get("total_lines_accepted", 0)
            total_active_users = day.get("total_active_users", 0)

            acceptance_rate = (
                round(total_acceptances / total_suggestions * 100, 1)
                if total_suggestions > 0
                else 0
            )

            log = LogEntry(
                namespace=self.namespace,
                level="info",
                message=(
                    f"Copilot org usage ({org}): "
                    f"{total_active_users} users, "
                    f"{acceptance_rate}% acceptance"
                ),
                timestamp=date,
                resource_id=f"copilot-org-{org}-{date}",
                custom_object={
                    "source": "copilot",
                    "org": org,
                    "total_suggestions": total_suggestions,
                    "total_acceptances": total_acceptances,
                    "total_lines_suggested": total_lines_suggested,
                    "total_lines_accepted": total_lines_accepted,
                    "total_active_users": total_active_users,
                    "acceptance_rate": acceptance_rate,
                    "breakdown": day.get("breakdown", []),
                },
            )
            logs.append(log)
        return logs

    @staticmethod
    def _get_storage_dir(custom: Optional[str] = None) -> Optional[Path]:
        """Get VS Code workspace storage directory."""
        if custom:
            return Path(custom).expanduser()

        import sys
        platform = sys.platform
        path = _VSCODE_STORAGE_PATHS.get(platform)
        if path and path.is_dir():
            return path
        return None
