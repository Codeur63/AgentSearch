"""Activité de rédaction."""
from temporalio import activity

from agentsearch.application.writing import write_draft
from agentsearch.domain.models import PublicationDraft, WritingInput
from agentsearch.infrastructure.groq_model import GroqLanguageModel


@activity.defn(name='write_draft')
def create_draft(data: WritingInput) -> PublicationDraft:
    return write_draft(data, GroqLanguageModel())
