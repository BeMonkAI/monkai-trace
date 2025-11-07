# Upgrade Guide

This guide helps you migrate your code when upgrading between major versions of monkai-trace-python.

## From v0.1.x to Current (Commit fc7764e)

### Breaking Changes

#### 1. Logging Integration: `metadata` → `custom_object`

**Old Code:**
```python
log_entry = LogEntry(
    namespace="my-app",
    level="info",
    message="User logged in",
    metadata={"user_id": "123"}  # ❌ Old field name
)
```

**New Code:**
```python
log_entry = LogEntry(
    namespace="my-app",
    level="info",
    message="User logged in",
    custom_object={"user_id": "123"}  # ✅ New field name
)
```

**Why?** Aligns with MonkAI API schema and prevents confusion with internal metadata.

**Migration:** Search and replace `metadata=` with `custom_object=` in `LogEntry` instantiations.

---

#### 2. Logging Handler: `upload_logs()` → `upload_logs_batch()`

**Impact:** Internal change only - no code changes required.

The `MonkAILogHandler` now uses `client.upload_logs_batch()` instead of `client.upload_logs()`.

**Benefits:**
- Consistent naming with `upload_records_batch()`
- Better performance for batch uploads
- Clearer API semantics

---

#### 3. OpenAI Agents: Import Path Update

**Old Code:**
```python
from agents.context import RunContextWrapper  # ❌ Old import
```

**New Code:**
```python
from agents.run_context import RunContextWrapper  # ✅ New import
```

**Why?** Compatibility with latest `openai-agents-python` package.

**Migration:** This is handled internally by the integration. No user code changes needed.

---

### Non-Breaking Improvements

#### 1. LangChain Integration (New Feature)

**New Feature:**
```python
from monkai_trace.integrations.langchain import MonkAICallbackHandler

handler = MonkAICallbackHandler(
    tracer_token="tk_your_token",
    namespace="my-agents"
)

agent = initialize_agent(tools, llm, callbacks=[handler])
```

**Benefit:** Full LangChain support with automatic conversation tracking.

---

#### 2. Graceful Optional Dependencies

**Old Behavior:**
```python
# ❌ Crashed on import if LangChain not installed
from monkai_trace.integrations.langchain import MonkAICallbackHandler
# ImportError: No module named 'langchain'
```

**New Behavior:**
```python
# ✅ Import succeeds, error only on instantiation
from monkai_trace.integrations.langchain import MonkAICallbackHandler

handler = MonkAICallbackHandler(...)
# ImportError: LangChain is required for this integration. Install it with: pip install langchain
```

**Benefit:** Better error messages and allows importing without all dependencies installed.

---

#### 3. Consistent Token Fields

**Old Behavior:**
```python
# Token fields were omitted if None/0
{
  "msg": {"role": "user", "content": "Hi"},
  "input_tokens": 10
  # ❌ output_tokens, process_tokens, memory_tokens missing
}
```

**New Behavior:**
```python
# All token fields always present
{
  "msg": {"role": "user", "content": "Hi"},
  "input_tokens": 10,
  "output_tokens": 0,    # ✅ Explicit 0
  "process_tokens": 0,   # ✅ Explicit 0
  "memory_tokens": 0     # ✅ Explicit 0
}
```

**Benefit:** Consistent analytics and prevents dashboard rendering issues.

---

#### 4. Improved Error Messages

**Old Error:**
```
HTTPError: 400 Bad Request
```

**New Error:**
```
HTTPError: 400 Bad Request: {"error": "Invalid namespace format", "details": "Namespace must contain only lowercase letters, numbers, and hyphens"}
```

**Benefit:** Faster debugging with detailed error context.

---

## Migration Checklist

- [ ] **Logging Code:** Replace `metadata=` with `custom_object=` in `LogEntry` instantiations
- [ ] **Dependencies:** Ensure `openai-agents-python` is updated to latest version (if using)
- [ ] **Tests:** Run full test suite to verify compatibility
- [ ] **LangChain (Optional):** Install LangChain integration if needed: `pip install langchain`
- [ ] **Review Logs:** Check MonkAI dashboard to verify custom_object fields appear correctly

---

## Need Help?

- 📧 Email: support@monkai.ai
- 💬 Discord: [Join our community](https://discord.gg/monkai)
- 📖 Docs: [Full documentation](https://docs.monkai.ai)
- 🐛 Issues: [GitHub Issues](https://github.com/monkai/monkai-trace-python/issues)
