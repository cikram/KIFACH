"""Review and validate procedure steps and their dependencies."""

from app.domain.models import Procedure, ProcedureDraft, ReviewChange, ValidationResult


def apply_review(draft: ProcedureDraft, changes: ReviewChange) -> Procedure:
    pass


def validate_procedure(procedure: Procedure) -> ValidationResult:
    pass
