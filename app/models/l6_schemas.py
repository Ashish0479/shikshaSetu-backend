from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class L6AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    dataset_id: Optional[str] = Field(default=None, max_length=128)
    scenario_id: Optional[str] = Field(default=None, max_length=128)

    @field_validator("question")
    @classmethod
    def question_must_have_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must contain text")
        return value.strip()


class EvidenceReference(BaseModel):
    source_type: str
    source_id: str
    title: str
    excerpt: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class L6AskResponse(BaseModel):
    answer: str
    intent: str
    language: str
    evidence: List[EvidenceReference] = Field(default_factory=list)
    dataset_id: Optional[str] = None
    analysis_id: Optional[str] = None
    scenario_id: Optional[str] = None
    calculation_provenance: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    provider_status: str
    provider_error_category: Optional[str] = None
    generated_at: datetime


class L6ReviewRequest(BaseModel):
    decision: str
    reviewer_id: str = Field(min_length=1, max_length=128)
    reason: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("decision")
    @classmethod
    def validate_decision(cls, value: str) -> str:
        normalized = value.upper().strip()
        if normalized not in {"ACCEPT", "REJECT", "OVERRIDE"}:
            raise ValueError("decision must be ACCEPT, REJECT, or OVERRIDE")
        return normalized

    @model_validator(mode="after")
    def validate_override_reason(self):
        if self.decision == "OVERRIDE" and not (self.reason or "").strip():
            raise ValueError("reason is required for OVERRIDE")
        if self.reason:
            self.reason = self.reason.strip()
        return self
