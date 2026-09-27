"""Entry points for learner attempts and assessments."""

from app.domain.models import Assessment, MediaRef, Procedure


def practice(procedure: Procedure, learner_media: MediaRef) -> Assessment:
    pass
