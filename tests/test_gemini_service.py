import pytest
from types import SimpleNamespace

from app.services.gemini_service import GeminiProviderError, GeminiService
from app.services.rag_service import RAGService
from google.genai.errors import ClientError, ServerError


class Response:
    text = "grounded answer"


class FakeModels:
    def __init__(self, outcomes):
        self.outcomes = iter(outcomes)
        self.calls = 0

    def generate_content(self, **kwargs):
        self.calls += 1
        outcome = next(self.outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeClient:
    def __init__(self, outcomes):
        self.models = FakeModels(outcomes)


def api_error(error_type, code):
    return error_type(code, {"error": {"code": code, "message": "test provider error"}})


def test_successful_generation_reuses_client():
    client = FakeClient([Response(), Response()])
    service = GeminiService(api_key="test", model="gemini-2.5-flash", client=client)
    assert service.generate("q", "evidence", "en") == "grounded answer"
    assert service.generate("q2", "evidence", "en") == "grounded answer"
    assert client.models.calls == 2


def test_transient_503_retries_then_succeeds(monkeypatch):
    client = FakeClient([api_error(ServerError, 503), Response()])
    service = GeminiService(api_key="test", model="gemini-2.5-flash", client=client)
    delays = []
    monkeypatch.setattr("app.services.gemini_service.time.sleep", delays.append)
    assert service.generate("q", "evidence", "en") == "grounded answer"
    assert client.models.calls == 2
    assert delays == [0.25]


def test_repeated_transient_failures_exhaust_retry_limit(monkeypatch):
    client = FakeClient([api_error(ServerError, 503)] * 3)
    service = GeminiService(api_key="test", model="gemini-2.5-flash", client=client)
    monkeypatch.setattr("app.services.gemini_service.time.sleep", lambda _: None)
    with pytest.raises(GeminiProviderError) as raised:
        service.generate("q", "evidence", "en")
    assert raised.value.category == "transient_provider"
    assert raised.value.status_code == 503
    assert client.models.calls == 3


def test_quota_and_auth_errors_are_classified(monkeypatch):
    monkeypatch.setattr("app.services.gemini_service.time.sleep", lambda _: None)
    for exception, category, retryable in [
        (api_error(ClientError, 429), "quota_or_rate_limit", True),
        (api_error(ClientError, 401), "authentication_or_permission", False),
        (api_error(ClientError, 403), "authentication_or_permission", False),
        (api_error(ClientError, 404), "model_not_found", False),
        (api_error(ClientError, 400), "invalid_request", False),
    ]:
        outcomes = [exception] * (3 if retryable else 1)
        service = GeminiService(api_key="test", model="gemini-2.5-flash", client=FakeClient(outcomes))
        with pytest.raises(GeminiProviderError) as raised:
            service.generate("q", "evidence", "en")
        assert raised.value.category == category
        assert raised.value.retryable is retryable


def test_rag_preserves_l3_evidence_when_provider_fails():
    class Retrieval:
        def retrieve(self, question, intent, dataset_id):
            assert intent.name == "L3_EXPLANATION"
            return {
                "evidence": [{"source_type": "analysis", "source_id": "dataset:l3", "title": "Layer 3 analysis", "excerpt": "S1 mathematics shortage 3", "metadata": {}}],
                "limitations": [],
                "provenance": ["L3AnalysisService.analyze_record_sets(clean_records)"],
                "dataset_id": dataset_id,
            }

    class FailedGemini:
        def generate(self, question, context, language):
            raise GeminiProviderError("quota_or_rate_limit", "Gemini quota or rate limit exceeded.", 429)

    response = RAGService(retrieval=Retrieval(), gemini=FailedGemini()).answer(
        "Which schools have the highest mathematics teacher shortages?", "dataset"
    )
    assert response.provider_error_category == "quota_or_rate_limit"
    assert response.evidence[0].source_id == "dataset:l3"
    assert "generated explanation" in response.answer
    assert "S1" not in response.answer


def test_timeout_and_network_failures_are_retryable(monkeypatch):
    monkeypatch.setattr("app.services.gemini_service.time.sleep", lambda _: None)
    for failure, category in [(TimeoutError(), "timeout"), (ConnectionError(), "network")]:
        service = GeminiService(api_key="test", model="gemini-2.5-flash", client=FakeClient([failure] * 3))
        with pytest.raises(GeminiProviderError) as raised:
            service.generate("q", "evidence", "en")
        assert raised.value.category == category
        assert raised.value.retryable is True


def test_retry_after_header_is_respected(monkeypatch):
    class RateLimitError(Exception):
        code = 429
        response = SimpleNamespace(headers={"retry-after": "1.5"})

    delays = []
    monkeypatch.setattr("app.services.gemini_service.time.sleep", delays.append)
    service = GeminiService(api_key="test", model="gemini-2.5-flash", client=FakeClient([RateLimitError()] * 3))
    with pytest.raises(GeminiProviderError):
        service.generate("q", "evidence", "en")
    assert delays == [1.5, 1.5]


def test_missing_sdk_is_classified(monkeypatch):
    import builtins

    original_import = builtins.__import__

    def missing_google(name, *args, **kwargs):
        if name == "google" or name.startswith("google."):
            raise ImportError("sdk missing")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", missing_google)
    service = GeminiService(api_key="test", model="gemini-2.5-flash")
    with pytest.raises(GeminiProviderError) as raised:
        service.generate("q", "evidence", "en")
    assert raised.value.category == "sdk_unavailable"


def test_missing_api_key_is_not_reported_as_provider_outage():
    service = GeminiService(api_key="", model="gemini-2.5-flash", client=FakeClient([]))
    with pytest.raises(Exception) as raised:
        service.generate("q", "evidence", "en")
    assert "not configured" in str(raised.value)
