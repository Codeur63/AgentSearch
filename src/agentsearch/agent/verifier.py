"""Adaptateur d'activité du vérificateur documentaire."""
from temporalio import activity

from agentsearch.application.verification import verify_claims
from agentsearch.domain.models import FactCheckInput, FactCheckReport
from agentsearch.infrastructure.groq_model import GroqLanguageModel


@activity.defn(name='verify_claims')
def verify_synthesis(data: FactCheckInput) -> FactCheckReport:
    return verify_claims(data, GroqLanguageModel())
