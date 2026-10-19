import json
from datetime import date

from agentsearch.application.research import make_request
from agentsearch.application.verification import verify_claims
from agentsearch.domain.models import ExtractedDocument, FactCheckInput, SynthesisInput


class FakeModel:
    def __init__(self, quote, source_id=1):
        self.quote = quote
        self.source_id = source_id

    def complete(self, *args, **kwargs):
        return json.dumps({
            'sufficient': True,
            'claims': [{'text': 'Une affirmation', 'status': 'supported',
                        'evidence': [{'source_id': self.source_id, 'quote': self.quote}]}],
            'issues': [], 'follow_up_queries': [],
        })


def data():
    doc = ExtractedDocument(url='https://example.com', title='Agents IA',
                            content='Les agents IA utilisent des outils.', word_count=7)
    return FactCheckInput(synthesis=SynthesisInput(question='Agents IA', sources=[doc]), text='Les agents utilisent des outils [1].')


def test_evidence_must_exist_in_source():
    report = verify_claims(data(), FakeModel('Citation entièrement inventée'))
    assert not report.sufficient
    assert 'Preuve absente' in report.issues[0]


def test_valid_evidence():
    assert verify_claims(data(), FakeModel('Les agents IA utilisent des outils.')).sufficient


def test_nonexistent_reference():
    assert not verify_claims(data(), FakeModel('Les agents IA utilisent des outils.', 2)).sufficient


def test_today_uses_explicit_date():
    request = make_request("Quelles sont les actualités de l'IA aujourd’hui ?", date(2026, 10, 19))
    assert request.require_freshness
    assert request.max_age_days == 0
    assert request.reference_date == date(2026, 10, 19)
