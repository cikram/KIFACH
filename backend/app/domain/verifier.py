"""Assess observations against a reviewed procedure."""

from app.domain.models import Assessment, Observation, ObservationSet, Procedure, StepMatch


def match_observation(observation: Observation, procedure: Procedure) -> StepMatch:
    pass


def assess_attempt(procedure: Procedure, observations: ObservationSet) -> Assessment:
    pass


def reassess_after_correction(
    previous: Assessment, observations: ObservationSet
) -> Assessment:
    pass
