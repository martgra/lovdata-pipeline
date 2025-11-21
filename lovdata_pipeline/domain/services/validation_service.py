"""State validation service.

Validates consistency between pipeline state and vector store.
"""

from dataclasses import dataclass

from lovdata_pipeline.domain.vector_store import VectorStoreRepository
from lovdata_pipeline.state import ProcessingState


@dataclass
class ValidationResult:
    """Result of state validation."""

    state_doc_count: int
    store_doc_count: int
    in_state_not_store: set[str]
    in_store_not_state: set[str]

    @property
    def is_consistent(self) -> bool:
        """Check if state and store are consistent."""
        return len(self.in_state_not_store) == 0 and len(self.in_store_not_state) == 0


class ValidationService:
    """Service for validating state consistency.

    Single Responsibility: Validate that pipeline state matches vector store contents.
    """

    def __init__(self, state: ProcessingState, vector_store: VectorStoreRepository):
        """Initialize validation service.

        Args:
            state: Pipeline state tracker
            vector_store: Vector store repository
        """
        self._state = state
        self._vector_store = vector_store

    def validate(self) -> ValidationResult:
        """Validate state consistency against vector store.

        Returns:
            ValidationResult with detailed comparison

        Raises:
            Exception: If vector store operations fail
        """
        # Get document IDs from both sources
        state_doc_ids = set(self._state.state.processed.keys())
        store_doc_ids = self._vector_store.get_all_document_ids()

        # Find inconsistencies
        in_state_not_store = state_doc_ids - store_doc_ids
        in_store_not_state = store_doc_ids - state_doc_ids

        return ValidationResult(
            state_doc_count=len(state_doc_ids),
            store_doc_count=len(store_doc_ids),
            in_state_not_store=in_state_not_store,
            in_store_not_state=in_store_not_state,
        )
