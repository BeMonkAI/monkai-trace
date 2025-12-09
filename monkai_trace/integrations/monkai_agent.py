"""
MonkAI Agent Framework integration for MonkAI Trace

Automatically tracks:
- Agent conversations with full token segmentation
- Multi-agent handoffs and transfers
- Tool calls and executions
- Per-agent usage statistics
- Session continuity across runs
"""

from typing import Any, Optional, Dict, List
from datetime import datetime
import uuid
import logging

try:
    from monkai_agent import Agent, AgentContext
    MONKAI_AGENT_AVAILABLE = True
except ImportError:
    MONKAI_AGENT_AVAILABLE = False
    Agent = Any
    AgentContext = Any

from ..client import MonkAIClient
from ..models import ConversationRecord, Message, Transfer, TokenUsage

logger = logging.getLogger(__name__)


class MonkAIAgentHooks:
    """
    MonkAI Agent Framework integration with automatic tracing.
    
    Args:
        tracer_token: MonkAI tracer token (starts with 'tk_')
        namespace: Namespace for organizing conversations
        auto_upload: Automatically upload after agent completion (default: True)
        estimate_system_tokens: Estimate tokens from agent instructions (default: True)
        batch_size: Number of records to batch before upload (default: 10)
        base_url: Optional custom base URL for MonkAI API
    
    Example:
        >>> hooks = MonkAIAgentHooks(
        ...     tracer_token="tk_your_token",
        ...     namespace="customer-support"
        ... )
        >>> agent = Agent(
        ...     name="Support Bot",
        ...     instructions="You are a helpful assistant",
        ...     hooks=hooks
        ... )
        >>> result = agent.run("Hello, I need help")
    """
    
    def __init__(
        self,
        tracer_token: str,
        namespace: str,
        auto_upload: bool = True,
        estimate_system_tokens: bool = True,
        batch_size: int = 10,
        base_url: Optional[str] = None
    ):
        if not MONKAI_AGENT_AVAILABLE:
            raise ImportError(
                "monkai_agent is not installed. "
                "Install it with: pip install monkai-agent"
            )
        
        self.tracer_token = tracer_token
        self.namespace = namespace
        self.auto_upload = auto_upload
        self.estimate_system_tokens = estimate_system_tokens
        self.batch_size = batch_size
        
        # Initialize MonkAI client
        self.client = MonkAIClient(tracer_token=tracer_token, base_url=base_url)
        
        # State tracking
        self._session_id: Optional[str] = None
        self._current_agent_name: Optional[str] = None
        self._messages: List[Message] = []
        self._transfers: List[Transfer] = []
        self._token_counts: Dict[str, int] = {
            "input": 0,
            "output": 0,
            "process": 0,
            "memory": 0
        }
        self._batch_buffer: List[ConversationRecord] = []
        
        logger.info(f"MonkAIAgentHooks initialized for namespace: {namespace}")
    
    def on_agent_start(self, agent: Agent, context: Optional[AgentContext] = None) -> None:
        """
        Called when agent starts processing.
        
        Args:
            agent: The MonkAI agent instance
            context: Optional agent context
        """
        # Generate or reuse session ID
        if not self._session_id:
            self._session_id = str(uuid.uuid4())
        
        self._current_agent_name = agent.name
        self._messages = []
        self._transfers = []
        self._token_counts = {"input": 0, "output": 0, "process": 0, "memory": 0}
        
        # Estimate system tokens from instructions
        if self.estimate_system_tokens and agent.instructions:
            estimated_tokens = len(agent.instructions.split()) * 1.3  # Rough estimate
            self._token_counts["memory"] = int(estimated_tokens)
        
        logger.debug(f"Agent started: {agent.name} (session: {self._session_id})")
    
    def on_agent_end(
        self,
        agent: Agent,
        context: Optional[AgentContext] = None,
        output: Optional[str] = None
    ) -> None:
        """
        Called when agent completes processing.
        
        Args:
            agent: The MonkAI agent instance
            context: Optional agent context
            output: Final output from the agent
        """
        # Extract usage statistics if available
        if context and hasattr(context, 'usage'):
            usage = context.usage
            self._token_counts["input"] = getattr(usage, 'input_tokens', self._token_counts["input"])
            self._token_counts["output"] = getattr(usage, 'output_tokens', self._token_counts["output"])
            if hasattr(usage, 'process_tokens'):
                self._token_counts["process"] = usage.process_tokens
        
        # Create conversation record
        record = ConversationRecord(
            namespace=self.namespace,
            agent=agent.name,
            session_id=self._session_id,
            msg=self._messages,
            input_tokens=self._token_counts["input"],
            output_tokens=self._token_counts["output"],
            process_tokens=self._token_counts["process"],
            memory_tokens=self._token_counts["memory"],
            transfers=self._transfers if self._transfers else None
        )
        
        # Upload or batch
        if self.auto_upload:
            self._batch_buffer.append(record)
            
            if len(self._batch_buffer) >= self.batch_size:
                self._flush_batch()
        else:
            self._batch_buffer.append(record)
        
        total_tokens = sum(self._token_counts.values())
        logger.info(
            f"Agent ended: {agent.name} | "
            f"Total tokens: {total_tokens} | "
            f"Messages: {len(self._messages)}"
        )
    
    def on_message(self, agent: Agent, message: Dict[str, Any]) -> None:
        """
        Called when a message is processed.
        
        Args:
            agent: The MonkAI agent instance
            message: Message dictionary with role and content
        """
        msg = Message(
            role=message.get("role", "user"),
            content=message.get("content", ""),
            sender=message.get("sender", agent.name),
            timestamp=datetime.utcnow().isoformat()
        )
        
        self._messages.append(msg)
        
        # Update token counts based on role
        if msg.role == "user":
            word_count = len(msg.content.split()) if msg.content else 0
            self._token_counts["input"] += int(word_count * 1.3)
        elif msg.role == "assistant":
            word_count = len(msg.content.split()) if msg.content else 0
            self._token_counts["output"] += int(word_count * 1.3)
        
        logger.debug(f"Message tracked: {msg.role} ({len(msg.content)} chars)")
    
    def on_handoff(
        self,
        from_agent: Agent,
        to_agent: Agent,
        context: Optional[AgentContext] = None,
        reason: Optional[str] = None
    ) -> None:
        """
        Called when agent hands off to another agent.
        
        Args:
            from_agent: Source agent
            to_agent: Destination agent
            context: Optional agent context
            reason: Optional reason for handoff
        """
        timestamp = datetime.utcnow().isoformat()
        
        transfer = Transfer(
            from_agent=from_agent.name,
            to_agent=to_agent.name,
            reason=reason,
            timestamp=timestamp
        )
        
        self._transfers.append(transfer)
        
        # Also create a tool message for the handoff (for frontend visualization)
        msg = Message(
            role="tool",
            content=f"Transferindo conversa para {to_agent.name}",
            sender=from_agent.name,
            tool_name="transfer_to_agent",
            tool_calls=[{
                "name": "transfer_to_agent",
                "arguments": {
                    "from_agent": from_agent.name,
                    "to_agent": to_agent.name,
                    "reason": reason,
                    "timestamp": timestamp
                }
            }],
            timestamp=timestamp
        )
        self._messages.append(msg)
        
        logger.info(f"Handoff: {from_agent.name} → {to_agent.name}")
    
    def on_tool_start(
        self,
        agent: Agent,
        tool_name: str,
        tool_input: Dict[str, Any]
    ) -> None:
        """
        Called when a tool starts executing.
        
        Args:
            agent: The MonkAI agent instance
            tool_name: Name of the tool being called
            tool_input: Input parameters for the tool
        """
        msg = Message(
            role="tool",
            content=f"Executing tool: {tool_name}",
            sender=agent.name,
            tool_calls=[{
                "name": tool_name,
                "arguments": tool_input
            }],
            timestamp=datetime.utcnow().isoformat()
        )
        
        self._messages.append(msg)
        
        # Estimate process tokens for tool execution
        input_size = len(str(tool_input))
        self._token_counts["process"] += int(input_size / 4)
        
        logger.debug(f"Tool started: {tool_name}")
    
    def on_tool_end(
        self,
        agent: Agent,
        tool_name: str,
        tool_output: Any
    ) -> None:
        """
        Called when a tool finishes executing.
        
        Args:
            agent: The MonkAI agent instance
            tool_name: Name of the tool that was called
            tool_output: Output from the tool
        """
        msg = Message(
            role="tool",
            content=f"Tool result: {str(tool_output)[:200]}",
            sender=agent.name,
            timestamp=datetime.utcnow().isoformat()
        )
        
        self._messages.append(msg)
        
        # Estimate process tokens for tool result
        output_size = len(str(tool_output))
        self._token_counts["process"] += int(output_size / 4)
        
        logger.debug(f"Tool ended: {tool_name}")
    
    def _flush_batch(self) -> None:
        """Upload batched records to MonkAI."""
        if not self._batch_buffer:
            return
        
        try:
            self.client.upload_records_batch(self._batch_buffer)
            logger.info(f"Uploaded {len(self._batch_buffer)} records to MonkAI")
            self._batch_buffer = []
        except Exception as e:
            logger.error(f"Failed to upload batch: {e}")
    
    def flush(self) -> None:
        """Manually flush any pending records in the batch buffer."""
        self._flush_batch()
    
    def reset_session(self) -> None:
        """Reset the session ID for a new conversation."""
        self._session_id = None
        logger.debug("Session reset")
