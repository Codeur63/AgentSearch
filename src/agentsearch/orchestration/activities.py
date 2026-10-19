"""Assemblage des activités et des connecteurs aux frontières du système."""

import os
from pathlib import Path

from temporalio import activity

from agentsearch.agent.verifier import verify_synthesis
from agentsearch.agent.writer import create_draft
from agentsearch.application.publishing import publish_once
from agentsearch.infrastructure.publication_store import PublicationLedger
from agentsearch.domain.models import PublicationCommand, PublicationReceipt
from agentsearch.infrastructure.mcp_publisher import MCPPublisher
from agentsearch.llm import ask_llm
from agentsearch.publishing.linkedin import LinkedInPublisher
from agentsearch.tools.filter_sources import filter_sources
from agentsearch.tools.search import search_web
from agentsearch.tools.verify_content import verify_content


@activity.defn(name='publish_draft')
def publish_draft(command: PublicationCommand) -> PublicationReceipt:
    try:
        backend = os.getenv('PUBLISH_BACKEND', 'linkedin')
        if backend == 'mcp':
            publisher = MCPPublisher(os.getenv('MCP_SERVER_URL', ''), os.getenv('MCP_PUBLISH_TOOL', ''), command.publication_id)
        elif backend == 'linkedin' and command.draft.platform == 'linkedin':
            publisher = LinkedInPublisher(os.getenv('LINKEDIN_ACCESS_TOKEN', ''),
                                          os.getenv('LINKEDIN_AUTHOR_URN', ''), os.getenv('LINKEDIN_API_VERSION', ''))
        else:
            raise ValueError('Configurer un connecteur MCP pour cette plateforme')
        publisher.validate(command.draft)
    except ValueError as exc:
        return PublicationReceipt(platform=command.draft.platform, remote_id='', status='failed', detail=str(exc))
    ledger = PublicationLedger(Path(os.getenv('PUBLICATION_LEDGER_PATH', '.agentsearch/publications.sqlite3')))
    return publish_once(command, publisher, ledger)


MAIN_ACTIVITIES = [search_web, filter_sources, verify_content, ask_llm, verify_synthesis, create_draft, publish_draft]
