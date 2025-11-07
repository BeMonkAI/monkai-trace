"""Pydantic models for MonkAI data structures"""

from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Dict, Any, Union
from datetime import datetime


class Message(BaseModel):
    """Single message in a conversation"""
    role: str = Field(..., description="Role: user, assistant, tool, system")
    content: Optional[Union[str, Dict]] = Field(None, description="Message content")
    sender: Optional[str] = Field(None, description="Agent/user that sent this")
    tool_calls: Optional[List[Dict]] = None
    tool_call_id: Optional[str] = None
    tool_name: Optional[str] = None
    refusal: Optional[str] = None
    annotations: Optional[List[Any]] = None
    audio: Optional[Any] = None
    function_call: Optional[Dict] = None


class Transfer(BaseModel):
    """Agent transfer information"""
    from_agent: str = Field(..., alias="from")
    to_agent: str = Field(..., alias="to")
    reason: Optional[str] = None
    timestamp: Optional[str] = None

    class Config:
        populate_by_name = True


class TokenUsage(BaseModel):
    """
    Token usage breakdown with automatic calculation.
    Supports all 4 token types used by MonkAI.
    """
    input_tokens: int = Field(0, description="User input tokens")
    output_tokens: int = Field(0, description="Agent output tokens")
    process_tokens: int = Field(0, description="System/processing tokens")
    memory_tokens: int = Field(0, description="Context/memory tokens")
    total_tokens: Optional[int] = Field(None, description="Auto-calculated if not provided")
    
    # OpenAI Agents specific fields (for compatibility)
    requests: Optional[int] = Field(None, description="Number of API requests made")
    
    @field_validator('total_tokens', mode='after')
    @classmethod
    def calculate_total(cls, v, info):
        """Auto-calculate total_tokens if not provided"""
        if v is None:
            return (
                info.data.get('input_tokens', 0) +
                info.data.get('output_tokens', 0) +
                info.data.get('process_tokens', 0) +
                info.data.get('memory_tokens', 0)
            )
        return v
    
    @classmethod
    def from_openai_agents_usage(
        cls,
        usage: Any,
        system_prompt_tokens: int = 0,
        context_tokens: int = 0
    ) -> "TokenUsage":
        """
        Create TokenUsage from OpenAI Agents Usage object.
        
        Args:
            usage: agents.Usage object from RunContextWrapper
            system_prompt_tokens: Estimated tokens in system prompts/instructions
            context_tokens: Estimated tokens in conversation history
        """
        return cls(
            input_tokens=getattr(usage, 'input_tokens', 0),
            output_tokens=getattr(usage, 'output_tokens', 0),
            process_tokens=system_prompt_tokens,
            memory_tokens=context_tokens,
            requests=getattr(usage, 'requests', None)
        )


class ConversationRecord(BaseModel):
    """
    Conversation record matching MonkAI's structure.
    Supports both flat token fields and TokenUsage object.
    """
    namespace: str = Field(..., description="Agent namespace")
    agent: str = Field(..., description="Agent name")
    session_id: Optional[str] = Field(None, description="Session identifier")
    msg: Union[Message, List[Message], Dict] = Field(..., description="Message(s)")
    
    # Flat token fields (for convenience)
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    process_tokens: Optional[int] = None
    memory_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    
    # Transfer information
    transfers: Optional[List[Transfer]] = None
    inserted_at: Optional[str] = None
    
    # Additional fields
    user_id: Optional[str] = None
    user_whatsapp: Optional[str] = None
    wam_id: Optional[str] = None
    replied_whatsapp: Optional[str] = None
    attachments: Optional[List[Any]] = None
    
    def to_api_format(self) -> Dict:
        """Convert to API request format"""
        data = {
            "namespace": self.namespace,
            "agent": self.agent,
            "msg": self._format_messages(),
        }
        
        # Add optional fields
        if self.session_id:
            data["session_id"] = self.session_id
        # Always include token fields, even if 0
        data["input_tokens"] = self.input_tokens or 0
        data["output_tokens"] = self.output_tokens or 0
        data["process_tokens"] = self.process_tokens or 0
        data["memory_tokens"] = self.memory_tokens or 0
        if self.transfers:
            data["transfers"] = [t.model_dump(by_alias=True) for t in self.transfers]
        if self.inserted_at:
            data["inserted_at"] = self.inserted_at
        if self.user_id:
            data["user_id"] = self.user_id
        if self.user_whatsapp:
            data["user_whatsapp"] = self.user_whatsapp
            
        return data
    
    def _format_messages(self):
        """Format messages for API"""
        if isinstance(self.msg, list):
            formatted = []
            for m in self.msg:
                if isinstance(m, Message):
                    # Only include essential fields for API
                    msg_dict = {
                        "role": m.role,
                        "content": m.content
                    }
                    # Note: API may not accept "sender" or "tool_name" fields
                    # Only include if explicitly needed by API
                    formatted.append(msg_dict)
                else:
                    formatted.append(m)
            return formatted
        elif isinstance(self.msg, Message):
            msg_dict = {
                "role": self.msg.role,
                "content": self.msg.content
            }
            return msg_dict
        else:
            return self.msg


class LogEntry(BaseModel):
    """Log entry matching MonkAI's structure"""
    namespace: str = Field(..., description="Namespace for this log")
    level: str = Field(..., description="Log level: info, warn, error, debug")
    message: str = Field(..., description="Log message")
    timestamp: Optional[str] = Field(None, description="ISO-8601 timestamp")
    resource_id: Optional[str] = Field(None, description="Resource identifier")
    custom_object: Optional[Dict[str, Any]] = Field(None, description="Custom data")
    
    def to_api_format(self) -> Dict:
        """Convert to API request format"""
        data = {
            "namespace": self.namespace,
            "level": self.level,
            "message": self.message,
        }
        
        if self.timestamp:
            data["timestamp"] = self.timestamp
        if self.resource_id:
            data["resource_id"] = self.resource_id
        if self.custom_object:
            data["custom_object"] = self.custom_object
            
        return data
