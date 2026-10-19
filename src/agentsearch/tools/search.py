"""Activité de recherche utilisant un fournisseur remplaçable."""
from temporalio import activity

from agentsearch.application.research import find_sources
from agentsearch.domain.models import SearchResult
from agentsearch.infrastructure.search import DDGSSearchProvider


@activity.defn(name='search_web')
def search_web(question: str) -> list[SearchResult]:
    return find_sources(question, DDGSSearchProvider())
