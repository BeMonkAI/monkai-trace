"""OpenAI Agents framework integration for MonkAI"""

from typing import Any, Optional, Dict, List
from datetime import datetime

try:
    from agents import RunHooks, Agent, Tool, RunContextWrapper
    OPENAI_AGENTS_AVAILABLE = True
except ImportError:
    OPENAI_AGENTS_AVAILABLE = False
    # Dummy classes for type hints when agents not installed
    RunHooks = object
    Agent = Any
    Tool = Any
    RunContextWrapper = Any

from ..client import MonkAIClient
from ..models import ConversationRecord, Message, Transfer, TokenUsage


class MonkAIRunHooks(RunHooks):
    """
    OpenAI Agents RunHooks integration for MonkAI.
    
    Automatically tracks:
    - Agent conversations with full token segmentation
    - Multi-agent handoffs
    - Tool calls
    - Per-agent usage statistics
    
    Usage:
        hooks = MonkAIRunHooks(
            tracer_token="tk_your_token",
            namespace="customer-support"
        )
        result = await Runner.run(agent, "Hello", hooks=hooks)
    """
    
    def __init__(
        self,
        tracer_token: str,
        namespace: str,
        auto_upload: bool = True,
        estimate_system_tokens: bool = True,
        batch_size: int = 1
    ):
        """
        Initialize MonkAI tracking hooks.
        
        Args:
            tracer_token: Your MonkAI tracer token
            namespace: Namespace for all tracked conversations
            auto_upload: Automatically upload after agent_end (default: True)
            estimate_system_tokens: Estimate process_tokens from instructions (default: True)
            batch_size: Number of records to batch before upload
        """
        if not OPENAI_AGENTS_AVAILABLE:
            raise ImportError(
                "openai-agents-python is required for this integration. "
                "Install it with: pip install openai-agents-python"
            )
        
        self.client = MonkAIClient(tracer_token=tracer_token)
        self.namespace = namespace
        self.auto_upload = auto_upload
        self.estimate_system_tokens = estimate_system_tokens
        self.batch_size = batch_size
        
        # Track conversation state
        self._current_session: Optional[str] = None
        self._messages: List[Message] = []
        self._transfers: List[Transfer] = []
        self._system_prompt_tokens: int = 0
        self._context_tokens: int = 0
        self._batch_buffer: List[ConversationRecord] = []
        self._user_input: Optional[str] = None
    
    async def on_agent_start(
        self,
        context: RunContextWrapper,
        agent: Agent
    ) -> None:
        """Called when agent starts processing"""
        print(f"[MonkAI] Agent '{agent.name}' started")
        
        # Capture user input from context
        if hasattr(context, 'input'):
            self._user_input = str(context.input)
        elif hasattr(context, 'messages') and context.messages:
            # Find user message in context
            for msg in context.messages:
                if hasattr(msg, 'role') and getattr(msg, 'role', None) == 'user':
                    self._user_input = getattr(msg, 'content', None) or str(msg)
                    break
        
        # Estimate system prompt tokens if enabled
        if self.estimate_system_tokens and hasattr(agent, 'instructions') and agent.instructions:
            # Rough estimate: ~4 chars per token
            self._system_prompt_tokens = len(agent.instructions) // 4
        
        # Generate session ID if not exists
        if not self._current_session:
            self._current_session = f"session-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    
    async def on_agent_end(
        self,
        context: RunContextWrapper,
        agent: Agent,
        output: Any
    ) -> None:
        """Called when agent completes - upload conversation to MonkAI"""
        print(f"[MonkAI] Agent '{agent.name}' ended")
        
        # Extract usage statistics
        usage = getattr(context, 'usage', None)
        if usage is None:
            # Try to get usage from result if available
            usage = getattr(output, 'usage', None)
        
        token_usage = TokenUsage.from_openai_agents_usage(
            usage if usage is not None else type('Usage', (), {'input_tokens': 0, 'output_tokens': 0, 'requests': None})(),
            system_prompt_tokens=self._system_prompt_tokens,
            context_tokens=self._context_tokens
        )
        
        # Build messages list - ensure we have user and assistant messages
        messages = self._messages.copy() if self._messages else []
        
        # Ensure we have user message
        has_user_message = any(msg.role == 'user' if isinstance(msg, Message) else msg.get('role') == 'user' if isinstance(msg, dict) else False for msg in messages)
        
        # Add user message if not present
        if not has_user_message and self._user_input:
            messages.insert(0, Message(role="user", content=self._user_input))
        
        # Ensure we have assistant message
        has_assistant_message = any(msg.role == 'assistant' if isinstance(msg, Message) else msg.get('role') == 'assistant' if isinstance(msg, dict) else False for msg in messages)
        
        if not has_assistant_message:
            messages.append(Message(role="assistant", content=str(output), sender=agent.name))
        
        # Create conversation record
        record = ConversationRecord(
            namespace=self.namespace,
            agent=agent.name,
            session_id=self._current_session,
            msg=messages,
            input_tokens=token_usage.input_tokens,
            output_tokens=token_usage.output_tokens,
            process_tokens=token_usage.process_tokens,
            memory_tokens=token_usage.memory_tokens,
            total_tokens=token_usage.total_tokens,
            transfers=self._transfers.copy() if self._transfers else None
            # Removed inserted_at as it may cause API issues
        )
        
        # Upload or batch
        if self.auto_upload:
            self._batch_buffer.append(record)
            if len(self._batch_buffer) >= self.batch_size:
                await self._flush_batch()
            else:
                # If batch not full, upload immediately if auto_upload is True and batch_size is 1
                if self.batch_size == 1:
                    await self._flush_batch()
        
        # Reset state for next conversation
        self._messages.clear()
        self._transfers.clear()
        self._system_prompt_tokens = 0
        self._context_tokens = 0
        self._user_input = None
        
        print(f"[MonkAI] Tracked {token_usage.total_tokens} tokens for '{agent.name}'")
    
    async def on_handoff(
        self,
        context: RunContextWrapper,
        from_agent: Agent,
        to_agent: Agent
    ) -> None:
        """Called when agent hands off to another agent"""
        print(f"[MonkAI] Handoff: {from_agent.name} → {to_agent.name}")
        
        # Track the transfer
        transfer = Transfer(
            from_agent=from_agent.name,
            to_agent=to_agent.name,
            timestamp=datetime.utcnow().isoformat()
        )
        self._transfers.append(transfer)
    
    async def on_tool_start(
        self,
        context: RunContextWrapper,
        agent: Agent,
        tool: Tool
    ) -> None:
        """Called when tool execution starts"""
        print(f"[MonkAI] Tool '{tool.name}' started by {agent.name}")
        
        # Track as a message
        self._messages.append(Message(
            role="tool",
            content=f"Calling tool: {tool.name}",
            sender=agent.name,
            tool_name=tool.name
        ))
    
    async def on_tool_end(
        self,
        context: RunContextWrapper,
        agent: Agent,
        tool: Tool,
        result: str
    ) -> None:
        """Called when tool execution completes"""
        print(f"[MonkAI] Tool '{tool.name}' completed")
        
        # Track tool result
        self._messages.append(Message(
            role="tool",
            content=result,
            sender=agent.name,
            tool_name=tool.name
        ))
    
    async def on_llm_start(
        self,
        context: RunContextWrapper,
        agent: Agent,
        instructions: str,
        input_data: Any
    ) -> None:
        """Called when LLM is about to be called - capture user message"""
        # The input_data parameter contains the user's message!
        if input_data and not self._user_input:
            # Convert input_data to string if needed
            if isinstance(input_data, str):
                self._user_input = input_data
            elif isinstance(input_data, list):
                # If it's a list, find user messages
                for item in input_data:
                    if isinstance(item, dict) and item.get('role') == 'user':
                        self._user_input = item.get('content', str(item))
                        break
                    elif hasattr(item, 'role') and getattr(item, 'role') == 'user':
                        self._user_input = getattr(item, 'content', str(item))
                        break
            else:
                self._user_input = str(input_data)
            
            # Add to messages list if not already there
            if self._user_input:
                has_user = any(m.role == 'user' if isinstance(m, Message) else m.get('role') == 'user' if isinstance(m, dict) else False for m in self._messages)
                if not has_user:
                    self._messages.append(Message(role="user", content=self._user_input))
    
    async def _flush_batch(self):
        """Upload batched records"""
        if not self._batch_buffer:
            print("[MonkAI] No records to upload")
            return
        
        try:
            result = self.client.upload_records_batch(self._batch_buffer)
            inserted = result.get('total_inserted', 0)
            if inserted > 0:
                print(f"[MonkAI] ✅ Uploaded {inserted} record(s) successfully")
            else:
                # Only log failures, not every response
                if result.get('failures'):
                    print(f"[MonkAI] ⚠️  Upload failed: {result.get('failures')[0].get('error', 'Unknown error')}")
            self._batch_buffer.clear()
        except Exception as e:
            print(f"[MonkAI] ❌ Upload failed: {e}")
            import traceback
            traceback.print_exc()
    
    def __del__(self):
        """Flush remaining batch on cleanup"""
        if self._batch_buffer:
            import asyncio
            try:
                asyncio.create_task(self._flush_batch())
            except:
                pass
