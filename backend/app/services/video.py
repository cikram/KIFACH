"""Accept media and locate evidence within it."""

from app.domain.models import EvidenceRef, MediaRef, Observation, ObservationSet, StepFinding


def accept_media(source: object) -> MediaRef:
    pass


def locate_evidence(media: MediaRef, observation: Observation) -> EvidenceRef:
    pass


def evidence_for_finding(
    finding: StepFinding, observations: ObservationSet
) -> EvidenceRef:
    pass
