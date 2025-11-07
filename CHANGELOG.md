# Changelog

All notable changes to monkai-trace-python will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
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
