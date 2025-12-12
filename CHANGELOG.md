# Changelog

All notable changes to monkai-trace-python will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
