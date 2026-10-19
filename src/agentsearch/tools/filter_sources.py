
import logging
import re
import unicodedata

from urllib.parse import urlsplit

from pydantic import BaseModel, Field
from temporalio import activity

from agentsearch.schema.schema import SearchResult
from agentsearch.tools.url_security import UnsafeURLError, validate_url


logger = logging.getLogger(__name__)


STOPWORDS = {
    "de", "du", "et", "le", "la", "un", "en", "au", "ce", "se", "ne", "ou", "il", "on",
    "les", "des", "une", "dans", "pour", "avec",
    "sur", "est", "sont", "que", "qui", "quoi",
    "quel", "quelle", "quelles", "quels",
    "comment", "pourquoi", "plus", "moins",
    "aux", "par", "leur", "leurs", "cette",
    "ces", "son", "ses", "nous", "vous",
    "the", "and", "for", "with", "from",
    "what", "how", "are", "this", "that",
}


class FilterSourcesInput(BaseModel):
    question: str
    sources: list[SearchResult]

    max_sources: int = Field(default=5, ge=1, le=20)
    min_score: float = Field(default=0.15, ge=0, le=1)

    allowed_domains: list[str] = Field(
        default_factory=list
    )


def normalize_text(text: str) -> set[str]:
    """Normalise une phrase en mots significatifs."""

    normalized = unicodedata.normalize("NFKD", text)

    normalized = "".join(
        char
        for char in normalized
        if not unicodedata.combining(char)
    )

    words = re.findall(
        r"[a-z0-9]+",
        normalized.lower(),
    )

    return {
        word
        for word in words
        if len(word) >= 2 and word not in STOPWORDS
    }


def relevance_score(
    question: str,
    source: SearchResult,
) -> float:
    """Calcule un score lexical compris entre 0 et 1."""

    query_words = normalize_text(question)

    if not query_words:
        return 0.0

    title_words = normalize_text(source.title)
    snippet_words = normalize_text(source.snippet)

    title_score = len(
        query_words & title_words
    ) / len(query_words)

    snippet_score = len(
        query_words & snippet_words
    ) / len(query_words)

    return round(
        0.7 * title_score + 0.3 * snippet_score,
        4,
    )


@activity.defn(name="filter_sources")
def filter_sources(
    data: FilterSourcesInput,
) -> list[SearchResult]:
    """Sélectionne les sources DDGS pertinentes et autorisées."""

    # 1. INITIALISATION
    # Tous les compteurs doivent exister avant la boucle.

    rejected_domain = 0
    rejected_relevance = 0
    rejected_duplicate = 0
    rejected_url = 0

    candidates = []
    seen_urls = set()

    allowed = {
        domain.lower().rstrip(".")
        for domain in data.allowed_domains
    }

    logger.info(
        "Filtrage de %d résultats DDGS",
        len(data.sources),
    )

    # 2. CONTRÔLE DES RÉSULTATS

    for source in data.sources:

        url = str(source.url)
        parsed = urlsplit(url)

        hostname = (
            parsed.hostname or ""
        ).lower().rstrip(".")

        # Protocole autorisé
        if parsed.scheme not in {"http", "https"}:
            rejected_url += 1
            continue

        # Identifiants intégrés interdits
        if parsed.username is not None or parsed.password is not None:
            rejected_url += 1
            continue

        # Vérifier le port
        try:
            port = parsed.port
        except ValueError:
            rejected_url += 1
            continue

        if port not in {None, 80, 443}:
            rejected_url += 1
            continue

        # Domaine explicitement autorisé
        if allowed and hostname not in allowed:
            rejected_domain += 1
            continue

        try:
            validate_url(url)
        except UnsafeURLError:
            rejected_url += 1
            continue

        # Doublons
        normalized_url = url.rstrip("/")

        if normalized_url in seen_urls:
            rejected_duplicate += 1
            continue

        seen_urls.add(normalized_url)

        # Pertinence
        score = relevance_score(
            data.question,
            source,
        )

        if score < data.min_score:
            rejected_relevance += 1
            continue

        candidates.append(
            (score, hostname, source)
        )

    # 3. CLASSER PAR PERTINENCE

    candidates.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    # 4. FAVORISER LA DIVERSITÉ DES DOMAINES

    selected = []
    deferred = []
    used_domains = set()

    for score, hostname, source in candidates:

        if hostname in used_domains:
            deferred.append(source)
        else:
            selected.append(source)
            used_domains.add(hostname)

        if len(selected) >= data.max_sources:
            break

    # 5. COMPLÉTER AVEC LES SOURCES RESTANTES

    if len(selected) < data.max_sources:
        for source in deferred:
            selected.append(source)

            if len(selected) >= data.max_sources:
                break

    # 6. JOURNALISATION

    logger.info(
        "Filtrage terminé : %d sources retenues",
        len(selected),
    )

    logger.info(
        "Rejets : domaines=%d, pertinence=%d, "
        "doublons=%d, URLs invalides=%d",
        rejected_domain,
        rejected_relevance,
        rejected_duplicate,
        rejected_url,
    )

    for source in selected:
        logger.info(
            "Source retenue : %s | %s",
            source.title,
            source.url,
        )

    return selected
