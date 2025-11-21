# Contributing to Lovdata Pipeline

Thank you for your interest in contributing to the Lovdata Pipeline! This document provides guidelines and best practices for contributing.

## Table of Contents

- [Getting Started](#getting-started)
- [Development Workflow](#development-workflow)
- [Code Quality Standards](#code-quality-standards)
- [Testing Requirements](#testing-requirements)
- [Pull Request Process](#pull-request-process)
- [Requirements Checklist](#requirements-checklist)
- [Code Style Guide](#code-style-guide)
- [Getting Help](#getting-help)

## Getting Started

### Prerequisites

- Python 3.11+
- Git
- Basic understanding of Python and command-line tools

### Setup Development Environment

```bash
# Fork and clone the repository
git clone https://github.com/YOUR-USERNAME/lovdata-pipeline.git
cd lovdata-pipeline

# Install dependencies
make install

# Install pre-commit hooks
uv run prek install

# Verify setup
make test
```

## Development Workflow

### 1. Create a Feature Branch

```bash
git checkout -b feature/your-feature-name
```

Use descriptive branch names:
- `feature/add-elasticsearch-storage` - New features
- `fix/embedding-rate-limit` - Bug fixes
- `docs/improve-architecture-guide` - Documentation
- `refactor/simplify-chunking` - Code refactoring

### 2. Make Changes

- Write clear, focused code
- Add tests for new functionality
- Update documentation as needed
- Follow the code style guide (see below)

### 3. Test Your Changes

```bash
# Run all tests
make test

# Run specific test file
uv run pytest tests/unit/test_your_feature.py -v

# Check code coverage
make coverage

# Run linting
make lint

# Format code
make format
```

### 4. Commit Your Changes

```bash
git add .
git commit -m "Add feature: clear description"
```

**Commit Message Guidelines:**
- Use present tense ("Add feature" not "Added feature")
- Use imperative mood ("Move cursor to..." not "Moves cursor to...")
- First line should be 50 characters or less
- Reference issues and PRs when applicable

Examples:
```
Add Elasticsearch vector store implementation
Fix rate limiting for OpenAI embedding API
Update GUIDE.md with migration examples
Refactor chunking service for better performance
```

### 5. Push and Create Pull Request

```bash
git push origin feature/your-feature-name
```

Then create a pull request on GitHub.

## Code Quality Standards

### Linting and Formatting

All code must pass:

- **Ruff** formatting and linting
- **Pylint** code quality checks
- **Type hints** for all functions

These are automatically checked by pre-commit hooks and CI.

### Pre-commit Hooks

> **Note:** This project uses `prek`, a fast Rust-based pre-commit hook manager.

Hooks run automatically on commit:
- Code formatting (Ruff)
- Linting (Ruff, Pylint)
- Trailing whitespace removal
- YAML validation

To run manually:
```bash
uv run prek run --all-files
```

## Testing Requirements

### Test Coverage

- All new features must include tests
- Aim for >80% code coverage
- Test both happy paths and error cases

### Test Structure

**Unit Tests** (`tests/unit/`)
- Fast, isolated tests
- Mock external dependencies
- Test individual components

**Integration Tests** (`tests/integration/`)
- Test service interactions
- Use real components where possible
- Verify end-to-end workflows

**Example Test:**

```python
import pytest
from lovdata_pipeline.domain.services.chunking_service import ChunkingService

def test_chunk_file():
    """Test chunking a legal document."""
    # Arrange
    service = ChunkingService(target_tokens=768)
    xml_path = "tests/fixtures/sample.xml"

    # Act
    chunks = service.chunk_file(
        xml_path=xml_path,
        doc_id="test-doc",
        dataset="test"
    )

    # Assert
    assert len(chunks) > 0
    assert all(chunk.token_count <= 8191 for chunk in chunks)
    assert all(chunk.document_id == "test-doc" for chunk in chunks)
```

## Pull Request Process

### Before Submitting

1. ✅ All tests pass (`make test`)
2. ✅ Code is formatted (`make format`)
3. ✅ Linting passes (`make lint`)
4. ✅ Documentation is updated
5. ✅ Commit messages are clear
6. ✅ Branch is up to date with main

### PR Description Template

```markdown
## Summary
Brief description of changes

## Motivation
Why is this change needed?

## Changes
- List of specific changes made
- Use bullet points

## Testing
How was this tested?

## Checklist
- [ ] Tests added/updated
- [ ] Documentation updated
- [ ] Code formatted and linted
- [ ] All tests pass
```

### Review Process

1. **Automated checks** must pass (CI tests, linting)
2. **Code review** by at least one maintainer
3. **Address feedback** and update PR as needed
4. **Approval** from maintainer
5. **Merge** to main branch

## Requirements Checklist

Before merging changes, verify these functional requirements:

### Change Detection
- [ ] Pipeline only processes added/modified files
- [ ] Uses file hash comparison (lovlig vs pipeline state)
- [ ] Detects renamed files as removed + added
- [ ] Handles missing state files gracefully

### Change Handling
- [ ] Removed files: chunks deleted from vector store
- [ ] Modified files: old chunks deleted, new chunks added
- [ ] Added files: chunks created and stored
- [ ] Atomic per-file processing (all or nothing)

### Processing
- [ ] Each file processed independently
- [ ] Failures don't block other files
- [ ] Failed files tracked in state
- [ ] Progress reporting shows current file

### State Management
- [ ] `pipeline_state.json` tracks processed/failed files
- [ ] State updated after each file completes
- [ ] State includes file hash for change detection
- [ ] State recoverable if corrupted

### Index Consistency
- [ ] No orphaned chunks (file deleted but chunks remain)
- [ ] No duplicate chunks (same chunk stored twice)
- [ ] Chunks deleted when source file removed/modified
- [ ] Chunk IDs unique across all documents
- [ ] Metadata format compatible with storage backend
- [ ] Migration between storage backends preserves all data

### Error Handling
- [ ] Network errors: retry with exponential backoff
- [ ] Rate limits: respect API limits, queue requests
- [ ] File errors: log and continue with other files
- [ ] State corruption: detect and recover/rebuild

### Observability
- [ ] Progress: current file, completion percentage
- [ ] Statistics: processed, failed, removed counts
- [ ] Errors: clear error messages with context
- [ ] State: can inspect processing status

## Code Style Guide

### General Principles

- **Keep it simple** - This is a straightforward ETL pipeline
- **Single responsibility** - Each class/function does one thing
- **Dependency injection** - Services receive dependencies via constructor
- **Protocol-based interfaces** - Use protocols for extensibility
- **Type hints** - Always use type hints

### Python Style

```python
# Good: Clear, typed, single responsibility
def chunk_file(
    xml_path: str,
    doc_id: str,
    dataset: str,
    target_tokens: int = 768
) -> list[ChunkMetadata]:
    """Chunk a legal document into semantic chunks.

    Args:
        xml_path: Path to XML file
        doc_id: Document identifier
        dataset: Dataset name
        target_tokens: Target tokens per chunk

    Returns:
        List of chunk metadata objects

    Raises:
        ValueError: If file doesn't exist or is invalid
    """
    # Implementation
    pass
```

### Naming Conventions

- **Classes**: PascalCase (`ChunkingService`, `EmbeddingProvider`)
- **Functions/Methods**: snake_case (`chunk_file`, `embed_text`)
- **Constants**: UPPER_SNAKE_CASE (`TARGET_TOKENS`, `MAX_RETRIES`)
- **Private**: Prefix with underscore (`_internal_method`)

### Documentation

- Write docstrings for all public classes and functions
- Use Google-style docstrings
- Include examples for complex functionality
- Keep comments concise and meaningful

### Architecture Patterns

Follow existing patterns in the codebase:

- **Service-Oriented**: Each service has single responsibility
- **Protocol Interfaces**: Define protocols for extensibility
- **Factory Pattern**: Use factories for dependency wiring
- **Immutable Data**: Use Pydantic models for data

## Getting Help

- **Questions?** Open a [GitHub Discussion](https://github.com/martgra/lovdata-pipeline/discussions)
- **Bug reports:** Open a [GitHub Issue](https://github.com/martgra/lovdata-pipeline/issues)
- **Documentation:** Check [DEVELOPMENT.md](docs/DEVELOPMENT.md) for architecture details
- **Examples:** Look at existing code for patterns

## Recognition

Contributors are recognized in:
- Git commit history
- Release notes
- README acknowledgments

Thank you for contributing to Lovdata Pipeline! 🎉
