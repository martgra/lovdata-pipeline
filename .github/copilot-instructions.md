---
description: "Python coding conventions and guidelines"
applyTo: "**/*.py"
---

# Python Coding Conventions

## Python Instructions

- Write clear and concise comments for each function.
- Ensure functions have descriptive names and include type hints.
- Provide docstrings following PEP 257 conventions.
- Break down complex functions into smaller, more manageable functions.
- Follow the one responsibility principle

## General Instructions

- Always prioritize readability and clarity.
- For algorithm-related code, include explanations of the approach used.
- Write code with good maintainability practices, including comments on why certain design decisions were made.
- Handle edge cases and write clear exception handling.
- For libraries or external dependencies, mention their usage and purpose in comments.
- Use consistent naming conventions and follow language-specific best practices.
- Write concise, efficient, and idiomatic code that is also easily understandable.

## Code Style and Formatting

- Follow the **PEP 8** style guide for Python.
- Maintain proper indentation (use 4 spaces for each level of indentation).
- Ensure lines do not exceed 100 characters.
- Place function and class docstrings immediately after the `def` or `class` keyword.
- Use blank lines to separate functions, classes, and code blocks where appropriate.
- Use google style doc strings

## Edge Cases and Testing

- Always include test cases for critical paths of the application.
- Account for common edge cases like empty inputs, invalid data types, and large datasets.
- Write unit tests for functions and document them with docstrings explaining the test cases.
- use name_test.py convention for test files

## Project instructions

- Always use the tool context7 to look up documentation for the libraries you use.
- Always check with docs/implementation_guide.md for implementation details
- Always check with docs/architecture_guide.md to align with architeture.
- Add libraries only after checking whats available in pyproject.toml
- The project must pass check defined in pre-commit file.

## Environment instructions

- This project use uv - so all python instructions are with a uv run prefix
- never add dependencies by editing pyproject.toml always use uv commands
- Th project uses prek instead of pre-commit
