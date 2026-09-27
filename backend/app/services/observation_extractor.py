"""Extract observations without judging correctness."""

from app.domain.models import MediaRef, ObservationSet, Procedure


def observe_demonstration(media: MediaRef) -> ObservationSet:
    pass


def observe_attempt(media: MediaRef, procedure: Procedure) -> ObservationSet:
    pass
