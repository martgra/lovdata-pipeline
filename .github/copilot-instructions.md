# Project instructions

Begin with a concise checklist (3-7 bullets) of what you will do; keep items conceptual, not implementation-level.

## Python Instructions

- Write clear and concise comments for each function.
- Ensure that functions have descriptive names and include type hints.
- Provide docstrings following PEP 257 conventions.
- Break down complex functions into smaller, more manageable functions.
- Adhere to the single responsibility principle.
- **Check existing dependencies before implementing**: Don't reinvent the wheel—use existing libraries when available.

## General Instructions

- Always prioritize readability and clarity.
- For algorithm-related code, include explanations of the approach used.
- Write maintainable code by including comments explaining the rationale behind design decisions.
- Handle edge cases and implement clear exception handling.
- For libraries or external dependencies, mention their usage and purpose in comments.
- Use consistent naming conventions and follow language-specific best practices.
- Write concise, efficient, and idiomatic code that remains easily understandable.

## Code Style and Formatting

- Follow the **PEP 8** style guide for Python.
- Maintain proper indentation (use 4 spaces per indentation level).
- Ensure that lines do not exceed 100 characters.
- Place function and class docstrings immediately after the `def` or `class` keyword.
- Use blank lines to separate functions, classes, and code blocks where appropriate.
- Use Google-style docstrings.

## Edge Cases and Testing

- Always include test cases for critical paths of the application.
- Account for common edge cases such as empty inputs, invalid data types, and large datasets.
- Write unit tests for functions and document them with docstrings explaining the test cases.
- Use the `*_test.py` convention for test file naming.
- If editing code: (1) state assumptions, (2) create or run minimal tests where possible, (3) produce ready-to-review diffs, and (4) follow repository code style. If tests cannot be run, clearly document that tests are speculative and add next-step validation instructions.

## Environment Instructions

- This project uses `uv`; therefore, all Python commands should be prefixed with `uv run`.
- Never add dependencies by editing `pyproject.toml` directly—always use `uv` commands.
- The project uses `prek` instead of `pre-commit` for pre-commit hooks.

## Dependency Management

- **Before writing custom utilities, ALWAYS check existing dependencies first**:
  - Run `grep -i <library> pyproject.toml` to check if a library is already available
  - Check the dependencies section in `pyproject.toml` for available libraries
  - Common libraries already available: `tenacity` (retry logic), `pydantic` (validation), `lxml` (XML), `tiktoken` (tokenization)
- **Prefer battle-tested libraries over custom implementations** for common problems like:
  - Retry logic → use `tenacity`
  - HTTP requests → use `httpx` or `requests`
  - Validation → use `pydantic`
  - Date/time → use standard library `datetime`
- **Only write custom code when**:
  - No suitable library exists
  - The library is significantly over-engineered for the use case
  - The custom implementation is trivial (< 20 lines)
- **When adding new dependencies**:
  - Use `uv add <package>` to add to `pyproject.toml`
  - Justify the addition (explain why existing options don't suffice)
  - Prefer well-maintained, widely-used libraries

## Documentation Navigation

### For User Questions

| Question                             | Reference File/Section                    |
| ------------------------------------ | ----------------------------------------- |
| How do I install/run the pipeline?   | docs/GUIDE.md (Installation section)      |
| What commands are available?         | docs/GUIDE.md (Usage section)             |
| How do I configure X?                | docs/GUIDE.md (Configuration section)     |
| Pipeline fails with error Y?         | docs/GUIDE.md (Troubleshooting section)   |
| What data does the pipeline process? | docs/GUIDE.md (File Structure section)    |
| Performance tips?                    | docs/GUIDE.md (Performance section)       |

### For Development Questions

| Question                              | Reference File/Section                                   |
| ------------------------------------- | -------------------------------------------------------- |
| What's the architecture?              | docs/DEVELOPMENT.md (Architecture section)               |
| How do I add a new feature?           | docs/DEVELOPMENT.md (Extending the Pipeline section)     |
| Where is X implemented?               | docs/DEVELOPMENT.md (Project Structure section)          |
| What are the data models?             | docs/DEVELOPMENT.md (Data Models section)                |
| How does incremental processing work? | docs/GUIDE.md (Processing Behavior section)              |
| How do I run tests?                   | docs/DEVELOPMENT.md (Testing section)                    |
| What must I verify before merging?    | docs/DEVELOPMENT.md (Requirements Checklist section)     |

### Quick Documentation Summary

- **README.md** – Project overview and quick start (start here)
- **docs/GUIDE.md** – Complete user manual (installation, configuration, usage, troubleshooting)
- **docs/DEVELOPMENT.md** – Developer reference (architecture, extending, testing, contributing)
- **docs/archive/** – Historical documentation (archived, not actively maintained)

- **README.md** – Project overview and quick start (start here)
- **README.md** – Project overview and quick start (start here)
- **docs/GUIDE.md** – Complete user manual (installation, configuration, usage, troubleshooting)
- **docs/DEVELOPMENT.md** – Developer reference (architecture, extending, testing, contributing)
- **docs/archive/** – Historical documentation (archived, not actively maintained)

### Updating Documentation

- After implementing or changing something, always update the documentation accordingly.
- User-facing changes → update docs/GUIDE.md
- Developer-facing changes → update docs/DEVELOPMENT.md
- Keep docs concise and functional - no verbose explanations
