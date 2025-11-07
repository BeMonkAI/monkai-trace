"""
LangChain integration for MonkAI Trace

This module provides callback handlers to automatically track LangChain agent
conversations, tool calls, and token usage in MonkAI.

Example:
    >>> from langchain.agents import initialize_agent
    >>> from monkai_trace.integrations.langchain import MonkAICallbackHandler
    >>> 
    >>> handler = MonkAICallbackHandler(
    ...     tracer_token="tk_your_token_here",
    ...     namespace="customer-support",
    ...     auto_upload=True
    ... )
    >>> 
    >>> agent = initialize_agent(tools, llm, callbacks=[handler])
    >>> agent.run("What's the weather?")
"""

import uuid
from typing import Any, Dict, List, Optional, Union
from datetime import datetime

try:
    from langchain.callbacks.base import BaseCallbackHandler
    from langchain.schema import AgentAction, AgentFinish, LLMResult
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False
    # Dummy classes for type hints when langchain not installed
    BaseCallbackHandler = object
    AgentAction = Any
    AgentFinish = Any
    LLMResult = Any

from ..client import MonkAIClient
from ..models import ConversationRecord, Message


class MonkAICallbackHandler(BaseCallbackHandler):
    """
    LangChain callback handler for MonkAI tracing.
    
    Automatically tracks agent conversations, tool calls, and token usage.
    
    Args:
        tracer_token: MonkAI tracer token (starts with 'tk_')
        namespace: Namespace for organizing conversations
        agent_name: Name of the agent (defaults to "langchain-agent")
        auto_upload: Whether to auto-upload records (default: True)
        batch_size: Number of records to batch before auto-upload (default: 10)
        estimate_tokens: Estimate tokens for tool calls (default: True)
    
    Example:
        >>> handler = MonkAICallbackHandler(
        ...     tracer_token="tk_abc123",
        ...     namespace="support",
        ...     agent_name="Customer Support Bot"
        ... )
        >>> agent = initialize_agent(tools, llm, callbacks=[handler])
        >>> agent.run("Help me with my order")
    """
    
    def __init__(
        self,
        tracer_token: str,
        namespace: str,
        agent_name: str = "langchain-agent",
        auto_upload: bool = True,
        batch_size: int = 10,
        estimate_tokens: bool = True
    ):
        """Initialize the MonkAI callback handler."""
        if not LANGCHAIN_AVAILABLE:
            raise ImportError(
                "LangChain is required for this integration. "
                "Install it with: pip install langchain"
            )
        super().__init__()
        
        self.client = MonkAIClient(tracer_token=tracer_token)
        self.namespace = namespace
        self.agent_name = agent_name
        self.auto_upload = auto_upload
        self.batch_size = batch_size
        self.estimate_tokens = estimate_tokens
        
        # Track current session and conversation state
        self.session_id: Optional[str] = None
        self.current_input: Optional[str] = None
        self.conversation_buffer: List[ConversationRecord] = []
        
        # Track tokens accumulated in current interaction
        self.input_tokens = 0
        self.output_tokens = 0
        self.process_tokens = 0  # For tool/chain execution
        
    def _get_or_create_session_id(self) -> str:
        """Get or create a session ID for this conversation."""
        if not self.session_id:
            self.session_id = str(uuid.uuid4())
        return self.session_id
    
    def _estimate_tokens(self, text: str) -> int:
        """Rough estimation: ~4 characters per token."""
        if not self.estimate_tokens:
            return 0
        return max(1, len(text) // 4)
    
    def on_llm_start(
        self,
        serialized: Dict[str, Any],
        prompts: List[str],
        **kwargs: Any
    ) -> None:
        """Called when LLM starts."""
        # Track input tokens from prompts
        for prompt in prompts:
            self.input_tokens += self._estimate_tokens(prompt)
    
    def on_llm_end(
        self,
        response: LLMResult,
        **kwargs: Any
    ) -> None:
        """Called when LLM ends."""
        # Extract actual token usage if available
        if hasattr(response, "llm_output") and response.llm_output:
            token_usage = response.llm_output.get("token_usage", {})
            if token_usage:
                self.input_tokens = token_usage.get("prompt_tokens", self.input_tokens)
                self.output_tokens += token_usage.get("completion_tokens", 0)
        else:
            # Fallback to estimation
            for generations in response.generations:
                for gen in generations:
                    self.output_tokens += self._estimate_tokens(gen.text)
    
    def on_chain_start(
        self,
        serialized: Dict[str, Any],
        inputs: Dict[str, Any],
        **kwargs: Any
    ) -> None:
        """Called when a chain starts."""
        # Track the initial user input
        if "input" in inputs:
            self.current_input = inputs["input"]
        elif "question" in inputs:
            self.current_input = inputs["question"]
    
    def on_chain_end(
        self,
        outputs: Dict[str, Any],
        **kwargs: Any
    ) -> None:
        """Called when a chain ends."""
        # Create conversation record with the final output
        if "output" in outputs or "answer" in outputs:
            output_text = outputs.get("output") or outputs.get("answer", "")
            
            record = ConversationRecord(
                namespace=self.namespace,
                agent=self.agent_name,
                session_id=self._get_or_create_session_id(),
                msg=Message(
                    role="assistant",
                    content=output_text,
                    sender=self.agent_name
                ),
                input_tokens=self.input_tokens,
                output_tokens=self.output_tokens,
                process_tokens=self.process_tokens,
                total_tokens=self.input_tokens + self.output_tokens + self.process_tokens
            )
            
            self._handle_record(record)
            
            # Reset tokens for next interaction
            self.input_tokens = 0
            self.output_tokens = 0
            self.process_tokens = 0
    
    def on_agent_action(
        self,
        action: AgentAction,
        **kwargs: Any
    ) -> None:
        """Called when agent takes an action (tool call)."""
        # Track tool usage as process tokens
        tool_input = str(action.tool_input)
        self.process_tokens += self._estimate_tokens(tool_input)
        
        # Create a record for the tool call
        record = ConversationRecord(
            namespace=self.namespace,
            agent=self.agent_name,
            session_id=self._get_or_create_session_id(),
            msg=Message(
                role="tool",
                content=f"Tool: {action.tool} | Input: {tool_input}",
                sender=action.tool
            ),
            process_tokens=self._estimate_tokens(tool_input),
            total_tokens=self._estimate_tokens(tool_input)
        )
        
        self._handle_record(record)
    
    def on_tool_start(
        self,
        serialized: Dict[str, Any],
        input_str: str,
        **kwargs: Any
    ) -> None:
        """Called when a tool starts."""
        # Track tool input as process tokens
        self.process_tokens += self._estimate_tokens(input_str)
    
    def on_tool_end(
        self,
        output: str,
        **kwargs: Any
    ) -> None:
        """Called when a tool ends."""
        # Track tool output as process tokens
        self.process_tokens += self._estimate_tokens(output)
    
    def on_agent_finish(
        self,
        finish: AgentFinish,
        **kwargs: Any
    ) -> None:
        """Called when agent finishes."""
        # Final output is handled in on_chain_end
        pass
    
    def _handle_record(self, record: ConversationRecord) -> None:
        """Handle a conversation record (buffer or upload)."""
        if self.auto_upload:
            self.conversation_buffer.append(record)
            
            if len(self.conversation_buffer) >= self.batch_size:
                self._flush_batch()
        else:
            self.conversation_buffer.append(record)
    
    def _flush_batch(self) -> None:
        """Upload buffered records to MonkAI."""
        if not self.conversation_buffer:
            return
        
        try:
            result = self.client.upload_records_batch(self.conversation_buffer)
            print(f"✅ Uploaded {result.get('total_inserted', 0)} records to MonkAI")
            self.conversation_buffer.clear()
        except Exception as e:
            print(f"❌ Failed to upload to MonkAI: {e}")
    
    def flush(self) -> None:
        """
        Manually flush any remaining buffered records.
        
        Call this at the end of your application to ensure all records are uploaded.
        """
        self._flush_batch()
    
    def reset_session(self) -> None:
        """
        Reset the session ID to start a new conversation.
        
        Call this between different user conversations.
        """
        self.session_id = None
    
    def __del__(self):
        """Ensure records are flushed on cleanup."""
        self._flush_batch()
