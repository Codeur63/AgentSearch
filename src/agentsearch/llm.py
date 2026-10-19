"""Activité de synthèse ; les règles métier sont dans application.synthesis."""
from temporalio import activity

from agentsearch.application.synthesis import format_sources, synthesize
from agentsearch.domain.models import SynthesisInput
from agentsearch.infrastructure.groq_model import GroqLanguageModel

__all__ = ['ask_llm', 'format_sources']


@activity.defn(name='ask_llm')
def ask_llm(synthesis: SynthesisInput) -> str:
    return synthesize(synthesis, GroqLanguageModel())
