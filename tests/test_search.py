from agentsearch.tools import search
from agentsearch.infrastructure import search as provider


def test_search_fallback_and_invalid_result(monkeypatch):
    calls = []

    class FakeDDGS:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def text(self, question, **kwargs):
            calls.append(kwargs["backend"])
            if len(calls) == 1:
                raise RuntimeError("Moteur indisponible")
            return [{"title": "Agents IA", "href": "https://example.com/a", "body": "Agents IA"},
                    {"title": "Invalide", "href": "invalid"}]

    monkeypatch.setattr(provider, "DDGS", FakeDDGS)
    results = search.search_web("Agents IA")
    assert len(results) == 1
    assert str(results[0].url) == "https://example.com/a"
    assert len(calls) == 2
