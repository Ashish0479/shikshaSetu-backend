"""Administrative geographic imbalance detection.

This service compares nearby schools and identifies shortage/surplus patterns
without making transfer recommendations.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from app.config import settings
from app.utils.helpers import is_null_or_empty, safe_str


class GeographicParadoxService:
    """Flag nearby schools whose teacher availability is inconsistent."""

    @staticmethod
    def _to_float(value: Any) -> Optional[float]:
        if is_null_or_empty(value):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        earth_radius_km = 6371.0
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)
        a = (
            math.sin(delta_phi / 2) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
        )
        return 2 * earth_radius_km * math.asin(math.sqrt(a))

    @classmethod
    def detect_imbalances(
        cls,
        schools: List[Dict[str, Any]],
        ptr_results: List[Dict[str, Any]],
        max_distance_km: Optional[float] = None,
    ) -> Dict[str, Any]:
        threshold = float(max_distance_km if max_distance_km is not None else settings.L3_GEOGRAPHIC_DISTANCE_KM)
        threshold = threshold if threshold > 0 else 10.0

        school_map = {}
        for school in schools:
            code = safe_str(school.get("School_Code"))
            if code:
                school_map[code.upper()] = school

        ptr_map = {}
        for item in ptr_results:
            code = safe_str(item.get("school_code"))
            if code:
                ptr_map[code.upper()] = item

        flags: List[Dict[str, Any]] = []
        seen_pairs = set()

        for school_code, ptr_item in ptr_map.items():
            if ptr_item.get("status") not in ("SHORTAGE", "SURPLUS"):
                continue
            school = school_map.get(school_code)
            if not school:
                continue

            lat1 = cls._to_float(school.get("Latitude"))
            lon1 = cls._to_float(school.get("Longitude"))
            school_name1 = safe_str(school.get("School_Name")) or school_code
            district1 = safe_str(school.get("District")) or "Unknown"

            for other_code, other_ptr in ptr_map.items():
                if other_code == school_code:
                    continue
                pair_key = tuple(sorted((school_code, other_code)))
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

                if other_ptr.get("status") not in ("SHORTAGE", "SURPLUS"):
                    continue

                other_school = school_map.get(other_code)
                if not other_school:
                    continue

                lat2 = cls._to_float(other_school.get("Latitude"))
                lon2 = cls._to_float(other_school.get("Longitude"))
                if lat1 is not None and lon1 is not None and lat2 is not None and lon2 is not None:
                    d = cls.haversine_km(lat1, lon1, lat2, lon2)
                    if d < 0.5:
                        continue
                    if d > threshold:
                        continue
                elif (safe_str(school.get("District")) or "").lower() != (safe_str(other_school.get("District")) or "").lower():
                    continue

                shortage_school = None
                surplus_school = None
                if ptr_item.get("status") == "SHORTAGE" and other_ptr.get("status") == "SURPLUS":
                    shortage_school = school_code
                    surplus_school = other_code
                elif ptr_item.get("status") == "SURPLUS" and other_ptr.get("status") == "SHORTAGE":
                    shortage_school = other_code
                    surplus_school = school_code
                else:
                    continue

                if shortage_school and surplus_school:
                    distance_km = None
                    if lat1 is not None and lon1 is not None and lat2 is not None and lon2 is not None:
                        distance_km = round(cls.haversine_km(lat1, lon1, lat2, lon2), 2)
                    flags.append({
                        "shortage_school_code": shortage_school,
                        "surplus_school_code": surplus_school,
                        "distance_km": distance_km,
                        "resolution": "geographic" if distance_km is not None else "district_level_only",
                        "potential_issue": "Potential geographic imbalance detected between nearby schools with opposite PTR status.",
                        "reason": (
                            f"Schools {school_name1} and {safe_str(other_school.get('School_Name')) or other_code} are within the configured threshold and show opposite staffing conditions."
                        ),
                    })

        return {
            "max_distance_km": threshold,
            "flags": flags,
            "flag_count": len(flags),
            "summary": {
                "shortage_surplus_pairs": len(flags),
            },
        }
