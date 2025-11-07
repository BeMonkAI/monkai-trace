# Contributing to MonkAI Trace Python SDK

Thank you for your interest in contributing to MonkAI Trace!

## Development Setup

1. Clone the repository:
```bash
git clone https://github.com/monkai/monkai-trace-python
cd monkai-trace-python
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install development dependencies:
```bash
pip install -e ".[dev]"
```

## Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=monkai_trace --cov-report=html

# Run specific test file
pytest tests/test_client.py
```

## Code Style

We use Black for formatting and Ruff for linting:

```bash
# Format code
black monkai_trace tests

# Lint code
ruff monkai_trace tests

# Type checking
mypy monkai_trace
```

## Pull Request Process

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Add tests for new functionality
5. Run tests and linting
6. Commit your changes (`git commit -m 'Add amazing feature'`)
7. Push to the branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

## Code Guidelines

- Write clear, concise commit messages
- Add docstrings to all public functions and classes
- Include type hints for all function parameters and returns
- Write tests for new features
- Update documentation as needed
- Follow PEP 8 style guidelines

## Questions?

Feel free to open an issue or reach out on Discord!
