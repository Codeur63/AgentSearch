"""Adaptateur explicite d'un outil MCP de publication configuré par l'opérateur."""

import asyncio
import json
from urllib.parse import urlsplit

from agentsearch.domain.models import PublicationDraft, PublicationReceipt


class MCPPublisher:
    def __init__(self, url: str, tool: str, publication_id: str) -> None:
        parsed = urlsplit(url)
        if (parsed.scheme != 'https' and not (
            parsed.scheme == 'http' and parsed.hostname in {'127.0.0.1', 'localhost', '::1'}
        )) or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('URL MCP HTTPS requise (HTTP autorisé uniquement en local)')
        if not tool:
            raise ValueError('Configurer MCP_PUBLISH_TOOL')
        self.url, self.tool, self.publication_id = url, tool, publication_id

    def validate(self, draft: PublicationDraft) -> None:
        if not draft.destination:
            raise ValueError('Une destination explicite est requise pour MCP')

    async def _publish(self, draft: PublicationDraft) -> PublicationReceipt:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        async with streamable_http_client(self.url) as streams:
            async with ClientSession(streams[0], streams[1], read_timeout_seconds=30) as session:
                await session.initialize()
                result = await session.call_tool(self.tool, {
                    'publication_id': self.publication_id, 'platform': draft.platform,
                    'destination': draft.destination, 'content': draft.content,
                }, read_timeout_seconds=30)
        if getattr(result, 'isError', False):
            raise ValueError('Erreur de l’outil MCP ; résultat externe à contrôler')
        payload = getattr(result, 'structuredContent', None)
        if payload is None:
            text = next((item.text for item in result.content if item.type == 'text'), '')
            payload = json.loads(text)
        receipt = PublicationReceipt.model_validate(payload)
        if receipt.platform != draft.platform or (receipt.status == 'published' and not receipt.remote_id):
            raise ValueError('Accusé MCP incompatible avec la publication demandée')
        return receipt

    def publish(self, draft: PublicationDraft) -> PublicationReceipt:
        self.validate(draft)
        return asyncio.run(self._publish(draft))
