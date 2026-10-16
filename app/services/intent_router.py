from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class Intent:
    name: str
    language: str
    entities: Dict[str, str] = field(default_factory=dict)
    clarification: str | None = None


class IntentRouter:
    """Deterministic, allowlisted routing for operational questions."""

    _hindi = re.compile(r"[\u0900-\u097f]")
    _scenario = re.compile(r"(?:scenario|परिदृश्य)[\s#:_-]*([A-Za-z0-9_-]+)", re.I)
    _school = re.compile(r"(?:school|विद्यालय)[\s#:_-]*(S?\d+[A-Za-z0-9_-]*)", re.I)
    _district = re.compile(r"(?:district|जिला)[\s:=-]*([A-Za-z][A-Za-z .'-]+)", re.I)

    def route(self, question: str, scenario_id: str | None = None) -> Intent:
        text = question.strip()
        lowered = text.lower()
        language = "hi" if self._hindi.search(text) and not re.search(r"\b(the|which|what|why|explain)\b", lowered) else "en"
        entities: Dict[str, str] = {}
        if scenario_id:
            entities["scenario_id"] = scenario_id
        else:
            match = self._scenario.search(text)
            if match:
                entities["scenario_id"] = match.group(1)
        school = self._school.search(text)
        if school:
            entities["school_id"] = school.group(1)
        district = self._district.search(text)
        if district:
            entities["district"] = district.group(1).strip(" .,;?")

        if any(word in lowered for word in ("accept", "reject", "override", "स्वीकार", "अस्वीकार")):
            name = "REVIEW_ACTION"
        elif any(word in lowered for word in ("policy", "constraint", "registry", "methodology", "policy", "नीति", "नियम")):
            name = "POLICY_QUERY"
        elif entities.get("scenario_id") or any(word in lowered for word in ("scenario", "परिदृश्य", "solver", "assignment")):
            name = "L5_SCENARIO_EXPLANATION"
        elif any(word in lowered for word in ("risk", "retirement", "forecast", "outlook", "जोखिम", "सेवानिवृत्ति")):
            name = "L4_EXPLANATION"
        elif any(word in lowered for word in ("qualification", "mismatch", "ptr", "shortage", "geographic", "eligible", "कमी", "योग्यता", "अनुपात")):
            name = "L3_EXPLANATION"
        elif any(word in lowered for word in ("school", "teacher", "staff", "district", "subject", "availability", "विद्यालय", "शिक्षक")):
            name = "DATA_QUERY"
        elif any(word in lowered for word in ("shikshasetu", "how does", "help", "method", "कैसे", "मदद")):
            name = "GENERAL_PROJECT_HELP"
        else:
            name = "UNKNOWN_OR_UNSUPPORTED"

        clarification = None
        if name == "L5_SCENARIO_EXPLANATION" and "scenario_id" not in entities:
            clarification = "Please provide a scenario ID so the saved L5 result can be retrieved reliably."
        return Intent(name=name, language=language, entities=entities, clarification=clarification)
