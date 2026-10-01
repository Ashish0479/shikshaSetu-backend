"""Deterministic teacher subject-qualification matching.

This service consumes L1-L2 cleaned teacher rows and reports whether the
recorded qualification is aligned with the assigned subject and designation.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from app.utils.helpers import is_null_or_empty, safe_str


class QualificationMatcherService:
    """Map teacher subject and qualification to explicit rule-based statuses."""

    @staticmethod
    def _clean_text(value: Any) -> str:
        if is_null_or_empty(value):
            return ""
        return re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()

    @staticmethod
    def _has_any(text: str, keywords: List[str]) -> bool:
        return any(keyword in text for keyword in keywords)

    @classmethod
    def _evaluate_single_teacher(cls, teacher: Dict[str, Any]) -> Dict[str, Any]:
        teacher_id = safe_str(teacher.get("Teacher_ID")) or "UNKNOWN"
        designation = cls._clean_text(teacher.get("Designation"))
        subject = cls._clean_text(teacher.get("Subject"))
        qualification = cls._clean_text(teacher.get("Qualification"))
        result = {
            "Teacher_ID": teacher_id,
            "Teacher_Name": safe_str(teacher.get("Teacher_Name")) or "Unknown",
            "School_Code": safe_str(teacher.get("School_Code")) or "Unknown",
            "Designation": safe_str(teacher.get("Designation")) or "Unknown",
            "Subject": safe_str(teacher.get("Subject")) or "Unknown",
            "Qualification": safe_str(teacher.get("Qualification")) or "Unknown",
        }

        def classify(status: str, reason: str, confidence: float) -> Dict[str, Any]:
            return {**result, "qualification_match": status, "reason": reason, "confidence": confidence}

        if not subject or not qualification:
            return classify("UNKNOWN", "Subject or qualification information is missing.", 0.0)

        subject_terms = {
            "mathematics": ["mathematics", "maths", "math"],
            "economics": ["economics", "economic"],
            "geography": ["geography", "geographic"],
            "political science": ["political science", "political"],
            "computer science": ["computer science", "information technology", "it"],
            "physics": ["physics"],
            "chemistry": ["chemistry"],
            "biology": ["biology"],
            "science": ["science"],
            "english": ["english"],
            "hindi": ["hindi"],
            "social science": ["social science", "social studies"],
            "history": ["history"],
        }
        canonical_subject = next(
            (name for name, terms in subject_terms.items() if any(term in subject for term in terms)),
            None,
        )

        # Exact specialization always wins over generic degree rules.
        if canonical_subject:
            specialization_terms = subject_terms[canonical_subject]
            if any(term in qualification for term in specialization_terms):
                return classify(
                    "MATCH",
                    f"Qualification has a {canonical_subject.title()} specialization matching the assigned subject.",
                    0.98,
                )

            incompatible_terms = {
                term
                for terms in subject_terms.values()
                for term in terms
                if term not in specialization_terms and term in qualification
            }
            if incompatible_terms:
                return classify(
                    "MISMATCH",
                    "Qualification specialization does not match the assigned subject.",
                    0.95,
                )

        if canonical_subject == "computer science" and cls._has_any(qualification, ["bca", "mca", "b tech", "btech", "m tech", "mtech"]):
            return classify("MATCH", "Qualification is a recognized Computer Science / IT pathway.", 0.92)
        if canonical_subject == "mathematics" and cls._has_any(qualification, ["b sc", "m sc"]):
            return classify("MATCH", "Qualification is a recognized science pathway compatible with Mathematics.", 0.85)
        if canonical_subject in {"physics", "chemistry", "biology", "science"} and cls._has_any(qualification, ["b sc", "m sc"]):
            return classify("MATCH", "Qualification is a recognized science pathway compatible with the assigned subject.", 0.85)
        if canonical_subject in {"english", "hindi", "history", "geography", "economics", "political science", "social science"} and cls._has_any(qualification, ["b a", "m a"]):
            return classify("PARTIAL_MATCH", "Qualification is a recognized arts pathway, but its subject specialization is not explicit.", 0.6)
        if "general" in subject or "all subjects" in subject or "primary" in designation:
            if cls._has_any(qualification, ["deled", "jbt", "b ed", "bed"]):
                return classify("MATCH", "Primary/general assignment is compatible with the recorded teacher-training qualification.", 0.9)
            return classify("PARTIAL_MATCH", "A general teaching assignment is present, but the qualification pathway is not fully specific.", 0.55)
        if cls._has_any(qualification, ["b sc", "m sc", "b a", "m a", "b ed", "bed", "deled", "jbt", "bca", "mca"]):
            return classify("PARTIAL_MATCH", "A recognized qualification is present, but subject compatibility cannot be established.", 0.5)
        return classify("UNKNOWN", "No recognized subject-to-qualification rule matched the teacher record.", 0.0)

    @classmethod
    def evaluate_teachers(cls, teachers: List[Dict[str, Any]]) -> Dict[str, Any]:
        records = [cls._evaluate_single_teacher(t) for t in teachers]
        match_count = sum(1 for r in records if r["qualification_match"] == "MATCH")
        partial_count = sum(1 for r in records if r["qualification_match"] == "PARTIAL_MATCH")
        mismatch_count = sum(1 for r in records if r["qualification_match"] == "MISMATCH")
        unknown_count = sum(1 for r in records if r["qualification_match"] == "UNKNOWN")

        return {
            "records": records,
            "summary": {
                "total_teachers": len(records),
                "match_count": match_count,
                "partial_match_count": partial_count,
                "mismatch_count": mismatch_count,
                "unknown_count": unknown_count,
            },
        }
