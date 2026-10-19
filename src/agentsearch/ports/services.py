"""Interfaces remplaçables des fournisseurs externes."""

from typing import Protocol

from agentsearch.domain.models import PublicationCommand, PublicationDraft, PublicationReceipt, SearchResult


class SearchProvider(Protocol):
    def search(self, question: str) -> list[SearchResult]: ...


class DocumentFetcher(Protocol):
    def fetch(self, url: str) -> str: ...


class LanguageModel(Protocol):
    def complete(self, system: str, user: str, *, json_output: bool = False) -> str: ...


class Publisher(Protocol):
    def publish(self, draft: PublicationDraft) -> PublicationReceipt: ...


class PublicationStore(Protocol):
    def reserve(self, command: PublicationCommand) -> PublicationReceipt | None: ...
    def record(self, command: PublicationCommand, receipt: PublicationReceipt) -> None: ...
