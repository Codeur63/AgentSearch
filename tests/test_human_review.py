import pytest
from pydantic import ValidationError

from agentsearch.domain.models import (
    EditorialPreferences, FactCheckReport, HumanDecision,
    PublicationCommand, PublicationDraft, Synthesis, WorkflowStatus,
)
from agentsearch.orchestration.workflows import ContentWorkflow


def flow_waiting():
    flow = ContentWorkflow()
    flow.state.status = WorkflowStatus.WAITING_SYNTHESIS
    flow.state.synthesis = Synthesis(version=2, text='Texte', documents=[], verification=FactCheckReport(sufficient=True))
    return flow


def test_stale_approval_rejected():
    flow = flow_waiting()
    decision = HumanDecision(stage='synthesis', version=1, action='approve', preferences=EditorialPreferences())
    with pytest.raises(ValueError, match='périmée'):
        flow.validate_decision(decision)
    assert not flow.state.decisions


def test_duplicate_decision_rejected():
    flow = flow_waiting()
    decision = HumanDecision(stage='synthesis', version=2, action='approve', preferences=EditorialPreferences())
    flow.validate_decision(decision)
    flow.decide(decision)
    with pytest.raises(ValueError):
        flow.validate_decision(decision)


def test_publication_requires_matching_approval_and_authorization():
    draft = PublicationDraft(version=2, synthesis_version=1, content='Texte', platform='linkedin', tone='informatif')
    with pytest.raises(ValidationError):
        PublicationCommand(publication_id='test', draft=draft, approved_version=2)
    with pytest.raises(ValidationError):
        PublicationCommand(publication_id='test', draft=draft, approved_version=1, authorized=True)


def test_revision_requires_feedback():
    with pytest.raises(ValidationError):
        HumanDecision(stage='draft', version=1, action='revise_style')


def test_human_wait_expires_without_publication(monkeypatch):
    import asyncio
    from datetime import date
    from agentsearch.domain.models import ResearchRequest
    from temporalio import workflow

    async def expired(*args, **kwargs):
        raise TimeoutError
    monkeypatch.setattr(workflow, 'wait_condition', expired)
    flow = flow_waiting()
    request = ResearchRequest(question='Agents IA', reference_date=date(2026, 10, 19))
    assert asyncio.run(flow.wait_for_decision(WorkflowStatus.WAITING_SYNTHESIS, request)) is None
    assert flow.state.status == WorkflowStatus.EXPIRED
    assert flow.state.receipt is None
