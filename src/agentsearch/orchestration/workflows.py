"""Orchestration déterministe : les accès externes sont exclusivement des activités."""

import asyncio
from datetime import timedelta
from typing import TypeVar

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

with workflow.unsafe.imports_passed_through():
    from agentsearch.application.research import research_query
    from agentsearch.domain.models import (
        EditorialPreferences, ExtractedDocument, FactCheckInput, FactCheckReport, ResearchRequest,
        SearchResult, Synthesis, SynthesisInput, VerificationInput,
        VerificationResult, WorkflowSnapshot, WorkflowStatus,
        HumanDecision, PublicationCommand, PublicationDraft, PublicationReceipt, WritingInput,
    )
    from agentsearch.tools.filter_sources import FilterSourcesInput

T = TypeVar('T')

MAIN_TASK_QUEUE = 'agent-search'
SCRAPER_TASK_QUEUE = 'agent-scraper'
RETRY = RetryPolicy(maximum_attempts=2, initial_interval=timedelta(seconds=1))


@workflow.defn
class ContentWorkflow:
    def __init__(self) -> None:
        self.state = WorkflowSnapshot()
        self.pending_decision: HumanDecision | None = None

    @workflow.query
    def snapshot(self) -> WorkflowSnapshot:
        return self.state

    async def activity(self, name: str, data: object, result_type: type[T], *, scraper: bool = False) -> T:
        return await workflow.execute_activity(
            name, data, result_type=result_type,
            task_queue=SCRAPER_TASK_QUEUE if scraper else MAIN_TASK_QUEUE,
            start_to_close_timeout=timedelta(minutes=2),
            schedule_to_close_timeout=timedelta(minutes=4),
            retry_policy=(RetryPolicy(maximum_attempts=1)
                          if name in {"ask_llm", "verify_claims", "write_draft"} else RETRY),
        )

    async def research(self, request: ResearchRequest, feedback: str = '') -> bool:
        documents: dict[str, ExtractedDocument] = {}
        follow_up: list[str] = []
        # Toute nouvelle recherche invalide les validations portant sur les anciennes données.
        self.state.draft = None
        self.state.synthesis = None
        while self.state.research_attempts < request.max_research_attempts:
            self.state.research_attempts += 1
            self.state.status = WorkflowStatus.RESEARCHING
            query = research_query(request, feedback, follow_up, self.state.research_attempts)
            sources = await self.activity('search_web', query, list[SearchResult])
            selected = await self.activity('filter_sources', FilterSourcesInput(
                question=request.question, sources=sources, max_sources=request.max_sources,
                allowed_domains=request.allowed_domains,
            ), list[SearchResult])
            extracted = await asyncio.gather(*[
                self.activity('extract_content', source, ExtractedDocument, scraper=True)
                for source in selected
            ], return_exceptions=True)
            for result in extracted:
                if isinstance(result, Exception):
                    continue
                documents[str(result.url)] = result
            # Borne la charge et la taille de l'historique à chaque tentative.
            bounded = list(documents.values())[-request.max_sources:]
            report = await self.activity('verify_content', VerificationInput(
                question=request.question, documents=bounded,
                require_freshness=request.require_freshness,
                max_age_days=request.max_age_days, reference_date=request.reference_date,
            ), VerificationResult)
            self.state.issues = report.reasons
            if not report.sufficient:
                continue
            if self.state.llm_calls + 2 > request.max_llm_calls:
                self.state.issues = ['Budget des appels LLM atteint']
                break
            self.state.status = WorkflowStatus.VERIFY
            data = SynthesisInput(
                question=request.question, sources=report.accepted_documents,
                language=request.language, feedback=feedback,
            )
            self.state.llm_calls += 1
            text = await self.activity('ask_llm', data, str)
            self.state.llm_calls += 1
            checks = await self.activity('verify_claims', FactCheckInput(synthesis=data, text=text), FactCheckReport)
            self.state.issues = checks.issues
            if checks.sufficient:
                self.state.synthesis = Synthesis(
                    version=self.state.research_attempts, text=text,
                    documents=report.accepted_documents, verification=checks,
                )
                return True
            follow_up = checks.follow_up_queries
        self.state.status = WorkflowStatus.NEEDS_INPUT
        if not self.state.issues:
            self.state.issues = ['Limite de recherches atteinte ; préciser la demande ou lancer une nouvelle tâche']
        return False

    @workflow.update
    def decide(self, decision: HumanDecision) -> None:
        self.pending_decision = decision
        self.state.decisions.append(decision)

    @decide.validator
    def validate_decision(self, decision: HumanDecision) -> None:
        stages = {
            WorkflowStatus.WAITING_SYNTHESIS: 'synthesis',
            WorkflowStatus.WAITING_DRAFT: 'draft',
            WorkflowStatus.WAITING_PUBLICATION: 'publication',
        }
        stage = stages.get(self.state.status)
        if stage != decision.stage or self.pending_decision is not None:
            raise ValueError('Cette étape ne peut pas recevoir cette décision')
        artifact = self.state.synthesis if stage == 'synthesis' else self.state.draft
        if artifact is None or artifact.version != decision.version:
            raise ValueError('Version périmée : relire le contenu courant')

    async def wait_for_decision(self, status: WorkflowStatus, request: ResearchRequest) -> HumanDecision | None:
        self.pending_decision = None
        self.state.status = status
        try:
            await workflow.wait_condition(
                lambda: self.pending_decision is not None,
                timeout=timedelta(hours=request.human_timeout_hours),
            )
        except TimeoutError:
            self.state.status = WorkflowStatus.EXPIRED
            self.state.issues = ['Délai de validation humaine dépassé']
            return None
        return self.pending_decision

    async def create_publication(self, request: ResearchRequest, preferences: EditorialPreferences) -> str:
        feedback = ''
        while self.state.editorial_attempts < request.max_editorial_attempts:
            if self.state.llm_calls + 2 > request.max_llm_calls:
                self.state.issues = ['Budget des appels LLM atteint']
                return 'limit'
            self.state.editorial_attempts += 1
            self.state.status = WorkflowStatus.WRITING
            self.state.llm_calls += 1
            self.state.draft = await self.activity('write_draft', WritingInput(
                synthesis=self.state.synthesis, preferences=preferences,
                version=self.state.editorial_attempts, feedback=feedback,
            ), PublicationDraft)
            self.state.llm_calls += 1
            check = await self.activity('verify_claims', FactCheckInput(
                synthesis=SynthesisInput(
                    question=request.question, sources=self.state.synthesis.documents,
                    language=request.language,
                ), text=self.state.draft.content,
            ), FactCheckReport)
            if not check.sufficient:
                feedback = '; '.join(check.issues)
                self.state.issues = check.issues
                continue
            self.state.issues = []
            decision = await self.wait_for_decision(WorkflowStatus.WAITING_DRAFT, request)
            if decision is None:
                return 'expired'
            if decision.action == 'revise_data':
                return 'research'
            if decision.action == 'revise_style':
                feedback = decision.feedback
                if decision.preferences:
                    preferences = decision.preferences
                continue
            if decision.action == 'finish':
                return 'finish'
            authorization = await self.wait_for_decision(WorkflowStatus.WAITING_PUBLICATION, request)
            if authorization is None:
                return 'expired'
            if authorization.action == 'finish':
                return 'finish'
            self.state.status = WorkflowStatus.PUBLISHING
            command = PublicationCommand(
                publication_id=f'{workflow.info().workflow_id}:draft:{self.state.draft.version}',
                draft=self.state.draft, approved_version=authorization.version, authorized=True,
            )
            # Une publication externe ne doit pas être réémise automatiquement.
            self.state.receipt = await workflow.execute_activity(
                'publish_draft', command, result_type=PublicationReceipt,
                start_to_close_timeout=timedelta(minutes=2),
                schedule_to_close_timeout=timedelta(minutes=3),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
            if self.state.receipt.status != 'published':
                self.state.issues = [self.state.receipt.detail or 'Vérifier le résultat sur la plateforme avant toute nouvelle publication']
                return 'limit'
            return 'finish'
        self.state.issues = ['Limite des révisions éditoriales atteinte']
        return 'limit'

    @workflow.run
    async def run(self, request: ResearchRequest) -> WorkflowSnapshot:
        feedback = ''
        try:
            while await self.research(request, feedback):
                decision = await self.wait_for_decision(WorkflowStatus.WAITING_SYNTHESIS, request)
                if decision is None:
                    return self.state
                if decision.action == 'finish':
                    self.state.status = WorkflowStatus.COMPLETED
                    return self.state
                if decision.action == 'revise_data':
                    feedback = decision.feedback
                    continue
                result = await self.create_publication(request, decision.preferences)
                if result == 'research':
                    feedback = self.state.decisions[-1].feedback
                    continue
                if result == 'finish':
                    self.state.status = WorkflowStatus.COMPLETED
                elif result != 'expired':
                    self.state.status = WorkflowStatus.NEEDS_INPUT
                return self.state
        except ActivityError:
            self.state.status = WorkflowStatus.FAILED
            self.state.issues = ['Échec d’une activité ; consulter les événements Temporal et la configuration des services']
        return self.state
