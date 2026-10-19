
from datetime import date
from urllib.parse import urlsplit

from temporalio import activity

from agentsearch.schema.schema import (
    VerificationInput,
    VerificationResult,
    DocumentAssessment,
)

from agentsearch.tools.filter_sources import normalize_text


def document_relevance(question: str, title: str, content: str) -> float:
    """Calcule une pertinence lexicale indicative."""

    query_words = normalize_text(question)

    if not query_words:
        return 0.0

    title_words = normalize_text(title)

    # On borne le texte analysé pour maîtriser le calcul.
    content_words = normalize_text(content[:15000])

    title_score = len(query_words & title_words) / len(query_words)
    content_score = len(query_words & content_words) / len(query_words)

    return round(
        0.3 * title_score + 0.7 * content_score,
        4,
    )


@activity.defn(name="verify_content")
def verify_content(
    data: VerificationInput,
) -> VerificationResult:
    """Évalue l'exploitabilité documentaire des articles."""

    today = data.reference_date or date.today()

    accepted_documents = []
    assessments = []
    seen_urls = set()

    for document in data.documents:
        reasons = []
        url = str(document.url)

        # 1. Éviter de compter deux fois la même URL.
        if url in seen_urls:
            reasons.append("Document en doublon")
        else:
            seen_urls.add(url)

        # 2. Vérifier le volume réellement présent.
        content = document.content.strip()
        word_count = len(content.split())

        if word_count < data.min_words_per_document:
            reasons.append("Contenu trop court")

        # 3. Évaluer la pertinence lexicale.
        score = document_relevance(
            data.question,
            document.title,
            content,
        )

        if score < data.min_relevance:
            reasons.append("Pertinence lexicale insuffisante")

        # 4. Vérifier la fraîcheur si nécessaire.
        if data.require_freshness:
            if document.published_at is None:
                reasons.append(
                    "Date inconnue : fraîcheur non vérifiable"
                )
            else:
                age = (today - document.published_at).days

                if age < 0:
                    reasons.append(
                        "Date de publication future à vérifier"
                    )
                elif age > data.max_age_days:
                    reasons.append("Publication trop ancienne")

        # 5. Décision individuelle.
        accepted = len(reasons) == 0

        assessments.append(
            DocumentAssessment(
                url=document.url,
                accepted=accepted,
                relevance_score=score,
                word_count=word_count,
                reasons=reasons,
            )
        )

        if accepted:
            accepted_documents.append(document)

    # 6. Calculer les indicateurs globaux.
    total_words = sum(
        len(doc.content.split())
        for doc in accepted_documents
    )

    domains = {
        urlsplit(str(doc.url)).hostname
        for doc in accepted_documents
    }

    unique_domains = len(domains - {None})

    # 7. Vérifier la suffisance globale.
    global_reasons = []

    if len(accepted_documents) < data.min_documents:
        global_reasons.append(
            "Nombre de documents exploitables insuffisant"
        )

    if total_words < data.min_total_words:
        global_reasons.append(
            "Volume documentaire insuffisant"
        )

    if unique_domains < data.min_domains:
        global_reasons.append(
            "Diversité des domaines insuffisante"
        )

    return VerificationResult(
        sufficient=len(global_reasons) == 0,
        accepted_documents=accepted_documents,
        assessments=assessments,
        reasons=global_reasons,
        total_words=total_words,
        unique_domains=unique_domains,
    )
