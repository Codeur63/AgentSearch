import pytest

from agentsearch.application.writing import write_draft
from agentsearch.domain.models import (
    EditorialPreferences, ExtractedDocument, FactCheckReport, Synthesis, WritingInput,
)


class FakeModel:
    def __init__(self, output):
        self.output = output
    def complete(self, system, user, **kwargs):
        self.prompt = user
        return self.output


def writing_input():
    doc = ExtractedDocument(url='https://example.com/a', title='Agents IA', content='Texte', word_count=1)
    return WritingInput(synthesis=Synthesis(version=1, text='Les agents IA [1]', documents=[doc],
                                          verification=FactCheckReport(sufficient=True)),
                        preferences=EditorialPreferences(tone='pédagogique', destination='urn:li:person:123'),
                        version=2, feedback='Plus court')


def test_tone_feedback_and_sources_preserved():
    model = FakeModel('Les agents IA [1].')
    draft = write_draft(writing_input(), model)
    assert 'pédagogique' in model.prompt
    assert 'Plus court' in model.prompt
    assert draft.content.endswith('[1] https://example.com/a')
    assert draft.version == 2 and draft.synthesis_version == 1
    assert draft.destination == 'urn:li:person:123'


def test_invented_reference_rejected():
    with pytest.raises(ValueError, match='sources valides'):
        write_draft(writing_input(), FakeModel('Une affirmation [9]'))


def test_linkedin_length_checked_after_references():
    with pytest.raises(ValueError, match='trop long'):
        write_draft(writing_input(), FakeModel('x' * 3000 + ' [1]'))
