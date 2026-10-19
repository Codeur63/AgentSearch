"""Tests sur un vrai serveur Temporal, sans accès à Groq ni publication externe.

AGENTSEARCH_TEMPORAL_BIN=/chemin/temporal pytest tests/test_temporal_integration.py -q
"""

import asyncio
import os
import uuid
from datetime import date

import pytest
from temporalio import activity
from temporalio.client import WorkflowUpdateFailedError
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Replayer, Worker

from agentsearch.domain.models import (
    EditorialPreferences, ExtractedDocument, FactCheckInput, FactCheckReport,
    HumanDecision, PublicationCommand, PublicationDraft, PublicationReceipt, ResearchRequest, SearchResult,
    SynthesisInput, WorkflowStatus, WritingInput,
)
from agentsearch.orchestration.workflows import ContentWorkflow
from agentsearch.tools.filter_sources import filter_sources
from agentsearch.tools.verify_content import verify_content

pytestmark = pytest.mark.skipif(
    not os.getenv('AGENTSEARCH_TEMPORAL_BIN'),
    reason='Définir AGENTSEARCH_TEMPORAL_BIN pour les tests avec serveur local',
)


async def wait_status(handle, status, draft_version=None):
    async with asyncio.timeout(30):
        while True:
            state = await handle.query(ContentWorkflow.snapshot)
            if state.status == status and (draft_version is None or (state.draft and state.draft.version == draft_version)):
                return state
            if state.status in {WorkflowStatus.FAILED, WorkflowStatus.NEEDS_INPUT}:
                raise AssertionError(state)
            await asyncio.sleep(0.05)


