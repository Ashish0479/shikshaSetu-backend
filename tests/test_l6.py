from app.database.mongodb import db_client
from app.models.l6_schemas import L6ReviewRequest
from app.services.intent_router import IntentRouter
from app.services.rag_service import RAGService


class FakeGemini:
    def generate(self, question, context, language):
        assert "secret" not in context
        return f"grounded:{language}:{question}"


def test_intent_router_covers_operational_categories_and_entities():
    router = IntentRouter()
    assert router.route("Why is school S12 high risk?", "").name == "L4_EXPLANATION"
    assert router.route("Compare scenario ABC", None).entities["scenario_id"] == "ABC"
    assert router.route("What is the policy constraint?", None).name == "POLICY_QUERY"
    assert router.route("इस स्कूल में गणित की कमी क्यों है?", None).language == "hi"
    assert router.route("tell me a joke", None).name == "UNKNOWN_OR_UNSUPPORTED"


def test_rag_uses_mocked_provider_and_returns_provenance():
    class Retrieval:
        def retrieve(self, question, intent, dataset_id):
            return {
                "evidence": [{"source_type": "analysis", "source_id": "d:l3", "title": "L3", "excerpt": "shortage=2", "metadata": {}}],
                "limitations": [],
                "provenance": ["L3AnalysisService.analyze_record_sets(clean_records)"],
                "dataset_id": dataset_id,
            }

    response = RAGService(retrieval=Retrieval(), gemini=FakeGemini()).answer("Why is there a shortage?", "d")
    assert response.provider_status == "available"
    assert response.evidence[0].source_id == "d:l3"
    assert response.calculation_provenance


def test_gemini_unavailable_is_explicit_and_does_not_invent_answer():
    class Unavailable:
        def generate(self, question, context, language):
            from app.services.gemini_service import GeminiUnavailable
            raise GeminiUnavailable("not configured")

    class Retrieval:
        def retrieve(self, question, intent, dataset_id):
            return {"evidence": [{"source_type": "document", "source_id": "README.md", "title": "README", "excerpt": "methodology", "metadata": {}}], "limitations": [], "provenance": [], "dataset_id": dataset_id}

    response = RAGService(retrieval=Retrieval(), gemini=Unavailable()).answer("What is the methodology?", None)
    assert response.provider_status == "unavailable"
    assert "unavailable" in response.answer.lower()


def test_override_requires_reason_and_review_events_are_append_only():
    valid = L6ReviewRequest(decision="override", reviewer_id="officer-1", reason="Policy exception")
    assert valid.decision == "OVERRIDE"
    try:
        L6ReviewRequest(decision="OVERRIDE", reviewer_id="officer-1")
        assert False, "Expected validation error"
    except ValueError:
        pass

    db_client._in_memory_store["l5_scenarios"]["l6-test"] = {"scenario_id": "l6-test", "status": "FEASIBLE"}
    db_client._in_memory_store["l5_review_events"].pop("l6-test", None)
    db_client.append_l5_review_event("l6-test", {"decision": "ACCEPT"})
    db_client.append_l5_review_event("l6-test", {"decision": "REJECT"})
    assert [event["decision"] for event in db_client.get_l5_review_events("l6-test")] == ["ACCEPT", "REJECT"]
