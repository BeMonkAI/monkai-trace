#!/usr/bin/env python3
"""
Inject `x-codeSamples` into every operation in `docs/openapi.yaml`.

Renders three samples per operation:

  - cURL with `Authorization: Bearer` and the `/v1/` base URL
  - Node.js using the native `fetch` API (Node 18+)
  - Python using the `requests` library

Run from the repo root:

    .venv/bin/python scripts/add_code_samples.py

Idempotent — overwrites any existing `x-codeSamples` block.
"""
from __future__ import annotations

import sys
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import LiteralScalarString

API_BASE = "https://api.monkai.ai/trace/v1"
LEGACY_BASE = (
    "https://lpvbvnqrozlwalnkvrgk.supabase.co/functions/v1/monkai-api/v1"
)
TOKEN_ENV = "MONKAI_TRACER_TOKEN"


def example_payload(operation_id: str) -> str:
    """Concrete example bodies, kept short for readability."""
    if operation_id == "healthCheck" or operation_id == "healthCheckHead":
        return ""  # GET/HEAD, no body
    if operation_id == "traceBatch":
        return (
            '{"traces":['
            '{"type":"llm","session_id":"sess_abc","model":"gpt-4","input":{"messages":[{"role":"user","content":"hi"}]},"output":{"content":"hello"}},'
            '{"type":"tool","session_id":"sess_abc","tool_name":"get_weather","arguments":{"city":"SP"},"result":{"temp":24}},'
            '{"type":"log","session_id":"sess_abc","level":"info","message":"done"}'
            "]}"
        )
    if operation_id == "createSession":
        return '{"namespace":"my-agent","user_id":"5521999998888","inactivity_timeout":300}'
    if operation_id == "getOrCreateSession":
        return '{"namespace":"my-agent","user_id":"5521999998888"}'
    if operation_id == "traceLlmCall":
        return (
            '{"session_id":"sess_abc","model":"gpt-4","input":{"messages":'
            '[{"role":"user","content":"Hi"}]},"output":{"content":"Hello"}}'
        )
    if operation_id == "traceToolCall":
        return (
            '{"session_id":"sess_abc","tool_name":"get_weather",'
            '"arguments":{"city":"SP"},"result":{"temp":24}}'
        )
    if operation_id == "traceHandoff":
        return (
            '{"session_id":"sess_abc","from_agent":"triage",'
            '"to_agent":"sales","reason":"intent matched"}'
        )
    if operation_id == "traceLog":
        return '{"session_id":"sess_abc","level":"info","message":"step 5 done"}'
    if operation_id == "uploadRecords":
        return (
            '{"records":[{"namespace":"my-agent","agent":"bot",'
            '"msg":[{"role":"user","content":"hi"}]}]}'
        )
    if operation_id == "uploadLogs":
        return '{"logs":[{"namespace":"my-agent","level":"info","message":"hi"}]}'
    if operation_id == "queryRecords":
        return '{"namespace":"my-agent","query":{"limit":50}}'
    if operation_id == "queryLogs":
        return '{"namespace":"my-agent","level":"error","limit":100}'
    if operation_id == "exportRecords":
        return '{"namespace":"my-agent","format":"json"}'
    if operation_id == "exportLogs":
        return '{"namespace":"my-agent","format":"csv"}'
    return "{}"


def curl_sample(path: str, body: str, method: str = "POST") -> str:
    if method in ("GET", "HEAD"):
        flag = " -I" if method == "HEAD" else ""
        return f"curl{flag} \"{API_BASE}{path}\"\n"
    return (
        f"curl -X {method} \"{API_BASE}{path}\" \\\n"
        f"  -H \"Authorization: Bearer ${TOKEN_ENV}\" \\\n"
        f"  -H \"Content-Type: application/json\" \\\n"
        f"  -H \"X-Request-ID: $(uuidgen)\" \\\n"
        f"  -d '{body}'\n"
    )


def node_sample(path: str, body: str, method: str = "POST") -> str:
    if method in ("GET", "HEAD"):
        return (
            "// Node.js 18+ — no dependencies, no auth required\n"
            f"const res = await fetch(\"{API_BASE}{path}\", {{ method: \"{method}\" }});\n"
            "console.log(res.status, res.headers.get(\"x-request-id\"));\n"
        )
    return (
        "// Node.js 18+ — no dependencies\n"
        f"const res = await fetch(\"{API_BASE}{path}\", {{\n"
        f"  method: \"{method}\",\n"
        "  headers: {\n"
        f"    \"Authorization\": `Bearer ${{process.env.{TOKEN_ENV}}}`,\n"
        "    \"Content-Type\": \"application/json\"\n"
        "  },\n"
        f"  body: JSON.stringify({body})\n"
        "});\n"
        "console.log(res.headers.get(\"x-request-id\"), await res.json());\n"
    )


def python_sample(path: str, body: str, method: str = "POST") -> str:
    if method in ("GET", "HEAD"):
        verb = method.lower()
        return (
            "import requests\n"
            f"r = requests.{verb}(\"{API_BASE}{path}\")\n"
            "print(r.status_code, r.headers[\"x-request-id\"])\n"
        )
    return (
        "import os, requests\n"
        f"r = requests.post(\n"
        f"    \"{API_BASE}{path}\",\n"
        f"    headers={{\"Authorization\": f\"Bearer {{os.environ['{TOKEN_ENV}']}}\"}},\n"
        f"    json={body},\n"
        f")\n"
        f"print(r.headers[\"x-request-id\"], r.json())\n"
    )


def build_code_samples(path: str, operation_id: str, method: str = "POST") -> list[dict]:
    body = example_payload(operation_id)
    return [
        {"lang": "Shell", "label": "curl", "source": LiteralScalarString(curl_sample(path, body, method))},
        {"lang": "JavaScript", "label": "Node.js", "source": LiteralScalarString(node_sample(path, body, method))},
        {"lang": "Python", "label": "Python", "source": LiteralScalarString(python_sample(path, body, method))},
    ]


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    spec_path = repo_root / "docs" / "openapi.yaml"

    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 4096
    yaml.indent(mapping=2, sequence=4, offset=2)

    with spec_path.open() as f:
        spec = yaml.load(f)

    paths = spec.get("paths", {})
    touched = 0
    for path, item in paths.items():
        for method, op in item.items():
            if not isinstance(op, dict) or "operationId" not in op:
                continue
            # Skip HEAD operations — same semantics as GET, code samples
            # would be redundant. ReDoc renders HEAD without samples cleanly.
            if method.lower() == "head":
                continue
            op["x-codeSamples"] = build_code_samples(
                path, op["operationId"], method=method.upper()
            )
            touched += 1

    with spec_path.open("w") as f:
        yaml.dump(spec, f)

    print(f"Injected x-codeSamples into {touched} operations.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