def test_human_review_survives_worker_restart_and_replays():
    async def scenario():
        calls = []
        publications = []
        sources = [SearchResult(title='Agents IA', url=f'https://{domain}/a', snippet='Agents IA')
                   for domain in ('example.com', 'example.org')]

        @activity.defn(name='search_web')
        async def search(query: str) -> list[SearchResult]:
            calls.append(query)
            return sources

        @activity.defn(name='extract_content')
        async def extract(source: SearchResult) -> ExtractedDocument:
            text = 'Les agents IA utilisent des outils pour rechercher des informations fiables. ' * 35
            return ExtractedDocument(url=source.url, title=source.title, content=text,
                                     word_count=len(text.split()), published_at=date(2026, 10, 19))

        @activity.defn(name='ask_llm')
        async def synthesize(data: SynthesisInput) -> str:
            return 'Les agents IA utilisent des outils [1] [2].'

        @activity.defn(name='verify_claims')
        async def verify(data: FactCheckInput) -> FactCheckReport:
            return FactCheckReport(sufficient=True)

        @activity.defn(name='write_draft')
        async def write(data: WritingInput) -> PublicationDraft:
            return PublicationDraft(version=data.version, synthesis_version=data.synthesis.version,
                                    content='Une publication [1]', platform=data.preferences.platform, tone=data.preferences.tone)

        @activity.defn(name='publish_draft')
        async def publish(command: PublicationCommand) -> PublicationReceipt:
            publications.append(command)
            return PublicationReceipt(platform=command.draft.platform, status='published', remote_id='fake-post')

        async with await WorkflowEnvironment.start_local(
            dev_server_existing_path=os.environ['AGENTSEARCH_TEMPORAL_BIN'],
            data_converter=pydantic_data_converter,
        ) as env:
            activities = [search, filter_sources, verify_content, synthesize, verify, write, publish]
            async with Worker(env.client, task_queue='agent-scraper', activities=[extract]):
                # Les deux activités synchrones nécessitent un exécuteur.
                from concurrent.futures import ThreadPoolExecutor
                with ThreadPoolExecutor(max_workers=4) as executor:
                    async with Worker(env.client, task_queue='agent-search', workflows=[ContentWorkflow],
                                      activities=activities, activity_executor=executor):
                        handle = await env.client.start_workflow(
                            ContentWorkflow.run,
                            ResearchRequest(question='Agents IA', reference_date=date(2026, 10, 19)),
                            id=f'test-{uuid.uuid4()}', task_queue='agent-search',
                        )
                        state = await wait_status(handle, WorkflowStatus.WAITING_SYNTHESIS)
                        assert state.synthesis.version == 1
                    # Nouveau worker : reconstruction de l'état depuis l'historique.
                    async with Worker(env.client, task_queue='agent-search', workflows=[ContentWorkflow],
                                      activities=activities, activity_executor=executor):
                        state = await wait_status(handle, WorkflowStatus.WAITING_SYNTHESIS)
                        assert len(calls) == 1
                        with pytest.raises(WorkflowUpdateFailedError):
                            await handle.execute_update(ContentWorkflow.decide, HumanDecision(
                                stage='synthesis', version=9, action='finish',
                            ))
                        await handle.execute_update(ContentWorkflow.decide, HumanDecision(
                            stage='synthesis', version=1, action='approve',
                            preferences=EditorialPreferences(tone='pédagogique'),
                        ))
                        state = await wait_status(handle, WorkflowStatus.WAITING_DRAFT)
                        await handle.execute_update(ContentWorkflow.decide, HumanDecision(
                            stage='draft', version=state.draft.version,
                            action='revise_style', feedback='Plus court',
                        ))
                        state = await wait_status(handle, WorkflowStatus.WAITING_DRAFT, draft_version=2)
                        assert state.draft.version == 2
                        await handle.execute_update(ContentWorkflow.decide, HumanDecision(
                            stage='draft', version=2, action='approve',
                        ))
                        await wait_status(handle, WorkflowStatus.WAITING_PUBLICATION)
                        await handle.execute_update(ContentWorkflow.decide, HumanDecision(
                            stage='publication', version=2, action='finish',
                        ))
                        result = await handle.result()
                        assert result.status == WorkflowStatus.COMPLETED
                        assert result.draft.tone == 'pédagogique'
                        assert result.receipt is None
                        assert len(result.decisions) == 4
                        history = await handle.fetch_history()
                        await Replayer(workflows=[ContentWorkflow], data_converter=pydantic_data_converter).replay_workflow(history)
                        assert not publications
                        # Un refus sur les données invalide le brouillon et repasse par la synthèse.
                        second = await env.client.start_workflow(
                            ContentWorkflow.run,
                            ResearchRequest(question='Agents IA', reference_date=date(2026, 10, 19)),
                            id=f'test-data-{uuid.uuid4()}', task_queue='agent-search',
                        )
                        await wait_status(second, WorkflowStatus.WAITING_SYNTHESIS)
                        await second.execute_update(ContentWorkflow.decide, HumanDecision(
                            stage='synthesis', version=1, action='approve', preferences=EditorialPreferences(),
                        ))
                        await wait_status(second, WorkflowStatus.WAITING_DRAFT)
                        await second.execute_update(ContentWorkflow.decide, HumanDecision(
                            stage='draft', version=1, action='revise_data', feedback='Confirmer les dates',
                        ))
                        state = await wait_status(second, WorkflowStatus.WAITING_SYNTHESIS)
                        assert state.synthesis.version == 2 and state.draft is None
                        await second.execute_update(ContentWorkflow.decide, HumanDecision(
                            stage='synthesis', version=2, action='approve', preferences=EditorialPreferences(),
                        ))
                        await wait_status(second, WorkflowStatus.WAITING_DRAFT, draft_version=2)
                        await second.execute_update(ContentWorkflow.decide, HumanDecision(
                            stage='draft', version=2, action='approve',
                        ))
                        await wait_status(second, WorkflowStatus.WAITING_PUBLICATION)
                        assert not publications
                        await second.execute_update(ContentWorkflow.decide, HumanDecision(
                            stage='publication', version=2, action='publish',
                        ))
                        result = await second.result()
                        assert result.status == WorkflowStatus.COMPLETED
                        assert result.receipt.remote_id == 'fake-post'
                        assert len(publications) == 1 and publications[0].approved_version == 2
    asyncio.run(scenario())
