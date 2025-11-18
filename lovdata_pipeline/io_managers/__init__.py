"""IO Managers for the Lovdata pipeline.

This module provides custom IO Managers that handle serialization and
storage of intermediate data between assets, replacing manual file I/O
with Dagster-managed storage.
"""

from lovdata_pipeline.io_managers.chunks_io_manager import ChunksIOManager

__all__ = ["ChunksIOManager"]
