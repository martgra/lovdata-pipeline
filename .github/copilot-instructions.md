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

| Question                             | Reference File/Section                       |
| ------------------------------------ | -------------------------------------------- |
| How do I install/run the pipeline?   | docs/USER_GUIDE.md                           |
| What commands are available?         | docs/QUICK_REFERENCE.md                      |
| How do I configure X?                | docs/USER_GUIDE.md (Configuration section)   |
| Pipeline fails with error Y?         | docs/USER_GUIDE.md (Troubleshooting section) |
| What data does the pipeline process? | docs/USER_GUIDE.md (Pipeline Steps section)  |

### For Development Questions

| Question                              | Reference File/Section                                    |
| ------------------------------------- | --------------------------------------------------------- |
| What's the architecture?              | docs/DEVELOPER_GUIDE.md (Architecture section)            |
| How do I add a new pipeline step?     | docs/DEVELOPER_GUIDE.md (Extending the Pipeline section)  |
| Where is X implemented?               | docs/DEVELOPER_GUIDE.md (Project Structure section)       |
| How does error handling work?         | docs/DEVELOPER_GUIDE.md (Pipeline Implementation section) |
| What are the data models?             | docs/DEVELOPER_GUIDE.md (Data Models section)             |
| How does incremental processing work? | docs/INCREMENTAL_UPDATES.md                               |
| How do I run tests?                   | docs/DEVELOPER_GUIDE.md (Testing section)                 |

### For Specification Questions

| Question                           | Reference File/Section                                          |
| ---------------------------------- | --------------------------------------------------------------- |
| What are the requirements?         | docs/FUNCTIONAL_REQUIREMENTS.md                                 |
| Does the pipeline handle removals? | docs/FUNCTIONAL_REQUIREMENTS.md (Change Handling section)       |
| Is it idempotent?                  | docs/FUNCTIONAL_REQUIREMENTS.md (section 2.4)                   |
| What must I verify before merging? | docs/FUNCTIONAL_REQUIREMENTS.md (Verification Checklist at end) |

### Quick Documentation Summary

- **README.md** – Project overview and quick start (start here)
- **docs/USER_GUIDE.md** – Complete user manual (installation, configuration, usage, troubleshooting)
- **docs/DEVELOPER_GUIDE.md** – Developer reference (architecture, extending, testing)
- **docs/FUNCTIONAL_REQUIREMENTS.md** – Specification (requirements all changes must satisfy)
- **docs/QUICK_REFERENCE.md** – Command cheat sheet
- **docs/INCREMENTAL_UPDATES.md** – Change detection details
- **docs/archive/** – Historical implementation docs (archived, not actively maintained)

### Updating Documentation

- After implementing or changing something, always update the documentation accordingly.
