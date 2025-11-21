"""File operation utilities for atomic writes and safe file handling.

NOTE: This module is currently UNUSED in the codebase.
State.py implements its own atomic write logic inline.
Consider removing if not needed or consolidating atomic write logic here.

This module provides utilities for safely writing files atomically to prevent
corruption from partial writes or crashes.
"""

import json
from pathlib import Path


def atomic_write_json(
    file_path: Path,
    data: dict,
    indent: int = 2,
    ensure_ascii: bool = True,
    **json_kwargs,
) -> None:
    """Write JSON data to file atomically using temp file + rename.

    This ensures the target file is never in a partially-written state.
    The write-then-rename operation is atomic on all modern filesystems.

    Args:
        file_path: Path to the target JSON file
        data: Dictionary to serialize as JSON
        indent: JSON indentation (default: 2)
        ensure_ascii: Whether to escape non-ASCII characters (default: False)
        **json_kwargs: Additional arguments to pass to json.dump()

    Example:
        >>> from pathlib import Path
        >>> atomic_write_json(Path("config.json"), {"key": "value"})
    """
    # Ensure parent directory exists
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # Write to temporary file
    temp_file = file_path.with_suffix(".tmp")
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent, ensure_ascii=ensure_ascii, **json_kwargs)

    # Atomic rename (overwrites target file)
    temp_file.replace(file_path)
