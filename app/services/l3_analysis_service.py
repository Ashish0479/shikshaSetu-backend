"""L3 orchestration layer for deterministic administrative analytics."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.config import settings
from app.services.geographic_paradox_service import GeographicParadoxService
from app.services.ptr_analysis_service import PTRAnalysisService
from app.services.qualification_matcher_service import QualificationMatcherService


class L3AnalysisService:
    """Runs the clean canonical dataset through PTR, qualification, and geographic analyses."""

    @staticmethod
    def analyze_record_sets(
        clean_data: Dict[str, List[Dict[str, Any]]],
        ptr_threshold: Optional[float] = None,
        max_distance_km: Optional[float] = None,
    ) -> Dict[str, Any]:
        teachers = clean_data.get("teachers", []) or clean_data.get("teacher", []) or []
        schools = clean_data.get("schools", []) or clean_data.get("school", []) or []
        enrollment = clean_data.get("enrollment", []) or clean_data.get("student", []) or []
        locations = clean_data.get("locations", []) or clean_data.get("location", []) or []

        ptr_analysis = PTRAnalysisService.analyze_schools(
            schools=schools,
            teachers=teachers,
            enrollment=enrollment,
            ptr_threshold=ptr_threshold if ptr_threshold is not None else settings.L3_PTR_THRESHOLD,
        )

        qualification_analysis = QualificationMatcherService.evaluate_teachers(teachers)

        geographic_analysis = GeographicParadoxService.detect_imbalances(
            schools=schools,
            ptr_results=ptr_analysis["schools"],
            max_distance_km=max_distance_km if max_distance_km is not None else settings.L3_GEOGRAPHIC_DISTANCE_KM,
        )

        summary = {
            "schools_analyzed": ptr_analysis["summary"]["schools_analyzed"],
            "schools_with_shortage": ptr_analysis["summary"]["schools_with_shortage"],
            "schools_with_surplus": ptr_analysis["summary"]["schools_with_surplus"],
            "qualification_matches": qualification_analysis["summary"]["match_count"],
            "qualification_mismatches": qualification_analysis["summary"]["mismatch_count"],
            "geographic_flags": geographic_analysis["flag_count"],
        }

        return {
            "ptr_analysis": ptr_analysis,
            "qualification_analysis": qualification_analysis,
            "geographic_analysis": geographic_analysis,
            "summary": summary,
            "metadata": {
                "ptr_threshold": ptr_analysis["ptr_threshold"],
                "ptr_status_tolerance": ptr_analysis["status_tolerance"],
                "max_distance_km": geographic_analysis["max_distance_km"],
            },
        }
