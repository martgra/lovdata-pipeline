"""Path parsing utilities for Lovdata file paths.

This module provides utilities for parsing and manipulating Lovdata file paths,
extracting dataset names and relative paths from absolute paths.
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class ParsedLovdataPath:
    """Represents a parsed Lovdata file path.

    Attributes:
        dataset_name: Dataset name with .tar.bz2 extension (e.g., 'gjeldende-lover.tar.bz2')
        relative_path: Relative path within dataset (e.g., 'nl/nl-18840614-003.xml')
        dataset_name_raw: Dataset name without extension (e.g., 'gjeldende-lover')
        document_id: Document ID extracted from filename stem
    """

    dataset_name: str
    relative_path: str
    dataset_name_raw: str
    document_id: str


def parse_lovdata_path(absolute_path: Path, extracted_data_dir: Path) -> ParsedLovdataPath | None:
    """Parse a Lovdata file path into its components.

    Expected structure: extracted_data_dir/dataset_name/relative_path

    Args:
        absolute_path: Absolute path to the file
        extracted_data_dir: Base directory for extracted data

    Returns:
        ParsedLovdataPath object or None if path cannot be parsed

    Example:
        >>> from pathlib import Path
        >>> path = Path('/data/extracted/gjeldende-lover/nl/nl-18840614-003.xml')
        >>> extracted_dir = Path('/data/extracted')
        >>> parsed = parse_lovdata_path(path, extracted_dir)
        >>> parsed.dataset_name
        'gjeldende-lover.tar.bz2'
        >>> parsed.relative_path
        'nl/nl-18840614-003.xml'
    """
    try:
        # Get path relative to extracted directory
        relative_to_extracted = absolute_path.relative_to(extracted_data_dir)
        parts = relative_to_extracted.parts

        if len(parts) < 2:
            # Need at least dataset/file
            return None

        # First part is dataset name (without .tar.bz2)
        dataset_name_raw = parts[0]
        dataset_name = f"{dataset_name_raw}.tar.bz2"

        # Remaining parts form the relative path
        relative_path = str(Path(*parts[1:]))

        # Extract document ID from filename
        document_id = absolute_path.stem

        return ParsedLovdataPath(
            dataset_name=dataset_name,
            relative_path=relative_path,
            dataset_name_raw=dataset_name_raw,
            document_id=document_id,
        )

    except (ValueError, IndexError):
        # Path is not relative to extracted_data_dir or malformed
        return None


def parse_lovdata_path_legacy(absolute_path: Path) -> tuple[str | None, str | None]:
    """Parse Lovdata path by searching for 'extracted' directory.

    This is a legacy function for backward compatibility when extracted_data_dir
    is not known. Prefer using parse_lovdata_path() when possible.

    Args:
        absolute_path: Absolute path to the file

    Returns:
        Tuple of (dataset_name, relative_path) or (None, None) if parsing fails

    Example:
        >>> from pathlib import Path
        >>> path = Path('/workspace/data/extracted/gjeldende-lover/nl/file.xml')
        >>> dataset, rel_path = parse_lovdata_path_legacy(path)
        >>> dataset
        'gjeldende-lover.tar.bz2'
    """
    try:
        parts = absolute_path.parts

        # Find index of "extracted" directory
        extracted_idx = None
        for i, part in enumerate(parts):
            if part == "extracted":
                extracted_idx = i
                break

        if extracted_idx is None or extracted_idx + 1 >= len(parts):
            return None, None

        # Dataset is next part after extracted
        dataset_name_raw = parts[extracted_idx + 1]
        dataset_name = f"{dataset_name_raw}.tar.bz2"

        # Relative path is remaining parts
        if extracted_idx + 2 < len(parts):
            relative_path = str(Path(*parts[extracted_idx + 2 :]))
        else:
            return None, None

        return dataset_name, relative_path

    except (ValueError, IndexError):
        return None, None
