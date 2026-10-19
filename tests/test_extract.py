import pytest
from agentsearch.tools.scraper import fetch_html, MAX_BYTES, extract_text
from agentsearch.tools.url_security import UnsafeURLError, validate_url
from datetime import date
from agentsearch.schema.schema import (
    SearchResult,
    ExtractedDocument,
    VerificationInput,
)
from agentsearch.tools.verify_content import verify_content
from agentsearch.tools.filter_sources import (
    FilterSourcesInput,
    filter_sources,
)


def test_html():
    import httpx
    html = "<html><body><p>Article de test</p></body></html>"
    with httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, text=html, headers={"content-type": "text/html"})
    )) as client:
        assert fetch_html("https://example.com/article", client) == html


def test_extract_text():
    html = """
    <html>
        <body>
            <main>
                <h1>Article sur les agents IA</h1>
                <p>Les agents IA peuvent rechercher des informations.</p>
                <p>Ils peuvent aussi produire des synthèses documentées.</p>
            </main>
        </body>
    </html>
    """

    resultat = extract_text(html)

    assert isinstance(resultat, str)
    assert "agents IA" in resultat    


def test_url_locale():
    with pytest.raises(UnsafeURLError):
        validate_url("http://127.0.0.1:8000")

def test_flux():
    with pytest.raises(UnsafeURLError):
        validate_url(
            "https://example.com.attacker.test/article"
        )

def test_filter_sources():

    sources = [
        SearchResult(
            title="Les agents IA et leurs applications",
            url="https://example.com/article-ia",
            snippet="Présentation des agents IA autonomes.",
        ),
        SearchResult(
            title="Recette de gâteau au chocolat",
            url="https://example.com/recette",
            snippet="Comment préparer un dessert maison.",
        ),
        SearchResult(
            title="Les agents IA et leurs applications",
            url="https://example.com/article-ia",
            snippet="Présentation des agents IA autonomes.",
        ),
    ]

    data = FilterSourcesInput(
        question="Quelles sont les applications des agents IA ?",
        sources=sources,
        max_sources=3,
        min_score=0.15,
        allowed_domains=["example.com"],
    )

    results = filter_sources(data)

    assert len(results) == 1
    assert results[0].title == (
        "Les agents IA et leurs applications"
    )        

def make_document(url: str, content: str, published_at=None):
    return ExtractedDocument(
        url=url,
        title="Applications des agents IA",
        content=content,
        published_at=published_at,
        word_count=len(content.split()),
    )


def test_documents_suffisants():
    texte = (
        "Les agents IA peuvent automatiser des tâches complexes. "
        "Ils utilisent des outils pour rechercher et analyser des données. "
    ) * 20

    documents = [
        make_document("https://example.com/a", texte),
        make_document("https://example.org/b", texte),
    ]

    result = verify_content(
        VerificationInput(
            question="Quelles sont les applications des agents IA ?",
            documents=documents,
        )
    )

    assert result.sufficient is True
    assert len(result.accepted_documents) == 2
    assert result.unique_domains == 2



def test_document_hors_sujet():
    texte = (
        "Cette recette explique comment préparer "
        "un gâteau au chocolat avec du beurre. "
    ) * 20

    document = ExtractedDocument(
        url="https://example.com/recette",
        title="Recette de gâteau au chocolat",
        content=texte,
        published_at=None,
        word_count=len(texte.split()),
    )

    result = verify_content(
        VerificationInput(
            question="Applications des agents IA",
            documents=[document],
        )
    )

    assert result.sufficient is False
    assert result.assessments[0].accepted is False
    assert "Pertinence lexicale insuffisante" in result.assessments[0].reasons


def test_document_trop_ancien():
    texte = "Les agents IA sont utilisés dans les entreprises. " * 30

    document = make_document(
        "https://example.com/ancien",
        texte,
        published_at=date(2020, 1, 1),
    )

    result = verify_content(
        VerificationInput(
            question="Utilisation des agents IA",
            documents=[document],
            require_freshness=True,
            max_age_days=365,
            reference_date=date(2026, 10, 16),
        )
    )

    assert result.assessments[0].accepted is False
    assert "Publication trop ancienne" in result.assessments[0].reasons
