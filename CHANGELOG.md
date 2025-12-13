# Changelog

All notable changes to monkai-trace-python will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
