"""OpenAI Agents framework integration for MonkAI"""

from typing import Any, Optional, Dict, List
from datetime import datetime

try:
    from agents import RunHooks, Agent, Tool
    from agents.run_context import RunContextWrapper
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
from ..session_manager import SessionManager
from functools import wraps


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
        batch_size: int = 10,
        session_manager: Optional[SessionManager] = None,
        inactivity_timeout: int = 120
    ):
        """
        Initialize MonkAI tracking hooks.
        
        Args:
            tracer_token: Your MonkAI tracer token
            namespace: Namespace for all tracked conversations
            auto_upload: Automatically upload after agent_end (default: True)
            estimate_system_tokens: Estimate process_tokens from instructions (default: True)
            batch_size: Number of records to batch before upload
            session_manager: Custom SessionManager instance (optional)
            inactivity_timeout: Seconds of inactivity before new session (default: 120)
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
        
        # Session management
        self.session_manager = session_manager or SessionManager(inactivity_timeout)
        self._current_user_id: Optional[str] = None
        
        # Track conversation state
        self._current_session: Optional[str] = None
        self._messages: List[Message] = []
        self._transfers: List[Transfer] = []
        self._system_prompt_tokens: int = 0
        self._context_tokens: int = 0
        self._batch_buffer: List[ConversationRecord] = []
        self._pending_user_input: Optional[str] = None  # Store user input before agent starts
        self._user_input: Optional[str] = None  # Store user input captured from hooks (on_llm_start, etc.)
    
    async def on_agent_start(
        self,
        context: RunContextWrapper,
        agent: Agent
    ) -> None:
        """Called when agent starts processing"""
        print(f"[MonkAI] Agent '{agent.name}' started")
        
        # Estimate system prompt tokens if enabled
        if self.estimate_system_tokens and hasattr(agent, 'instructions') and agent.instructions:
            # Rough estimate: ~4 chars per token
            self._system_prompt_tokens = len(agent.instructions) // 4
        
        # Determinar user_id (priority: context > attribute > default)
        user_id = None
        if hasattr(context, 'user_id') and context.user_id:
            user_id = context.user_id
        elif self._current_user_id:
            user_id = self._current_user_id
        else:
            user_id = "anonymous"  # Fallback
        
        # Get or create session with timeout logic
        self._current_session = self.session_manager.get_or_create_session(
            user_id=user_id,
            namespace=self.namespace
        )
        
        print(f"[MonkAI] Session: {self._current_session} (user: {user_id})")
        
        # Extract user message - most efficient approach
        user_message_content = None
        
        # Priority 1: Use stored pending input (set via set_user_input method)
        if self._pending_user_input:
            user_message_content = self._pending_user_input
            self._pending_user_input = None  # Clear after use
        
        # Priority 2: Check context.input (if available)
        elif hasattr(context, 'input') and context.input:
            user_message_content = str(context.input)
        
        # Priority 3: Check context.messages list (if available)
        elif hasattr(context, 'messages') and context.messages:
            # Look for the first user message
            for msg in context.messages:
                if hasattr(msg, 'role') and msg.role == 'user':
                    user_message_content = msg.content if hasattr(msg, 'content') else str(msg)
                    break
                elif isinstance(msg, dict) and msg.get('role') == 'user':
                    user_message_content = msg.get('content', str(msg))
                    break
        
        # Priority 4: Check context.context (nested context)
        elif hasattr(context, 'context') and context.context:
            nested = context.context
            if hasattr(nested, 'input') and nested.input:
                user_message_content = str(nested.input)
            elif hasattr(nested, 'messages') and nested.messages:
                for msg in nested.messages:
                    if hasattr(msg, 'role') and msg.role == 'user':
                        user_message_content = msg.content if hasattr(msg, 'content') else str(msg)
                        break
        
        # Add user message if found
        if user_message_content:
            self._user_input = user_message_content  # Store for later use in on_agent_end
            self._messages.append(Message(
                role="user",
                content=user_message_content,
                sender="user"
            ))
            print(f"[MonkAI] Captured user message: {user_message_content[:50]}...")
        else:
            print("[MonkAI] ⚠️ WARNING: No user message captured. Consider using hooks.set_user_input() or MonkAIRunHooks.run_with_tracking()")
    
    def set_user_input(self, user_input: str) -> None:
        """
        Set the user input before running the agent.
        This is the most reliable way to capture the initial user message.
        
        Usage:
            hooks = MonkAIRunHooks(...)
            hooks.set_user_input("Hello, how can you help?")
            result = await Runner.run(agent, "Hello, how can you help?", hooks=hooks)
        """
        self._pending_user_input = user_input
    
    def set_user_id(self, user_id: str) -> None:
        """
        Define user_id para gerenciamento de sessão.
        Deve ser chamado ANTES de agent_start.
        
        Usage:
            hooks = MonkAIRunHooks(...)
            hooks.set_user_id("user-12345")
            result = await Runner.run(agent, "Hello", hooks=hooks)
        """
        self._current_user_id = user_id
    
    async def on_agent_end(
        self,
        context: RunContextWrapper,
        agent: Agent,
        output: Any
    ) -> None:
        """Called when agent completes - upload conversation to MonkAI"""
        print(f"[MonkAI] Agent '{agent.name}' ended")
        
        # Capture internal tools from response raw_items (web_search, file_search, etc.)
        self._capture_internal_tools(output, context, agent.name)
        
        # Extract usage statistics
        usage = getattr(context, 'usage', None)
        if usage is None:
            print(f"[MonkAI] Warning: context.usage is None for '{agent.name}'")
            # Create token usage with defaults
            token_usage = TokenUsage(
                input_tokens=0,
                output_tokens=0,
                process_tokens=self._system_prompt_tokens,
                memory_tokens=self._context_tokens
            )
        else:
            token_usage = TokenUsage.from_openai_agents_usage(
                usage,
                system_prompt_tokens=self._system_prompt_tokens,
                context_tokens=self._context_tokens
            )
        
        # Build messages list - ensure we have user and assistant messages
        messages = self._messages.copy() if self._messages else []
        
        # Ensure we have user message (guarantee from on_agent_end)
        has_user_message = any(
            msg.role == 'user' if isinstance(msg, Message) else 
            msg.get('role') == 'user' if isinstance(msg, dict) else False 
            for msg in messages
        )
        
        # Add user message if not present but we have _user_input
        if not has_user_message and self._user_input:
            messages.insert(0, Message(role="user", content=self._user_input, sender="user"))
            print(f"[MonkAI] Added user message from backup: {self._user_input[:50]}...")
        
        # Ensure we have assistant message
        has_assistant_message = any(
            msg.role == 'assistant' if isinstance(msg, Message) else 
            msg.get('role') == 'assistant' if isinstance(msg, dict) else False 
            for msg in messages
        )
        
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
            transfers=self._transfers.copy() if self._transfers else None,
            inserted_at=datetime.utcnow().isoformat()
        )
        
        # Upload or batch
        if self.auto_upload:
            self._batch_buffer.append(record)
            if len(self._batch_buffer) >= self.batch_size:
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
        
        timestamp = datetime.utcnow().isoformat()
        
        # Track the transfer
        transfer = Transfer(
            from_agent=from_agent.name,
            to_agent=to_agent.name,
            timestamp=timestamp
        )
        self._transfers.append(transfer)
        
        # Also create a tool message for the handoff (for frontend visualization)
        self._messages.append(Message(
            role="tool",
            content=f"Transferindo conversa para {to_agent.name}",
            sender=from_agent.name,
            tool_name="transfer_to_agent",
            tool_calls=[{
                "name": "transfer_to_agent",
                "arguments": {
                    "from_agent": from_agent.name,
                    "to_agent": to_agent.name,
                    "timestamp": timestamp
                }
            }]
        ))
    
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
        """
        Called when LLM is about to be called - capture user message.
        This hook provides direct access to input_data which contains the user message.
        """
        # The input_data parameter contains the user's message directly!
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
                has_user = any(
                    m.role == 'user' if isinstance(m, Message) else 
                    m.get('role') == 'user' if isinstance(m, dict) else False 
                    for m in self._messages
                )
                if not has_user:
                    self._messages.append(Message(role="user", content=self._user_input, sender="user"))
                    print(f"[MonkAI] Captured user message from on_llm_start: {self._user_input[:50]}...")
    
    def _capture_internal_tools(self, output: Any, context: RunContextWrapper, agent_name: str) -> None:
        """
        Capture OpenAI internal tools from response raw_items.
        These tools (web_search, file_search, code_interpreter) don't trigger on_tool_start/end hooks.
        
        Handles multiple structures:
        1. Direct internal tool items: item.type == 'web_search_call'
        2. Wrapped in ToolCallItem: item.type == 'tool_call_item' with item.raw_item.type == 'web_search_call'
        3. web_searches array on output object
        4. new_items array on output (RunResult)
        5. Nested in output.output for streaming results
        """
        # DEBUG: Detailed logging to investigate structure
        print(f"\n[MonkAI DEBUG] ========== _capture_internal_tools START ==========")
        print(f"[MonkAI DEBUG] agent_name: {agent_name}")
        print(f"[MonkAI DEBUG] output type: {type(output)}")
        print(f"[MonkAI DEBUG] output class name: {output.__class__.__name__ if output else 'None'}")
        
        # Log all attributes of output
        if output:
            output_attrs = [attr for attr in dir(output) if not attr.startswith('_')]
            print(f"[MonkAI DEBUG] output public attrs: {output_attrs}")
            
            # Log specific interesting attributes
            for attr in ['raw_items', 'new_items', 'items', 'output', 'final_output', 'messages', 'raw_response', 'data']:
                if hasattr(output, attr):
                    val = getattr(output, attr, None)
                    val_type = type(val).__name__ if val is not None else 'None'
                    val_len = len(val) if hasattr(val, '__len__') and not isinstance(val, str) else 'N/A'
                    print(f"[MonkAI DEBUG] output.{attr}: type={val_type}, len={val_len}")
                    # If it's a list, log first few items
                    if isinstance(val, (list, tuple)) and len(val) > 0:
                        for i, item in enumerate(val[:5]):
                            item_type = getattr(item, 'type', 'no_type_attr')
                            item_class = item.__class__.__name__
                            print(f"[MonkAI DEBUG]   output.{attr}[{i}]: class={item_class}, type={item_type}")
                            # Check for raw_item nested structure
                            if hasattr(item, 'raw_item'):
                                raw_item = item.raw_item
                                raw_type = self._get_attr(raw_item, 'type')
                                raw_class = raw_item.__class__.__name__ if raw_item else 'None'
                                print(f"[MonkAI DEBUG]     raw_item: class={raw_class}, type={raw_type}")
        
        # Log context attributes
        if context:
            print(f"[MonkAI DEBUG] context type: {type(context)}")
            context_attrs = [attr for attr in dir(context) if not attr.startswith('_')]
            print(f"[MonkAI DEBUG] context public attrs (first 20): {context_attrs[:20]}")
            
            if hasattr(context, 'response'):
                resp = context.response
                if resp:
                    print(f"[MonkAI DEBUG] context.response type: {type(resp)}")
                    if hasattr(resp, 'raw_items'):
                        print(f"[MonkAI DEBUG] context.response.raw_items exists, len={len(resp.raw_items) if resp.raw_items else 0}")
        
        print(f"[MonkAI DEBUG] ========== END DEBUG INFO ==========\n")
        
        # Map of internal tool types
        internal_tool_types = {
            'web_search_call': 'web_search',
            'file_search_call': 'file_search',
            'code_interpreter_call': 'code_interpreter',
            'computer_call': 'computer_use',
        }
        
        raw_items = None
        source = None
        
        # Try to get raw_items from various locations
        # Location 1: output.raw_items
        if hasattr(output, 'raw_items') and output.raw_items:
            raw_items = output.raw_items
            source = 'output.raw_items'
        # Location 2: output.new_items (RunResult structure)
        elif hasattr(output, 'new_items') and output.new_items:
            raw_items = output.new_items
            source = 'output.new_items'
        # Location 3: output.items
        elif hasattr(output, 'items') and output.items:
            raw_items = output.items
            source = 'output.items'
        # Location 4: context.response.raw_items
        elif hasattr(context, 'response') and context.response and hasattr(context.response, 'raw_items') and context.response.raw_items:
            raw_items = context.response.raw_items
            source = 'context.response.raw_items'
        # Location 5: output.output (nested for streaming)
        elif hasattr(output, 'output') and output.output:
            nested = output.output
            if hasattr(nested, 'raw_items') and nested.raw_items:
                raw_items = nested.raw_items
                source = 'output.output.raw_items'
            elif hasattr(nested, 'new_items') and nested.new_items:
                raw_items = nested.new_items
                source = 'output.output.new_items'
        # Location 6: output as iterable (last resort)
        elif hasattr(output, '__iter__') and not isinstance(output, str):
            try:
                raw_items = list(output)
                source = 'output (iterable)'
            except:
                pass
        
        if raw_items:
            print(f"[MonkAI DEBUG] Found raw_items from {source}, count={len(raw_items)}")
        else:
            print(f"[MonkAI DEBUG] No raw_items found in any location")
        
        captured_count = 0
        
        # Process raw_items if found
        if raw_items:
            for idx, item in enumerate(raw_items):
                item_type = getattr(item, 'type', None)
                item_class = item.__class__.__name__
                print(f"[MonkAI DEBUG] Processing item[{idx}]: class={item_class}, type={item_type}")
                
                # Case 1: Direct internal tool type (item.type == 'web_search_call')
                if item_type in internal_tool_types:
                    tool_name = internal_tool_types[item_type]
                    tool_details = self._parse_internal_tool_details(item, item_type)
                    self._add_internal_tool_message(agent_name, item, item_type, tool_name, tool_details)
                    captured_count += 1
                    print(f"[MonkAI DEBUG] Captured direct internal tool: {tool_name}")
                
                # Case 2: Wrapped in tool_call_item (item.type == 'tool_call_item')
                elif item_type == 'tool_call_item':
                    raw_item = getattr(item, 'raw_item', None)
                    if raw_item:
                        # Get the actual type from raw_item (can be object or dict)
                        actual_type = self._get_attr(raw_item, 'type')
                        print(f"[MonkAI DEBUG] tool_call_item raw_item.type={actual_type}")
                        
                        if actual_type in internal_tool_types:
                            tool_name = internal_tool_types[actual_type]
                            tool_details = self._parse_internal_tool_details(raw_item, actual_type)
                            self._add_internal_tool_message(agent_name, raw_item, actual_type, tool_name, tool_details)
                            captured_count += 1
                            print(f"[MonkAI DEBUG] Captured wrapped internal tool: {tool_name}")
                
                # Case 3: Check if item itself has nested structure we haven't checked
                else:
                    # Check for any nested items that might contain internal tools
                    for nested_attr in ['raw_item', 'item', 'data', 'content']:
                        if hasattr(item, nested_attr):
                            nested = getattr(item, nested_attr)
                            if nested:
                                nested_type = self._get_attr(nested, 'type')
                                if nested_type in internal_tool_types:
                                    tool_name = internal_tool_types[nested_type]
                                    tool_details = self._parse_internal_tool_details(nested, nested_type)
                                    self._add_internal_tool_message(agent_name, nested, nested_type, tool_name, tool_details)
                                    captured_count += 1
                                    print(f"[MonkAI DEBUG] Captured nested ({nested_attr}) internal tool: {tool_name}")
        
        # Case 4: Check for web_searches array directly on output (fallback)
        if hasattr(output, 'web_searches') and output.web_searches:
            print(f"[MonkAI DEBUG] Found output.web_searches, count={len(output.web_searches)}")
            for ws in output.web_searches:
                ws_type = self._get_attr(ws, 'type')
                if ws_type == 'web_search_call':
                    tool_details = self._parse_internal_tool_details(ws, 'web_search_call')
                    self._add_internal_tool_message(agent_name, ws, 'web_search_call', 'web_search', tool_details)
                    captured_count += 1
                    print(f"[MonkAI DEBUG] Captured web_search from web_searches array")
        
        # Case 5: Check output.data for RunResult with nested data
        if hasattr(output, 'data') and output.data:
            data = output.data
            if hasattr(data, 'raw_items') and data.raw_items:
                print(f"[MonkAI DEBUG] Found output.data.raw_items, processing...")
                for item in data.raw_items:
                    item_type = getattr(item, 'type', None)
                    if item_type in internal_tool_types:
                        tool_name = internal_tool_types[item_type]
                        tool_details = self._parse_internal_tool_details(item, item_type)
                        self._add_internal_tool_message(agent_name, item, item_type, tool_name, tool_details)
                        captured_count += 1
                        print(f"[MonkAI DEBUG] Captured from output.data.raw_items: {tool_name}")
        
        if captured_count > 0:
            print(f"[MonkAI] Captured {captured_count} internal tool(s)")
        else:
            print(f"[MonkAI DEBUG] No internal tools captured - may need to check different structure")
    
    def _get_attr(self, obj: Any, attr: str, default: Any = None) -> Any:
        """Get attribute from object or dict safely"""
        if obj is None:
            return default
        if isinstance(obj, dict):
            return obj.get(attr, default)
        return getattr(obj, attr, default)
    
    def _add_internal_tool_message(self, agent_name: str, item: Any, item_type: str, tool_name: str, tool_details: Dict) -> None:
        """Add an internal tool message to the messages list"""
        self._messages.append(Message(
            role="tool",
            content=f"Internal tool: {tool_name}",
            sender=agent_name,
            tool_name=tool_name,
            is_internal_tool=True,
            internal_tool_type=item_type,
            tool_calls=[{
                "name": tool_name,
                "type": item_type,
                "id": self._get_attr(item, 'id'),
                "status": self._get_attr(item, 'status'),
                "arguments": tool_details.get('arguments'),
                "result": tool_details.get('result'),
            }]
        ))
    
    def _parse_internal_tool_details(self, item: Any, item_type: str) -> Dict:
        """Parse specific details for each internal tool type. Supports both objects and dicts."""
        
        if item_type == 'web_search_call':
            action = self._get_attr(item, 'action')
            result = self._get_attr(item, 'result')
            
            # Primary: sources are in action.sources (when include param is used)
            sources = self._get_attr(action, 'sources') if action else None
            
            # Fallback: if sources is None, try result as fallback
            if sources is None and result:
                sources = (
                    self._get_attr(result, 'sources') or 
                    self._get_attr(result, 'results') or
                    self._get_attr(result, 'web_results')
                )
                if sources is None and isinstance(result, list):
                    sources = result
            
            return {
                "arguments": {
                    "query": self._get_attr(action, 'query') if action else None,
                    "sources": sources,
                },
                "result": result
            }
        
        elif item_type == 'file_search_call':
            return {
                "arguments": {
                    "query": self._get_attr(item, 'query'),
                    "file_ids": self._get_attr(item, 'file_ids'),
                },
                "result": self._get_attr(item, 'results')
            }
        
        elif item_type == 'code_interpreter_call':
            return {
                "arguments": {
                    "code": self._get_attr(item, 'code'),
                    "language": self._get_attr(item, 'language', 'python'),
                },
                "result": self._get_attr(item, 'output')
            }
        
        elif item_type == 'computer_call':
            action = self._get_attr(item, 'action')
            return {
                "arguments": {
                    "action_type": self._get_attr(action, 'type') if action else None,
                },
                "result": self._get_attr(item, 'output')
            }
        
        return {"arguments": None, "result": None}
    
    async def _flush_batch(self):
        """Upload batched records"""
        if not self._batch_buffer:
            return
        
        try:
            result = self.client.upload_records_batch(self._batch_buffer)
            print(f"[MonkAI] Uploaded {result['total_inserted']} records")
            self._batch_buffer.clear()
        except Exception as e:
            print(f"[MonkAI] Upload failed: {e}")
    
    def __del__(self):
        """Flush remaining batch on cleanup"""
        if self._batch_buffer:
            import asyncio
            try:
                asyncio.create_task(self._flush_batch())
            except:
                pass
    
    def _capture_internal_tools_from_result(self, result: Any, agent_name: str) -> None:
        """
        Capture internal tools from the complete RunResult object.
        Called AFTER Runner.run() returns, when we have access to new_items and raw_responses.
        
        This is the CORRECT place to capture internal tools because:
        - on_agent_end only receives final_output (a string), not the full RunResult
        - RunResult.new_items contains all ToolCallItem objects with web_search_call, etc.
        """
        
        internal_tool_types = {
            'web_search_call': 'web_search',
            'file_search_call': 'file_search',
            'code_interpreter_call': 'code_interpreter',
            'computer_call': 'computer_use',
        }
        
        captured_count = 0
        
        # Check for new_items (primary source)
        new_items = getattr(result, 'new_items', None)
        if new_items:
            captured_count += self._process_items_for_internal_tools(new_items, agent_name, 'result.new_items', internal_tool_types)
        
        # Also check raw_responses as backup
        raw_responses = getattr(result, 'raw_responses', None)
        if raw_responses:
            for i, resp in enumerate(raw_responses):
                resp_output = getattr(resp, 'output', None)
                if resp_output and isinstance(resp_output, list):
                    captured_count += self._process_items_for_internal_tools(resp_output, agent_name, f'result.raw_responses[{i}].output', internal_tool_types)
        
        if captured_count > 0:
            # Add internal tools to the LAST buffered record (the one from on_agent_end)
            if self._batch_buffer:
                last_record = self._batch_buffer[-1]
                internal_tool_messages = [m for m in self._messages if getattr(m, 'is_internal_tool', False)]
                if internal_tool_messages:
                    existing_msgs = last_record.msg if isinstance(last_record.msg, list) else []
                    last_record.msg = existing_msgs + internal_tool_messages
    
    def _process_items_for_internal_tools(self, items: list, agent_name: str, source: str, internal_tool_types: dict) -> int:
        """Process a list of items to extract internal tools. Returns count of captured tools."""
        captured_count = 0
        
        for item in items:
            item_type = self._get_attr(item, 'type')
            
            # Case 1: Direct internal tool (item.type == 'web_search_call')
            if item_type in internal_tool_types:
                tool_name = internal_tool_types[item_type]
                tool_details = self._parse_internal_tool_details(item, item_type)
                self._add_internal_tool_message(agent_name, item, item_type, tool_name, tool_details)
                captured_count += 1
                continue
            
            # Case 2: Wrapped in ToolCallItem (item.type == 'tool_call_item')
            if item_type == 'tool_call_item':
                raw_item = self._get_attr(item, 'raw_item')
                if raw_item:
                    actual_type = self._get_attr(raw_item, 'type')
                    if actual_type in internal_tool_types:
                        tool_name = internal_tool_types[actual_type]
                        tool_details = self._parse_internal_tool_details(raw_item, actual_type)
                        self._add_internal_tool_message(agent_name, raw_item, actual_type, tool_name, tool_details)
                        captured_count += 1
        
        return captured_count
    
    @staticmethod
    async def run_with_tracking(agent: Agent, user_input: str, hooks: 'MonkAIRunHooks', **kwargs):
        """
        Convenience wrapper for Runner.run() that automatically captures user input
        and internal tools from the complete RunResult.
        
        This is the recommended way to use MonkAIRunHooks.
        
        BREAKING CHANGE in v0.2.4: This method is now async and must be awaited.
        
        v0.2.7: Fixed include params - now passed via RunConfig.model_settings.response_include
        instead of as a direct kwarg (which was being ignored by Runner.run).
        
        Usage:
            hooks = MonkAIRunHooks(...)
            result = await MonkAIRunHooks.run_with_tracking(agent, "Hello", hooks)
        """
        # Set user input before running
        hooks.set_user_input(user_input)
        
        # Import Runner and RunConfig here to avoid circular dependency
        from agents import Runner
        
        # Get or create RunConfig with model_settings that include response_include
        run_config = kwargs.pop('run_config', None)
        
        # Required includes for capturing internal tool sources
        required_includes = [
            "web_search_call.action.sources",
            "file_search_call.results",
        ]
        
        try:
            # Try to use RunConfig with ModelSettings (agents SDK >= 0.1.0)
            from agents import RunConfig
            from agents.model_settings import ModelSettings
            
            if run_config is None:
                # Create new RunConfig with response_include
                run_config = RunConfig(
                    model_settings=ModelSettings(
                        response_include=required_includes
                    )
                )
            else:
                # Merge with existing RunConfig
                existing_settings = run_config.model_settings
                if existing_settings is None:
                    run_config.model_settings = ModelSettings(
                        response_include=required_includes
                    )
                else:
                    # Merge response_include lists
                    existing_includes = existing_settings.response_include or []
                    merged_includes = list(existing_includes)
                    for inc in required_includes:
                        if inc not in merged_includes:
                            merged_includes.append(inc)
                    existing_settings.response_include = merged_includes
            
            # Run with the updated RunConfig
            result = await Runner.run(agent, user_input, hooks=hooks, run_config=run_config, **kwargs)
            
        except ImportError:
            # Fallback for older agents SDK versions without RunConfig/ModelSettings
            print("[MonkAI] Warning: agents SDK doesn't support RunConfig/ModelSettings, sources may be null")
            result = await Runner.run(agent, user_input, hooks=hooks, **kwargs)
        
        # Capture internal tools from the COMPLETE RunResult (has new_items, raw_responses)
        hooks._capture_internal_tools_from_result(result, agent.name)
        
        # Force flush any remaining buffered records that now include the internal tools
        if hooks._batch_buffer:
            await hooks._flush_batch()
        
        return result
