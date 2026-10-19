"""Règles de recherche indépendantes du moteur et de Temporal."""

import re
from datetime import date

from agentsearch.domain.models import ResearchRequest, SearchResult
from agentsearch.ports.services import SearchProvider


def make_request(question: str, reference_date: date, **kwargs) -> ResearchRequest:
    """La date vient de l'interface, pour ne pas dépendre de l'horloge du workflow."""
    normalized = question.lower().replace('’', "'")
    today = bool(re.search(r"aujourd[' ]?hui|ce jour|today", normalized))
    recent = today or any(term in normalized for term in ('actualité', 'actualite', 'cette semaine', 'récent', 'recent'))
    defaults = {'require_freshness': recent, 'max_age_days': 0 if today else 7 if recent else 365}
    return ResearchRequest(question=question, reference_date=reference_date, **(defaults | kwargs))


def research_query(request: ResearchRequest, feedback: str, follow_up: list[str], attempt: int) -> str:
    query = request.question
    if request.require_freshness:
        query += f' {request.reference_date.isoformat()}'
    if follow_up:
        query += ' ' + follow_up[(attempt - 1) % len(follow_up)][:500]
    elif feedback:
        query += ' ' + feedback[:500]
    if attempt > 1:
        query += ' sources primaires confirmation' if attempt % 2 == 0 else ' nouvelles sources indépendantes'
    return query


def find_sources(question: str, provider: SearchProvider) -> list[SearchResult]:
    question = question.strip()
    if not question:
        raise ValueError('Question vide')
    return provider.search(question)
