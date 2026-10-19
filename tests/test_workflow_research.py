import asyncio
from datetime import date

from agentsearch.domain.models import (
    ExtractedDocument, FactCheckReport, ResearchRequest, SearchResult,
    VerificationResult, WorkflowStatus,
)
from agentsearch.orchestration.workflows import ContentWorkflow


def test_research_retries_with_follow_up_and_stops_on_success():
    flow = ContentWorkflow()
    queries = []
    checks = []
    doc = ExtractedDocument(url='https://example.com/a', title='Agents IA', content='Texte', word_count=1)

    async def fake(name, data, result_type, **kwargs):
        if name == 'search_web':
            queries.append(data)
            return [SearchResult(title=doc.title, url=doc.url)]
        if name == 'filter_sources':
            return data.sources
        if name == 'extract_content':
            return doc
        if name == 'verify_content':
            return VerificationResult(sufficient=True, accepted_documents=[doc], assessments=[], total_words=300, unique_domains=2)
        if name == 'ask_llm':
            return 'Synthèse [1]'
        if name == 'verify_claims':
            checks.append(data)
            return FactCheckReport(sufficient=len(checks) == 2,
                                   issues=[] if len(checks) == 2 else ['À confirmer'],
                                   follow_up_queries=['confirmation annonce'])
        raise AssertionError(name)

    flow.activity = fake
    assert asyncio.run(flow.research(ResearchRequest(question='Agents IA', reference_date=date(2026, 10, 19))))
    assert len(queries) == 2
    assert 'confirmation annonce' in queries[1]
    assert flow.state.llm_calls == 4
    assert flow.state.synthesis.version == 2


def test_research_limit_does_not_loop_forever():
    flow = ContentWorkflow()
    async def fake(name, data, result_type, **kwargs):
        if name in {'search_web', 'filter_sources'}:
            return []
        if name == 'verify_content':
            return VerificationResult(sufficient=False, accepted_documents=[], assessments=[],
                                      total_words=0, unique_domains=0, reasons=['Sources insuffisantes'])
        raise AssertionError(name)
    flow.activity = fake
    request = ResearchRequest(question='Agents IA', reference_date=date(2026, 10, 19), max_research_attempts=2)
    assert not asyncio.run(flow.research(request))
    assert flow.state.research_attempts == 2
    assert flow.state.status == WorkflowStatus.NEEDS_INPUT
