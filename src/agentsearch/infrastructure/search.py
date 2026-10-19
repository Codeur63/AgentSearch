import logging
from ddgs import DDGS
from pydantic import ValidationError
from agentsearch.domain.models import SearchResult

logger = logging.getLogger(__name__)

SEARCH_BACKENDS = (
    "duckduckgo",
    "bing",
    "mojeek",
    "wikipedia",
)


class DDGSSearchProvider:
    def search(self, question: str) -> list[SearchResult]:
        logger.info("Recherche web : %s", question)

        errors = []

        for backend in SEARCH_BACKENDS:

            try:
                logger.info(
                    "Tentative avec le moteur : %s",
                    backend,
                )

                with DDGS(timeout=12) as ddgs:
                    raw_results = ddgs.text(
                        question,
                        max_results=10,
                        backend=backend,
                    )

                sources = []

                for result in raw_results:
                    try:
                        source = SearchResult(
                            title=result["title"],
                            url=result["href"],
                            snippet=result.get("body", ""),
                        )
                        sources.append(source)

                    except (ValidationError, KeyError, TypeError):
                        logger.warning(
                            "Résultat invalide ignoré : %s",
                            backend,
                        )

                if sources:
                    logger.info(
                        "%d sources trouvées avec %s",
                        len(sources),
                        backend,
                    )
                    return sources

                logger.warning(
                    "Aucun résultat exploitable avec %s",
                    backend,
                )

            except Exception as exc:
                errors.append(f"{backend}: {exc}")
                logger.exception(
                    "Erreur inattendue avec %s",
                    backend,
                )

        if errors:
            raise RuntimeError(
                "La recherche a échoué sur un ou plusieurs "
                "moteurs sans produire de résultats : "
                + "; ".join(errors)
            )

        return []
