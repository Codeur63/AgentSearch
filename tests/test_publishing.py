from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from agentsearch.application.publishing import publish_once
from agentsearch.infrastructure.publication_store import PublicationLedger
from agentsearch.domain.models import PublicationCommand, PublicationDraft, PublicationReceipt
from agentsearch.publishing.linkedin import LinkedInPublisher


def command():
    return PublicationCommand(
        publication_id='workflow-1:draft:1', approved_version=1, authorized=True,
        draft=PublicationDraft(version=1, synthesis_version=1, content='Publication validée [1]',
                               platform='linkedin', tone='informatif', destination='urn:li:person:123'),
    )


class FakePublisher:
    def __init__(self, fail=False):
        self.calls = 0
        self.fail = fail
    def publish(self, draft):
        self.calls += 1
        if self.fail:
            raise TimeoutError('Publication peut-être créée')
        return PublicationReceipt(platform='linkedin', status='published', remote_id='urn:li:share:123')


def test_duplicate_publication_returns_existing_receipt(tmp_path):
    ledger = PublicationLedger(tmp_path / 'ledger.sqlite3')
    publisher = FakePublisher()
    first = publish_once(command(), publisher, ledger)
    second = publish_once(command(), publisher, PublicationLedger(ledger.path))
    assert first == second
    assert publisher.calls == 1


def test_timeout_never_reposts_automatically(tmp_path):
    ledger = PublicationLedger(tmp_path / 'ledger.sqlite3')
    publisher = FakePublisher(fail=True)
    assert publish_once(command(), publisher, ledger).status == 'unknown'
    assert publish_once(command(), publisher, ledger).status == 'unknown'
    assert publisher.calls == 1


def test_crash_after_reservation_is_not_reissued(tmp_path):
    ledger = PublicationLedger(tmp_path / 'ledger.sqlite3')
    ledger.reserve(command())
    publisher = FakePublisher()
    assert publish_once(command(), publisher, ledger).status == 'unknown'
    assert publisher.calls == 0


def test_same_identifier_cannot_publish_modified_content(tmp_path):
    ledger = PublicationLedger(tmp_path / 'ledger.sqlite3')
    publish_once(command(), FakePublisher(), ledger)
    changed = command()
    changed.draft.content = 'Autre contenu'
    with pytest.raises(ValueError, match='autre contenu'):
        publish_once(changed, FakePublisher(), ledger)


def test_concurrent_workers_only_emit_once(tmp_path):
    ledger = PublicationLedger(tmp_path / 'ledger.sqlite3')
    publisher = FakePublisher()
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _: publish_once(command(), publisher, ledger), range(4)))
    assert publisher.calls == 1
    assert any(result.status == 'published' for result in results)


def test_linkedin_request_and_receipt():
    requests = []
    def respond(request):
        requests.append(request)
        return httpx.Response(201, headers={'x-restli-id': 'urn:li:share:123'})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        publisher = LinkedInPublisher('FAKE_TEST_TOKEN', 'urn:li:person:123', '202606', client)
        receipt = publisher.publish(command().draft)
        assert receipt.status == 'published'
        assert requests[0].url == 'https://api.linkedin.com/rest/posts'
        assert requests[0].headers['LinkedIn-Version'] == '202606'
        assert b'urn:li:person:123' in requests[0].content
        draft = command().draft
        draft.destination = 'urn:li:person:other'
        with pytest.raises(ValueError, match='destination approuvée'):
            publisher.publish(draft)
        assert len(requests) == 1


def test_unknown_backend_cannot_fall_back_to_linkedin(monkeypatch):
    from agentsearch.orchestration.activities import publish_draft
    monkeypatch.setenv('PUBLISH_BACKEND', 'invalid-backend')
    receipt = publish_draft(command())
    assert receipt.status == 'failed'
