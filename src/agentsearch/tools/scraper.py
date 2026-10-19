"""Collecte HTTP bornée, avec destination DNS figée et extraction documentaire."""

from datetime import date, datetime, timezone
from urllib.parse import urljoin

import httpx
import trafilatura
from temporalio import activity

from agentsearch.schema.schema import ExtractedDocument, SearchResult
from agentsearch.tools.url_security import resolve_public_address, validate_url

MAX_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 5


class PublicWebTransport(httpx.BaseTransport):
    """Évite une seconde résolution DNS après le contrôle de l'adresse."""

    def __init__(self) -> None:
        self.transport = httpx.HTTPTransport(trust_env=False)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        hostname = request.url.host
        ip = resolve_public_address(str(request.url))
        headers = request.headers.copy()
        headers['Host'] = request.url.netloc.decode('ascii')
        pinned = httpx.Request(
            request.method, request.url.copy_with(host=ip), headers=headers,
            stream=request.stream,
            extensions={**request.extensions, 'sni_hostname': hostname},
        )
        return self.transport.handle_request(pinned)

    def close(self) -> None:
        self.transport.close()


def fetch_html(url: str, client: httpx.Client | None = None) -> str:
    """Télécharge une page ; le client injecté est réservé aux adaptateurs/tests."""
    if client is None:
        with httpx.Client(transport=PublicWebTransport(), trust_env=False) as owned:
            return fetch_html(url, owned)
    for _ in range(MAX_REDIRECTS + 1):
        validate_url(url)
        with client.stream('GET', url, timeout=15, follow_redirects=False) as response:
            if response.is_redirect:
                location = response.headers.get('location')
                if not location:
                    raise ValueError('Redirection sans destination')
                url = urljoin(url, location)
                continue
            response.raise_for_status()
            content_type = response.headers.get('content-type', '').lower()
            if not any(t in content_type for t in ('text/html', 'application/xhtml+xml')):
                raise ValueError(f'Format non pris en charge : {content_type}')
            chunks = []
            total = 0
            for chunk in response.iter_bytes():
                total += len(chunk)
                if total > MAX_BYTES:
                    raise ValueError('Page HTML trop volumineuse')
                chunks.append(chunk)
            return b''.join(chunks).decode(response.encoding or 'utf-8', errors='replace')
    raise ValueError('Trop de redirections')


def extract_text(html: str) -> str:
    text = trafilatura.extract(html)
    if not text or not text.strip():
        raise ValueError("Aucun contenu exploitable n'a été extrait")
    return text.strip()


@activity.defn(name='extract_content')
def extract_content(source: SearchResult) -> ExtractedDocument:
    html = fetch_html(str(source.url))
    text = extract_text(html)[:30000]
    metadata = trafilatura.bare_extraction(html, url=str(source.url), with_metadata=True)
    published_at = None
    if metadata and metadata.date:
        try:
            published_at = date.fromisoformat(metadata.date[:10])
        except ValueError:
            pass
    return ExtractedDocument(
        url=source.url, title=source.title, content=text,
        published_at=published_at, word_count=len(text.split()), collected_at=datetime.now(timezone.utc),
    )
