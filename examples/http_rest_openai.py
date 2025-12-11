"""
Example of MonkAI Trace with OpenAI using HTTP REST API

This example shows how to trace OpenAI API calls using the
HTTP REST API without the MonkAI SDK.
"""

import time
import requests
from openai import OpenAI


# Configuration
MONKAI_API = "https://lpvbvnqrozlwalnkvrgk.supabase.co/functions/v1/monkai-api"
TRACER_TOKEN = "tk_your_token_here"  # Replace with your MonkAI token
NAMESPACE = "openai-demo"


class MonkAITracer:
    """Simple tracer for MonkAI HTTP REST API."""
    
    def __init__(self, token: str, namespace: str):
        self.token = token
        self.namespace = namespace
        self.base_url = MONKAI_API
        self.session_id = None
    
    def _headers(self):
        return {
            "tracer_token": self.token,
            "Content-Type": "application/json"
        }
    
    def start_session(self, user_id: str, metadata: dict = None) -> str:
        """Start a new tracking session."""
        response = requests.post(
            f"{self.base_url}/sessions/create",
            headers=self._headers(),
            json={
                "namespace": self.namespace,
                "user_id": user_id,
                "inactivity_timeout": 300,
                "metadata": metadata or {}
            }
        )
        response.raise_for_status()
        self.session_id = response.json()["session_id"]
        return self.session_id
    
    def trace_completion(
        self,
        model: str,
        messages: list,
        response_content: str,
        usage: dict,
        latency_ms: int
    ):
        """Trace an OpenAI completion call."""
        requests.post(
            f"{self.base_url}/traces/llm",
            headers=self._headers(),
            json={
                "session_id": self.session_id,
                "model": model,
                "provider": "openai",
                "input": {"messages": messages},
                "output": {
                    "content": response_content,
                    "usage": {
                        "prompt_tokens": usage.get("prompt_tokens", 0),
                        "completion_tokens": usage.get("completion_tokens", 0)
                    }
                },
                "latency_ms": latency_ms
            }
        )
    
    def trace_tool_call(
        self,
        tool_name: str,
        arguments: dict,
        result: any,
        latency_ms: int
    ):
        """Trace a tool/function call."""
        requests.post(
            f"{self.base_url}/traces/tool",
            headers=self._headers(),
            json={
                "session_id": self.session_id,
                "tool_name": tool_name,
                "arguments": arguments,
                "result": result,
                "latency_ms": latency_ms
            }
        )


def get_weather(city: str) -> dict:
    """Mock weather function."""
    return {
        "city": city,
        "temperature": 22,
        "condition": "partly cloudy",
        "humidity": 65
    }


def main():
    # Initialize OpenAI client
    client = OpenAI()  # Uses OPENAI_API_KEY env var
    
    # Initialize MonkAI tracer
    tracer = MonkAITracer(token=TRACER_TOKEN, namespace=NAMESPACE)
    
    print("MonkAI Trace + OpenAI Example")
    print("=" * 50)
    
    # Start session
    session_id = tracer.start_session(
        user_id="demo-user",
        metadata={"example": "openai-integration"}
    )
    print(f"\nSession started: {session_id}")
    
    # Define tools
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get current weather for a city",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {
                            "type": "string",
                            "description": "City name"
                        }
                    },
                    "required": ["city"]
                }
            }
        }
    ]
    
    # User message
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What's the weather like in Tokyo?"}
    ]
    
    print("\nUser: What's the weather like in Tokyo?")
    
    # First completion (may include tool call)
    start_time = time.time()
    response = client.chat.completions.create(
        model="gpt-4",
        messages=messages,
        tools=tools,
        tool_choice="auto"
    )
    latency_ms = int((time.time() - start_time) * 1000)
    
    # Trace the LLM call
    assistant_message = response.choices[0].message
    tracer.trace_completion(
        model="gpt-4",
        messages=messages,
        response_content=assistant_message.content or "[tool_call]",
        usage={
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens
        },
        latency_ms=latency_ms
    )
    
    # Handle tool calls if any
    if assistant_message.tool_calls:
        for tool_call in assistant_message.tool_calls:
            if tool_call.function.name == "get_weather":
                import json
                args = json.loads(tool_call.function.arguments)
                
                # Execute tool
                tool_start = time.time()
                result = get_weather(args["city"])
                tool_latency = int((time.time() - tool_start) * 1000)
                
                # Trace tool call
                tracer.trace_tool_call(
                    tool_name="get_weather",
                    arguments=args,
                    result=result,
                    latency_ms=tool_latency
                )
                
                print(f"\nTool called: get_weather({args})")
                print(f"Result: {result}")
                
                # Add tool result to messages
                messages.append(assistant_message.model_dump())
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result)
                })
        
        # Get final response
        start_time = time.time()
        final_response = client.chat.completions.create(
            model="gpt-4",
            messages=messages
        )
        latency_ms = int((time.time() - start_time) * 1000)
        
        final_content = final_response.choices[0].message.content
        
        # Trace final completion
        tracer.trace_completion(
            model="gpt-4",
            messages=messages,
            response_content=final_content,
            usage={
                "prompt_tokens": final_response.usage.prompt_tokens,
                "completion_tokens": final_response.usage.completion_tokens
            },
            latency_ms=latency_ms
        )
        
        print(f"\nAssistant: {final_content}")
    else:
        print(f"\nAssistant: {assistant_message.content}")
    
    print("\n" + "=" * 50)
    print("✅ All traces sent to MonkAI!")
    print("   View your data at: https://monkai.app/monitoring")


if __name__ == "__main__":
    main()
