"""Imports de compatibilité ; les contrats métier sont dans domain.models."""
from agentsearch.domain.models import (
    DocumentAssessment, ExtractedDocument, SearchResult, State, SynthesisInput,
    VerificationInput, VerificationResult, WorkflowStatus,
)

__all__ = [
    'DocumentAssessment', 'ExtractedDocument', 'SearchResult', 'State',
    'SynthesisInput', 'VerificationInput', 'VerificationResult', 'WorkflowStatus',
]
