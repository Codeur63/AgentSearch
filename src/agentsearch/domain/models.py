"""Contrats métier indépendants de Temporal et des fournisseurs externes."""

from datetime import date, datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class SearchResult(Model):
    title: str
    url: HttpUrl
    snippet: str = ''


class ExtractedDocument(Model):
    url: HttpUrl
    title: str
    content: str
    published_at: date | None = None
    word_count: int = Field(ge=0)
    collected_at: datetime | None = None


class SynthesisInput(Model):
    question: str
    sources: list[ExtractedDocument]
    language: str = 'fr'
    feedback: str = ''


class VerificationInput(Model):
    question: str
    documents: list[ExtractedDocument]
    min_words_per_document: int = Field(default=100, ge=1)
    min_total_words: int = Field(default=300, ge=1)
    min_documents: int = Field(default=2, ge=1)
    min_domains: int = Field(default=2, ge=1)
    min_relevance: float = Field(default=0.15, ge=0, le=1)
    require_freshness: bool = False
    max_age_days: int = Field(default=365, ge=0)
    reference_date: date | None = None


class DocumentAssessment(Model):
    url: HttpUrl
    accepted: bool
    relevance_score: float = Field(ge=0, le=1)
    word_count: int = Field(ge=0)
    reasons: list[str] = Field(default_factory=list)


class VerificationResult(Model):
    sufficient: bool
    accepted_documents: list[ExtractedDocument]
    assessments: list[DocumentAssessment]
    reasons: list[str] = Field(default_factory=list)
    total_words: int = Field(ge=0)
    unique_domains: int = Field(ge=0)


class ResearchRequest(Model):
    question: str = Field(min_length=3, max_length=2000)
    language: str = 'fr'
    reference_date: date
    require_freshness: bool = False
    max_age_days: int = Field(default=365, ge=0, le=3650)
    allowed_domains: list[str] = Field(default_factory=list)
    max_sources: int = Field(default=5, ge=2, le=10)
    max_research_attempts: int = Field(default=3, ge=1, le=5)
    max_editorial_attempts: int = Field(default=3, ge=1, le=5)
    max_llm_calls: int = Field(default=12, ge=2, le=30)
    human_timeout_hours: int = Field(default=72, ge=1, le=720)


class Evidence(Model):
    source_id: int = Field(ge=1)
    quote: str = Field(min_length=10, max_length=2000)


class Claim(Model):
    text: str = Field(min_length=1, max_length=3000)
    status: Literal['supported', 'uncertain', 'contradicted']
    evidence: list[Evidence] = Field(default_factory=list, max_length=5)


class FactCheckInput(Model):
    synthesis: SynthesisInput
    text: str


class FactCheckReport(Model):
    sufficient: bool
    claims: list[Claim] = Field(default_factory=list, max_length=30)
    issues: list[str] = Field(default_factory=list, max_length=20)
    follow_up_queries: list[str] = Field(default_factory=list, max_length=3)


class Synthesis(Model):
    version: int = Field(ge=1)
    text: str
    documents: list[ExtractedDocument]
    verification: FactCheckReport


class EditorialPreferences(Model):
    tone: str = Field(default='informatif', min_length=1, max_length=200)
    platform: str = Field(default='linkedin', pattern=r'^[a-z][a-z0-9_-]{1,39}$')
    instructions: str = Field(default='', max_length=2000)
    destination: str = Field(default='', max_length=300)


class WritingInput(Model):
    synthesis: Synthesis
    preferences: EditorialPreferences
    version: int = Field(ge=1)
    feedback: str = ''


class PublicationDraft(Model):
    version: int = Field(ge=1)
    synthesis_version: int = Field(ge=1)
    content: str = Field(min_length=1, max_length=10000)
    platform: str
    tone: str
    destination: str = ''


class HumanDecision(Model):
    stage: Literal['synthesis', 'draft', 'publication']
    version: int = Field(ge=1)
    action: Literal['approve', 'revise_data', 'revise_style', 'publish', 'finish']
    feedback: str = Field(default='', max_length=2000)
    preferences: EditorialPreferences | None = None

    @model_validator(mode='after')
    def valid_action(self):
        allowed = {
            'synthesis': {'approve', 'revise_data', 'finish'},
            'draft': {'approve', 'revise_data', 'revise_style', 'finish'},
            'publication': {'publish', 'finish'},
        }
        if self.action not in allowed[self.stage]:
            raise ValueError('Action incompatible avec cette étape')
        if self.action.startswith('revise') and not self.feedback:
            raise ValueError('Un commentaire est nécessaire pour une révision')
        if self.stage == 'synthesis' and self.action == 'approve' and self.preferences is None:
            raise ValueError('Le ton et la plateforme sont nécessaires')
        return self


class PublicationCommand(Model):
    publication_id: str = Field(min_length=1, max_length=200)
    draft: PublicationDraft
    approved_version: int = Field(ge=1)
    authorized: bool = False

    @model_validator(mode='after')
    def approved_content(self):
        if not self.authorized or self.approved_version != self.draft.version:
            raise ValueError('Publication non autorisée pour cette version')
        return self


class PublicationReceipt(Model):
    platform: str
    remote_id: str
    url: str | None = None
    status: Literal['published', 'unknown', 'failed']
    detail: str = ''


class WorkflowStatus(str, Enum):
    CREATED = 'CREATED'
    RESEARCHING = 'RESEARCHING'
    VERIFY = 'VERIFY'
    WAITING_SYNTHESIS = 'WAITING_SYNTHESIS'
    WRITING = 'WRITING'
    WAITING_DRAFT = 'WAITING_DRAFT'
    WAITING_PUBLICATION = 'WAITING_PUBLICATION'
    PUBLISHING = 'PUBLISHING'
    COMPLETED = 'COMPLETED'
    NEEDS_INPUT = 'NEEDS_INPUT'
    EXPIRED = 'EXPIRED'
    FAILED = 'FAILED'


class WorkflowSnapshot(Model):
    status: WorkflowStatus = WorkflowStatus.CREATED
    research_attempts: int = 0
    editorial_attempts: int = 0
    llm_calls: int = 0
    synthesis: Synthesis | None = None
    draft: PublicationDraft | None = None
    receipt: PublicationReceipt | None = None
    decisions: list[HumanDecision] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)


class State(Model):
    """Compatibilité avec l'ancien état ; le workflow utilise WorkflowSnapshot."""
    task_id: str
    status: WorkflowStatus = WorkflowStatus.CREATED
    question: str
    language: str = 'fr'
    research: list[str] = Field(default_factory=list)
    sources: list[SearchResult] = Field(default_factory=list)
    content: str | None = None
    date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
