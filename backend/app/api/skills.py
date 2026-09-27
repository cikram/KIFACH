"""Entry points for creating and reviewing a skill."""

from app.domain.models import MediaRef, Procedure, ProcedureDraft, ReviewChange


def teach(expert_media: MediaRef) -> ProcedureDraft:
    pass


def confirm_procedure(draft: ProcedureDraft, changes: ReviewChange) -> Procedure:
    pass
