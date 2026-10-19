
import httpx
import pytest

from agentsearch import llm
from agentsearch.schema.schema import SearchResult, SynthesisInput, VerificationInput
from agentsearch.tools import scraper
from agentsearch.tools.filter_sources import FilterSourcesInput, filter_sources
from agentsearch.tools.url_security import UnsafeURLError, resolve_public_address, validate_url
from agentsearch.tools.verify_content import verify_content


@pytest.mark.parametrize('url', [
    'http://127.0.0.1', 'http://192.168.1.1', 'http://[::1]',
    'http://localhost', 'https://user:secret@example.com', 'file:///etc/passwd',
])
def test_unsafe_urls(url):
    with pytest.raises(UnsafeURLError):
        validate_url(url)


def test_dns_rejects_private_address(monkeypatch):
    monkeypatch.setattr('socket.getaddrinfo', lambda *a, **k: [(2, 1, 6, '', ('10.0.0.1', 443))])
    with pytest.raises(UnsafeURLError):
        resolve_public_address('https://example.com')


def test_redirect_is_validated():
    def respond(request):
        return httpx.Response(302, headers={'location': 'http://127.0.0.1/'})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(UnsafeURLError):
            scraper.fetch_html('https://example.com', client)


def test_research_to_synthesis_without_external_services(monkeypatch):
    source = SearchResult(title='Applications des agents IA', url='https://example.com/a', snippet='Agents IA')
    selected = filter_sources(FilterSourcesInput(question='Agents IA', sources=[source]))
    assert selected == [source]
    text = 'Les agents IA permettent aux entreprises de rechercher des informations utiles. ' * 35
    monkeypatch.setattr(scraper, 'fetch_html', lambda url: f'<html><body><article><p>{text}</p></article></body></html>')
    document = scraper.extract_content(source)
    report = verify_content(VerificationInput(
        question='Agents IA', documents=[document], min_documents=1, min_domains=1,
    ))
    assert report.sufficient
    captured = {}

    class FakeModel:
        def complete(self, system, user, **kwargs):
            captured['prompt'] = user
            return 'Synthèse [1]'

    monkeypatch.setattr(llm, 'GroqLanguageModel', FakeModel)
    result = llm.ask_llm(SynthesisInput(question='Agents IA', sources=report.accepted_documents))
    assert result == 'Synthèse [1]'
    assert text.strip()[:100] in captured['prompt']
    assert str(source.url) in captured['prompt']


def test_connection_uses_validated_ip_and_original_tls_hostname(monkeypatch):
    monkeypatch.setattr(scraper, 'resolve_public_address', lambda url: '93.184.216.34')
    seen = []
    class InnerTransport:
        def handle_request(self, request):
            seen.append(request)
            return httpx.Response(200, headers={'content-type': 'text/html'}, text='<html>Article</html>')
        def close(self):
            pass
    transport = scraper.PublicWebTransport()
    transport.transport.close()
    transport.transport = InnerTransport()
    with httpx.Client(transport=transport) as client:
        assert 'Article' in scraper.fetch_html('https://example.com/article', client)
    assert seen[0].url.host == '93.184.216.34'
    assert seen[0].headers['host'] == 'example.com'
    assert seen[0].extensions['sni_hostname'] == 'example.com'


def test_mixed_public_and_private_dns_is_rejected(monkeypatch):
    monkeypatch.setattr('socket.getaddrinfo', lambda *a, **k: [
        (2, 1, 6, '', ('93.184.216.34', 443)), (2, 1, 6, '', ('127.0.0.1', 443)),
    ])
    with pytest.raises(UnsafeURLError):
        resolve_public_address('https://example.com')


def test_scraping_size_limit():
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(
        200, content=b'x' * (scraper.MAX_BYTES + 1), headers={'content-type': 'text/html'},
    ))) as client:
        with pytest.raises(ValueError, match='volumineuse'):
            scraper.fetch_html('https://example.com', client)
