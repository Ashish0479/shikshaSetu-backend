from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict

from app.models.l6_schemas import L6AskResponse
from app.services.gemini_service import GeminiProviderError, GeminiService, GeminiUnavailable
from app.services.intent_router import IntentRouter
from app.services.retrieval_service import RetrievalService


class RAGService:
    def __init__(self, router=None, retrieval=None, gemini=None):
        self.router = router or IntentRouter()
        self.retrieval = retrieval or RetrievalService()
        self.gemini = gemini or GeminiService()

    def answer(self, question: str, dataset_id: str | None = None, scenario_id: str | None = None) -> L6AskResponse:
        intent = self.router.route(question, scenario_id)
        retrieved = self.retrieval.retrieve(question, intent, dataset_id)
        evidence = retrieved["evidence"]
        limitations = retrieved["limitations"]
        provider_status = "unavailable"
        provider_error_category = None
        if intent.clarification:
            answer = intent.clarification
            limitations.append("The question was not answered because a unique operational identifier was missing.")
        elif not evidence:
            answer = "I cannot provide a reliable answer because authoritative evidence is unavailable for this question."
        else:
            context = json.dumps(evidence, ensure_ascii=False, default=str)
            try:
                answer = self.gemini.generate(question, context, intent.language)
                provider_status = "available"
            except GeminiProviderError as exc:
                provider_error_category = exc.category
                answer = f"Gemini is unavailable, so no generated explanation was produced. Retrieved evidence is available for review. ({exc})"
            except GeminiUnavailable as exc:
                answer = f"Gemini is unavailable, so no generated explanation was produced. Retrieved evidence is available for review. ({exc})"
        return L6AskResponse(
            answer=answer,
            intent=intent.name,
            language=intent.language,
            evidence=evidence,
            dataset_id=retrieved.get("dataset_id"),
            scenario_id=intent.entities.get("scenario_id"),
            calculation_provenance=retrieved["provenance"],
            limitations=list(dict.fromkeys(limitations)),
            provider_status=provider_status,
            provider_error_category=provider_error_category,
            generated_at=datetime.now(timezone.utc),
        )
