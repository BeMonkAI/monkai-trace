# Changelog

All notable changes to monkai-trace-python will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.13] - 2026-02-12

### Added
- **Programmatic Data Export**: New methods for querying and exporting conversation records and logs
  - `query_records()` - Query records with filters (namespace, agent, date range, pagination)
  - `query_logs()` - Query logs with filters (namespace, level, date range, pagination)
  - `export_records()` - Export records to JSON or CSV files with automatic server-side pagination
  - `export_logs()` - Export logs to JSON or CSV files with automatic server-side pagination
- New REST API endpoints: `/records/export` and `/logs/export` for bulk data extraction
- New example: `examples/export_data.py` demonstrating query and export workflows
- New documentation: `docs/data_export.md` with complete export guide

## [0.2.10] - 2025-12-14 ✅ STABLE RELEASE

### Fixed
- **Critical fix for internal tools with batch_size=1**: The `on_agent_end` hook was calling `_flush_batch()` immediately when `batch_size=1`, BEFORE `_capture_internal_tools_from_result()` could add internal tools to the record. This caused internal tools (web_search, file_search, etc.) to never be included in uploaded records.
- **JSON serialization fix for sources**: `ActionSearchSource` and other Pydantic objects from OpenAI SDK were not JSON serializable, causing upload failures with error "Object of type ActionSearchSource is not JSON serializable".

### Added
- **`_skip_auto_flush` flag**: New internal flag to prevent `on_agent_end` from auto-flushing when using `run_with_tracking()`. This ensures internal tools are captured before flush.
- **`_serialize_to_dict()` method**: New helper method to recursively serialize Pydantic objects, dataclasses, and other complex types to JSON-serializable dictionaries. Handles `model_dump()` for Pydantic models with fallbacks for other types.

### Changed
- `run_with_tracking()` now sets `_skip_auto_flush=True` before running and resets it in the `finally` block.
- `on_agent_end` now checks `_skip_auto_flush` flag before auto-flushing, ensuring `run_with_tracking()` controls the flush timing.
- `_parse_internal_tool_details()` now uses `_serialize_to_dict()` for sources and results to ensure JSON serialization.

### Technical Details
The fix addresses the following execution order issue:
```
# BEFORE (v0.2.9 - broken with batch_size=1):
1. Runner.run() calls on_agent_end internally
2. on_agent_end adds record to buffer AND flushes (buffer now empty)
3. _capture_internal_tools_from_result() called - buffer is empty, tools lost!

# AFTER (v0.2.10 - fixed):
1. run_with_tracking() sets _skip_auto_flush=True
2. Runner.run() calls on_agent_end
3. on_agent_end adds record to buffer (no flush due to flag)
4. _capture_internal_tools_from_result() adds internal tools to record
5. finally block flushes with complete record including internal tools
```

### Notes
- v0.2.5-v0.2.9 had various issues with internal tool capture timing and serialization
- Users should upgrade to v0.2.10 for reliable internal tool capture with sources
- `batch_size=1` is now fully supported and recommended for real-time monitoring

## [0.2.9] - 2025-12-14

### Fixed
- **Critical fix for internal tools capture**: Moved `_capture_internal_tools_from_result()` to execute BEFORE `_flush_batch()`. Previously, internal tools were captured AFTER flush, meaning the buffer was already cleared and internal tool messages were never saved.
- This ensures `web_search`, `file_search`, `code_interpreter`, and `computer_use` tool calls are correctly included in uploaded records.

### Changed
- Internal tool capture now happens in both main try block and ImportError fallback, ensuring coverage for all SDK versions.
- Flush now correctly happens AFTER internal tools are added to the buffer.

### Notes
- v0.2.5-v0.2.8 had various issues with internal tool capture timing
- Users should upgrade to v0.2.9 for reliable internal tool capture
- **⚠️ Bug**: Still had issues with `batch_size=1` - fixed in v0.2.10

## [0.2.8] - 2025-12-13

### Fixed
- **Critical fix for record upload**: Records now guaranteed to upload via `finally` block in `run_with_tracking()`. Fixes "0 records uploaded" issue in v0.2.7.
- **Fixed ModelSettings import**: Changed from `from agents.model_settings import ModelSettings` to `from agents import RunConfig, ModelSettings` for SDK compatibility.
- **Removed debug logs**: Cleaned up excessive `[MonkAI DEBUG]` print statements from `_capture_internal_tools()`.

### Added
- **`flush()` method**: Public async method to force upload of buffered records immediately. Useful for users calling `Runner.run()` directly instead of `run_with_tracking()`.

### Changed
- Exception handling in `run_with_tracking()` now catches broader `Exception` types and re-raises after ensuring flush.
- Internal tool capture moved to after successful result, before return.

### Notes
- v0.2.5, v0.2.6, v0.2.7 had issues with sources capture and/or record upload
- Users should upgrade directly to v0.2.8 for reliable operation

## [0.2.7] - 2025-12-13

### Fixed
- **Critical fix for sources capture**: The `include` parameter was being passed as a direct kwarg to `Runner.run()`, which ignores unknown kwargs. Now correctly passed via `RunConfig.model_settings.response_include`.
- Sources are now properly requested from OpenAI API and captured in web_search_call records.

### Changed
- `run_with_tracking()` now creates/merges `RunConfig` with `ModelSettings(response_include=[...])`.
- Added fallback for older agents SDK versions.

## [0.2.6] - 2025-12-13

