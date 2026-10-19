import json
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from agentsearch.domain.models import PublicationDraft
from agentsearch.infrastructure.mcp_publisher import MCPPublisher


@pytest.mark.parametrize('structured', [True, False])
def test_mcp_explicit_tool_and_receipt(monkeypatch, structured):
    seen = []
    payload = {'platform': 'facebook', 'remote_id': 'post-123', 'status': 'published'}

    @asynccontextmanager
    async def transport(url):
        assert url == 'http://localhost:8000/mcp'
        yield (None, None, None)

    class Session:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def initialize(self):
            pass
        async def call_tool(self, name, arguments, **kwargs):
            seen.append((name, arguments))
            return SimpleNamespace(isError=False, structuredContent=payload if structured else None,
                                   content=[SimpleNamespace(type='text', text=json.dumps(payload))])

    monkeypatch.setattr('mcp.ClientSession', Session)
    monkeypatch.setattr('mcp.client.streamable_http.streamable_http_client', transport)
    publisher = MCPPublisher('http://localhost:8000/mcp', 'publish_post', 'task:draft:2')
    draft = PublicationDraft(version=2, synthesis_version=1, content='Publication approuvée',
                             platform='facebook', tone='informatif', destination='page-123')
    receipt = publisher.publish(draft)
    assert receipt.remote_id == 'post-123'
    assert seen == [('publish_post', {'publication_id': 'task:draft:2', 'platform': 'facebook',
                                     'destination': 'page-123', 'content': draft.content})]


def test_remote_mcp_requires_https():
    with pytest.raises(ValueError, match='HTTPS'):
        MCPPublisher('http://remote.example/mcp', 'publish_post', 'task')