### Fixed
- Sources extraction path corrected to `action.sources` (note: was ineffective due to Runner.run ignoring kwargs - fixed in v0.2.7).

## [0.2.5] - 2025-12-13 [YANKED]

### Note
This version had incorrect sources extraction logic and has been superseded by v0.2.6

## [0.2.4] - 2024-12-13

### Fixed
- **Critical Fix for Internal Tools Capture**: Internal tools (web_search, file_search, code_interpreter, computer_use) are now correctly captured from the complete `RunResult`
  - `on_agent_end` only receives `final_output` (string), not the full result with `new_items`
  - Moved internal tool capture to `run_with_tracking()` which has access to complete `RunResult`
  - New method `_capture_internal_tools_from_result()` processes `result.new_items` and `result.raw_responses`
  - New helper method `_process_items_for_internal_tools()` handles both direct and wrapped tool items
  - Internal tools are now correctly added to the buffered conversation record before upload

### Changed
- **[BREAKING]** `run_with_tracking()` is now `async` and must be awaited: `result = await MonkAIRunHooks.run_with_tracking(agent, input, hooks)`

## [0.2.3] - 2024-12-12

### Added
- **Debug Logging for Internal Tools**: Comprehensive debug output in `_capture_internal_tools()` to investigate `Runner.run()` output structure
  - Logs output type, class name, and all public attributes
  - Logs specific attribute values: `raw_items`, `new_items`, `items`, `output`, `final_output`, `messages`, `raw_response`, `data`
  - Logs first 5 items of list attributes with their class and type
  - Logs nested `raw_item` structures within `tool_call_item` wrappers
  - Logs context attributes and `context.response.raw_items` when available
  - Identifies source of captured raw_items for debugging

### Fixed
- Extended internal tool capture to check additional locations:
  - `output.new_items` (RunResult structure)
  - `output.items`
  - `output.output.raw_items` (nested streaming results)
  - `output.output.new_items`
  - `output.data.raw_items`
- Added fallback nested attribute check for `raw_item`, `item`, `data`, `content`

## [0.2.2] - 2024-12-12

### Fixed
- **Web Search Capture Fix**: Fixed capture of `web_search_call` and other internal tools that are wrapped in `tool_call_item`
  - Now correctly extracts internal tools from `item.raw_item.type` when `item.type == 'tool_call_item'`
  - Added fallback check for `output.web_searches` array
  - Refactored `_parse_internal_tool_details()` to support both object attributes and dictionary access
- Added helper methods `_get_attr()` and `_add_internal_tool_message()` for cleaner code organization

## [0.2.1] - 2024-12-11

### Added
- **Internal OpenAI Tools Capture**: Automatic capture of OpenAI's built-in tools that don't trigger regular hooks
  - `web_search_call` - Web search queries, sources, and results
  - `file_search_call` - File search queries and matched results
  - `code_interpreter_call` - Code execution with language and output
  - `computer_call` - Computer use actions and outputs
- New `Message` fields: `is_internal_tool` and `internal_tool_type` for identifying internal tools
- New `_capture_internal_tools()` method in `MonkAIRunHooks` to extract tools from `response.raw_items`
- New `_parse_internal_tool_details()` method for type-specific argument/result extraction
- Documentation section on internal tools in `docs/openai_agents_integration.md`

### Changed
- `_format_messages()` now includes `is_internal_tool` and `internal_tool_type` fields in API output
- Internal tools appear alongside custom tools in MonkAI Conversations panel

## [0.2.0] - 2024-12-09

### Added
- **Handoffs as Tool Messages**: Agent handoffs (`on_handoff`) now automatically create a `tool` type message in addition to the `Transfer` record
  - New tool message with `tool_name="transfer_to_agent"` for frontend visualization
  - Includes `from_agent`, `to_agent`, and `reason` (when available) in `tool_calls` arguments
  - Enables frontend to display handoffs as tool calls without synthetic message generation
- Full LangChain integration with `MonkAICallbackHandler`
- Graceful import handling for optional dependencies (LangChain, OpenAI Agents)
- Batch upload support for improved performance

### Changed
- **[BREAKING]** Logging integration now uses `custom_object` instead of `metadata` in `LogEntry` model
- **[BREAKING]** Logging handler now uses `upload_logs_batch()` instead of `upload_logs()` for consistency
- Updated OpenAI Agents integration to use `agents.run_context` (compatible with latest openai-agents-python)
- Improved error handling in client with detailed error messages
- Message formatting now uses whitelist approach for API compatibility
- Token fields (`input_tokens`, `output_tokens`, `process_tokens`, `memory_tokens`) now always present in API requests (defaults to 0)

### Fixed
- LangChain integration can now be imported without LangChain installed (raises error only on instantiation)
- Consistent token field presence prevents analytics inconsistencies
- Import path compatibility with updated openai-agents-python package

## [0.1.0] - 2024-01-XX

### Added
- Initial release
- OpenAI Agents integration via `MonkAIRunHooks`
- Python logging integration via `MonkAILogHandler`
- Core client for conversation and log uploads
- Batch upload support
- Token usage tracking with segmentation
- Multi-agent transfer tracking
- JSON file upload utilities

## [0.1.0] - 2024-01-XX

### Added
- Initial release
- OpenAI Agents integration via `MonkAIRunHooks`
- Python logging integration via `MonkAILogHandler`
- Core client for conversation and log uploads
- Batch upload support
- Token usage tracking with segmentation
- Multi-agent transfer tracking
- JSON file upload utilities
