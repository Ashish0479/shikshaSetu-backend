"""Layer 4 predictive analytics for retirement outlook, staffing risk, and clustering."""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from app.config import settings
from app.services.l3_analysis_service import L3AnalysisService
from app.utils.helpers import is_null_or_empty, safe_str


class L4AnalysisService:
    """Build explainable L4 analytics on top of the cleaned L1/L2/L3 system."""

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        if is_null_or_empty(value):
            return default
        try:
            numeric = float(value)
            if math.isnan(numeric) or math.isinf(numeric):
                return default
            return numeric
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _normalize_school_code(value: Any) -> Optional[str]:
        code = safe_str(value)
        if not code:
            return None
        return code.strip().upper()

    @staticmethod
    def _parse_date(value: Any) -> Optional[pd.Timestamp]:
        if is_null_or_empty(value):
            return None
        try:
            dt = pd.to_datetime(value, errors="coerce")
        except Exception:
            return None
        if pd.isna(dt):
            return None
        return dt

    @staticmethod
    def _retirement_year_for_dob(value: Any) -> Optional[int]:
        dt = L4AnalysisService._parse_date(value)
        if dt is None:
            return None
        if dt.year > datetime.now().year:
            return None
        if dt.year < 1900:
            return None
        return dt.year + settings.RETIREMENT_AGE

    @staticmethod
    def calculate_retirement_outlook(teachers: List[Dict[str, Any]]) -> Dict[str, Any]:
        current_year = datetime.now().year
        horizon_years = list(range(current_year + 1, current_year + settings.FORECAST_HORIZON_YEARS + 1))
        year_counts = {year: 0 for year in horizon_years}
        retirement_years_by_school: Dict[str, int] = defaultdict(int)
        excluded = []
        included = 0

        for index, teacher in enumerate(teachers, start=1):
            dob = teacher.get("Date_of_Birth")
            retirement_year = L4AnalysisService._retirement_year_for_dob(dob)
            if retirement_year is None:
                excluded.append({
                    "row_number": index,
                    "Teacher_ID": safe_str(teacher.get("Teacher_ID")) or "UNKNOWN",
                    "reason": "Missing, invalid, or future DOB excluded from retirement calculation.",
                })
                continue
            if retirement_year in year_counts:
                year_counts[retirement_year] += 1
                included += 1
                school_code = L4AnalysisService._normalize_school_code(teacher.get("School_Code"))
                if school_code:
                    retirement_years_by_school[school_code] += 1

        total = sum(year_counts.values())
        retirement_rows = [
            {"year": year, "teachers_reaching_retirement_age": year_counts.get(year, 0)}
            for year in horizon_years
        ]

        warnings = []
        if excluded:
            warnings.append(
                f"{len(excluded)} teacher records were excluded from retirement projection because DOB was missing, invalid, or in the future."
            )

        return {
            "current_year": current_year,
            "retirement_age": settings.RETIREMENT_AGE,
            "forecast_horizon_years": horizon_years,
            "yearly_counts": retirement_rows,
            "total_teachers_reaching_retirement_age": total,
            "teachers_considered_for_calculation": included,
            "retirement_years_by_school": dict(sorted(retirement_years_by_school.items())),
            "excluded_dob_records": excluded,
            "warnings": warnings,
        }

    @staticmethod
    def compute_school_risk_metrics(
        shortage: float,
        expected_teachers: float,
        current_teachers: int,
        retiring_within_5_years: int,
        actual_ptr: Optional[float],
        target_ptr: float,
        gap_score: float,
    ) -> Dict[str, float]:
        if expected_teachers > 0:
            shortage_ratio = shortage / expected_teachers
            shortage_score = min(shortage_ratio * 100.0, 100.0)
        else:
            shortage_score = 0.0

        if current_teachers > 0:
            retirement_ratio = retiring_within_5_years / current_teachers
            retirement_score = min(retirement_ratio * 100.0, 100.0)
        else:
            retirement_score = 0.0

        if actual_ptr is not None and actual_ptr > 0:
            ptr_pressure = max((actual_ptr - target_ptr) / target_ptr, 0.0) if target_ptr > 0 else 0.0
            ptr_score = min(ptr_pressure * 100.0, 100.0)
        else:
            ptr_score = 0.0

        gap_score = max(0.0, min(float(gap_score), 100.0))
        risk_score = (
            0.40 * shortage_score
            + 0.30 * retirement_score
            + 0.20 * ptr_score
            + 0.10 * gap_score
        )
        risk_score = max(0.0, min(risk_score, 100.0))

        if risk_score < 25:
            category = "Low"
        elif risk_score < 50:
            category = "Moderate"
        elif risk_score < 75:
            category = "High"
        else:
            category = "Critical"

        return {
            "shortage_score": round(shortage_score, 2),
            "retirement_score": round(retirement_score, 2),
            "ptr_score": round(ptr_score, 2),
            "gap_score": round(gap_score, 2),
            "risk_score": round(risk_score, 2),
            "risk_category": category,
        }

    @staticmethod
    def _build_risk_reason(shortage_score: float, retirement_score: float, ptr_score: float, risk_score: float) -> str:
        if shortage_score >= 50 and retirement_score >= 25:
            return "High staffing pressure due to existing shortage and multiple teachers approaching retirement."
        if shortage_score >= 35:
            return "Current shortage is materially increasing staffing pressure across the school."
        if retirement_score >= 30:
            return "Retirement turnover is a meaningful driver of future staffing pressure."
        if ptr_score >= 25:
            return "PTR is above target and is creating near-term operational pressure."
        if risk_score >= 50:
            return "School risk is elevated due to combined staffing and retirement pressure."
        return "Staffing risk remains comparatively moderate and may require monitoring."

    @staticmethod
    def _qualification_gap_ratio_per_school(
        school_code: Optional[str],
        qualification_records: List[Dict[str, Any]],
        teacher_count: int,
    ) -> Tuple[Optional[float], List[str]]:
        if not school_code or teacher_count <= 0:
            return None, []

        mismatch_count = 0
        for record in qualification_records:
            if safe_str(record.get("School_Code")).upper() != school_code.upper():
                continue
            if safe_str(record.get("qualification_match")) == "MISMATCH":
                mismatch_count += 1

        if teacher_count <= 0:
            return None, []
        ratio = mismatch_count / teacher_count
        return min(max(ratio, 0.0), 1.0), []

    @staticmethod
    def _calculate_future_staffing_risk(
        clean_data: Dict[str, List[Dict[str, Any]]],
        l3_analysis: Dict[str, Any],
        retirement_outlook: Dict[str, Any],
    ) -> Dict[str, Any]:
        teachers = clean_data.get("teachers", []) or clean_data.get("teacher", []) or []
        schools = clean_data.get("schools", []) or clean_data.get("school", []) or []

        ptr_by_school = {safe_str(item.get("school_code")).upper(): item for item in (l3_analysis.get("ptr_analysis", {}).get("schools", []) or []) if safe_str(item.get("school_code"))}
        qualification_records = l3_analysis.get("qualification_analysis", {}).get("records", []) or []
        warnings: List[str] = []

        teacher_by_school: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for teacher in teachers:
            code = L4AnalysisService._normalize_school_code(teacher.get("School_Code"))
            if code:
                teacher_by_school[code].append(teacher)
            elif teacher.get("School_Code") is not None:
                warnings.append("Teachers with missing or invalid School_Code were excluded from the school-level staffing risk model.")

        retirement_by_school: Dict[str, int] = defaultdict(int)
        retirement_years = retirement_outlook.get("retirement_years_by_school", {})
        if retirement_years:
            for school_code, count in retirement_years.items():
                retirement_by_school[school_code.upper()] = int(count)

        if not retirement_by_school and teachers:
            current_year = datetime.now().year
            horizon = list(range(current_year + 1, current_year + settings.FORECAST_HORIZON_YEARS + 1))
            for teacher in teachers:
                stream = L4AnalysisService._retirement_year_for_dob(teacher.get("Date_of_Birth"))
                if stream in horizon and teacher.get("School_Code"):
                    retirement_by_school[L4AnalysisService._normalize_school_code(teacher.get("School_Code"))] += 1

        school_map = {L4AnalysisService._normalize_school_code(school.get("School_Code")): school for school in schools if L4AnalysisService._normalize_school_code(school.get("School_Code")) is not None}
        all_school_codes = sorted(set(list(ptr_by_school.keys()) + list(school_map.keys()) + list(teacher_by_school.keys())))

        risk_rows: List[Dict[str, Any]] = []
        for school_code in all_school_codes:
            school = school_map.get(school_code, {})
            ptr_item = ptr_by_school.get(school_code, {})
            current_teachers = len(teacher_by_school.get(school_code, []))
            expected_teachers = L4AnalysisService._safe_float(ptr_item.get("expected_teachers"), 0.0)
            current_shortage = L4AnalysisService._safe_float(ptr_item.get("shortage"), 0.0)
            current_surplus = L4AnalysisService._safe_float(ptr_item.get("surplus"), 0.0)
            actual_ptr = ptr_item.get("ptr")
            if actual_ptr is None:
                if current_teachers > 0 and (ptr_item.get("total_students") or 0) > 0:
                    actual_ptr = float(ptr_item.get("total_students", 0.0)) / float(current_teachers)
            actual_ptr = L4AnalysisService._safe_float(actual_ptr, 0.0)
            retiring = retirement_by_school.get(school_code, 0)

            qualification_gap_ratio, _ = L4AnalysisService._qualification_gap_ratio_per_school(
                school_code=school_code,
                qualification_records=qualification_records,
                teacher_count=current_teachers,
            )
            subject_gap_ratio = None
            gap_score = 0.0
            if subject_gap_ratio is not None and qualification_gap_ratio is not None:
                subject_score = min(subject_gap_ratio * 100.0, 100.0)
                qualification_score = min(qualification_gap_ratio * 100.0, 100.0)
                gap_score = 0.5 * subject_score + 0.5 * qualification_score
            elif subject_gap_ratio is not None:
                gap_score = min(subject_gap_ratio * 100.0, 100.0)
            elif qualification_gap_ratio is not None:
                gap_score = min(qualification_gap_ratio * 100.0, 100.0)
            else:
                warnings.append(
                    "Qualification and subject-gap signals were unavailable for at least one school, so the L4 gap score was set to 0 for that school."
                )

            metrics = L4AnalysisService.compute_school_risk_metrics(
                shortage=current_shortage,
                expected_teachers=expected_teachers,
                current_teachers=current_teachers,
                retiring_within_5_years=retiring,
                actual_ptr=actual_ptr,
                target_ptr=settings.TARGET_PTR,
                gap_score=gap_score,
            )

            risk_rows.append({
                "School_Code": school_code,
                "School_Name": safe_str(school.get("School_Name")) or safe_str(ptr_item.get("school_name")) or "Unknown",
                "District": safe_str(school.get("District")) or safe_str(ptr_item.get("district")) or "Unknown",
                "Current_Teachers": current_teachers,
                "Expected_Teachers": round(expected_teachers, 2),
                "Current_Shortage": round(current_shortage, 2),
                "Current_Surplus": round(current_surplus, 2),
                "PTR": round(actual_ptr, 2) if actual_ptr else 0.0,
                "Retiring_Within_5_Years": retiring,
                "Shortage_Score": metrics["shortage_score"],
                "Retirement_Score": metrics["retirement_score"],
                "PTR_Score": metrics["ptr_score"],
                "Gap_Score": metrics["gap_score"],
                "Risk_Score": metrics["risk_score"],
                "Risk_Category": metrics["risk_category"],
                "Reason": L4AnalysisService._build_risk_reason(
                    metrics["shortage_score"],
                    metrics["retirement_score"],
                    metrics["ptr_score"],
                    metrics["risk_score"],
                ),
            })

        if not risk_rows:
            warnings.append("No eligible school records were available for the L4 risk model.")

        summary = {
            "low": sum(1 for row in risk_rows if row["Risk_Category"] == "Low"),
            "moderate": sum(1 for row in risk_rows if row["Risk_Category"] == "Moderate"),
            "high": sum(1 for row in risk_rows if row["Risk_Category"] == "High"),
            "critical": sum(1 for row in risk_rows if row["Risk_Category"] == "Critical"),
        }

        return {
            "target_ptr": settings.TARGET_PTR,
            "schools": risk_rows,
            "summary": summary,
            "warnings": list(dict.fromkeys(warnings)),
        }

    @staticmethod
    def _scale_features(frame: pd.DataFrame) -> pd.DataFrame:
        scaled = frame.copy()
        for column in scaled.columns:
            values = pd.to_numeric(scaled[column], errors="coerce")
            if values.isna().all():
                scaled[column] = 0.0
                continue
            min_value = values.min()
            max_value = values.max()
            if pd.isna(min_value) or pd.isna(max_value) or max_value == min_value:
                scaled[column] = 0.0
            else:
                scaled[column] = (values - min_value) / (max_value - min_value)
        return scaled.fillna(0.0).replace([np.inf, -np.inf], 0.0)

    @staticmethod
    def _kmeans(data: np.ndarray, k: int, max_iterations: int = 50, random_state: int = 42) -> Tuple[np.ndarray, np.ndarray]:
        rng = np.random.default_rng(random_state)
        n_samples = len(data)
        if n_samples == 0:
            return np.array([]), np.array([], dtype=int)
        if k <= 0 or k > n_samples:
            k = max(1, min(k, n_samples))
        centroids = data[rng.choice(n_samples, size=k, replace=False)].copy()
        labels = np.zeros(n_samples, dtype=int)
        for _ in range(max_iterations):
            distances = np.linalg.norm(data[:, None, :] - centroids[None, :, :], axis=2)
            new_labels = np.argmin(distances, axis=1)
            if np.array_equal(new_labels, labels):
                labels = new_labels
                break
            labels = new_labels
            new_centroids = centroids.copy()
            for cluster_id in range(k):
                members = data[labels == cluster_id]
                if len(members) == 0:
                    new_centroids[cluster_id] = centroids[cluster_id]
                else:
                    new_centroids[cluster_id] = members.mean(axis=0)
            centroids = new_centroids
        return centroids, labels

    @staticmethod
    def _silhouette_score(data: np.ndarray, labels: np.ndarray) -> float:
        if len(data) < 2:
            return 0.0
        unique_labels = np.unique(labels)
        if len(unique_labels) < 2:
            return 0.0
        scores = []
        for index in range(len(data)):
            same_cluster = labels == labels[index]
            same_cluster_count = np.count_nonzero(same_cluster) - 1
            if same_cluster_count <= 0:
                scores.append(0.0)
                continue
            same_cluster_distances = np.linalg.norm(data[same_cluster] - data[index], axis=1)
            a = same_cluster_distances.sum() / same_cluster_count
            other_clusters = [cluster for cluster in unique_labels if cluster != labels[index]]
            if not other_clusters:
                scores.append(0.0)
                continue
            b_values = []
            for cluster_id in other_clusters:
                cluster_distances = np.linalg.norm(data[labels == cluster_id] - data[index], axis=1)
                if len(cluster_distances):
                    b_values.append(cluster_distances.min())
            if not b_values:
                scores.append(0.0)
                continue
            b = min(b_values)
            denominator = max(a, b)
            if denominator == 0:
                scores.append(0.0)
            else:
                scores.append((b - a) / denominator)
        return float(np.mean(scores)) if scores else 0.0

    @staticmethod
    def _school_cluster_rows(risk_rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[str]]:
        if len(risk_rows) < 4:
            return [], [], ["Insufficient school records for reliable clustering."]

        feature_columns = [
            "Current_Teachers",
            "Expected_Teachers",
            "PTR",
            "Current_Shortage",
            "Current_Surplus",
            "Retiring_Within_5_Years",
            "Risk_Score",
        ]
        frame = pd.DataFrame(risk_rows)
        numeric_frame = frame[feature_columns].apply(pd.to_numeric, errors="coerce").fillna(0.0).replace([np.inf, -np.inf], 0.0)
        scaled = L4AnalysisService._scale_features(numeric_frame)
        data = scaled.to_numpy(dtype=float)

        best_k = 2
        best_score = -1.0
        max_k = min(6, len(risk_rows) - 1)
        if max_k < 2:
            return [], [], ["Insufficient school records for reliable clustering."]

        for k in range(2, max_k + 1):
            centroids, labels = L4AnalysisService._kmeans(data, k)
            if centroids.size == 0:
                continue
            score = L4AnalysisService._silhouette_score(data, labels)
            if score > best_score:
                best_score = score
                best_k = k

        centroids, labels = L4AnalysisService._kmeans(data, best_k)
        clustered_rows = []
        for index, row in enumerate(risk_rows):
            clustered_rows.append({
                "School_Code": row["School_Code"],
                "School_Name": row["School_Name"],
                "District": row["District"],
                "Cluster_ID": int(labels[index]) + 1,
                "Students": max(0, int(round(row["Current_Teachers"] * max(row["PTR"], 0.0)))) if row.get("PTR") else 0,
                "Teachers": row["Current_Teachers"],
                "PTR": row["PTR"],
                "Shortage": row["Current_Shortage"],
                "Surplus": row["Current_Surplus"],
                "Retiring_Within_5_Years": row["Retiring_Within_5_Years"],
                "Risk_Score": row["Risk_Score"],
                "Risk_Category": row["Risk_Category"],
            })

        summary = []
        for cluster_id in sorted({row["Cluster_ID"] for row in clustered_rows}):
            cluster_rows = [row for row in clustered_rows if row["Cluster_ID"] == cluster_id]
            if not cluster_rows:
                continue
            avg_students = sum(row["Students"] for row in cluster_rows) / len(cluster_rows)
            avg_teachers = sum(row["Teachers"] for row in cluster_rows) / len(cluster_rows)
            avg_ptr = sum(row["PTR"] for row in cluster_rows) / len(cluster_rows)
            avg_shortage = sum(row["Shortage"] for row in cluster_rows) / len(cluster_rows)
            avg_surplus = sum(row["Surplus"] for row in cluster_rows) / len(cluster_rows)
            avg_retirements = sum(row["Retiring_Within_5_Years"] for row in cluster_rows) / len(cluster_rows)
            avg_risk = sum(row["Risk_Score"] for row in cluster_rows) / len(cluster_rows)
            summary.append({
                "Cluster_ID": cluster_id,
                "Number_of_Schools": len(cluster_rows),
                "Average_Students": round(avg_students, 2),
                "Average_Teachers": round(avg_teachers, 2),
                "Average_PTR": round(avg_ptr, 2),
                "Average_Shortage": round(avg_shortage, 2),
                "Average_Surplus": round(avg_surplus, 2),
                "Average_Retirements": round(avg_retirements, 2),
                "Average_Risk_Score": round(avg_risk, 2),
            })

        explanations = []
        overall_ptr = sum(row["PTR"] for row in clustered_rows) / len(clustered_rows) if clustered_rows else 0.0
        overall_shortage = sum(row["Shortage"] for row in clustered_rows) / len(clustered_rows) if clustered_rows else 0.0
        overall_risk = sum(row["Risk_Score"] for row in clustered_rows) / len(clustered_rows) if clustered_rows else 0.0
        for item in summary:
            if item["Average_PTR"] > overall_ptr and item["Average_Shortage"] > overall_shortage:
                explanations.append(
                    f"Cluster {item['Cluster_ID']} contains schools with relatively high enrollment, higher PTR and greater average staffing shortage."
                )
            elif item["Average_Risk_Score"] > overall_risk:
                explanations.append(
                    f"Cluster {item['Cluster_ID']} contains schools with above-average staffing risk and retirement pressure."
                )
            else:
                explanations.append(
                    f"Cluster {item['Cluster_ID']} is comparatively stable with lower average shortage and moderate staffing risk."
                )

        return clustered_rows, summary, explanations

    @staticmethod
    def _calculate_school_clusters(risk_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        clustered_rows, summary, explanations = L4AnalysisService._school_cluster_rows(risk_rows)
        if not clustered_rows:
            return {
                "available": False,
                "message": "Insufficient school records for reliable clustering.",
                "clusters": [],
                "cluster_summary": [],
                "warnings": explanations,
            }

        return {
            "available": True,
            "clusters": clustered_rows,
            "cluster_summary": summary,
            "cluster_explanations": explanations,
            "warnings": [],
        }

    @staticmethod
    def _calculate_forecast_information(clean_data: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
        historical = clean_data.get("historical_staffing") or clean_data.get("historical_data") or clean_data.get("history") or []
        if isinstance(historical, dict):
            historical = [historical]
        if not historical:
            return {
                "available": False,
                "message": "Historical time-series data is insufficient for Prophet/ARIMA backtesting. Retirement outlook is calculated from current teacher DOB data using the configured retirement age of 60 years.",
                "models": [],
                "forecast_performance": [],
                "warnings": [
                    "Historical time-series data is insufficient for Prophet/ARIMA backtesting. Retirement outlook is calculated from current teacher DOB data using the configured retirement age of 60 years."
                ],
            }

        has_time_axis = False
        for row in historical:
            if isinstance(row, dict) and any(key.lower() in ("year", "month", "date", "period") for key in row.keys()):
                has_time_axis = True
                break

        if not has_time_axis:
            return {
                "available": False,
                "message": "Historical time-series data is insufficient for Prophet/ARIMA backtesting. Retirement outlook is calculated from current teacher DOB data using the configured retirement age of 60 years.",
                "models": [],
                "forecast_performance": [],
                "warnings": [
                    "Historical time-series data is insufficient for Prophet/ARIMA backtesting. Retirement outlook is calculated from current teacher DOB data using the configured retirement age of 60 years."
                ],
            }

        return {
            "available": True,
            "message": "Historical time-series data is available for forecasting; use a dedicated time-series model pipeline to train and compare Prophet and ARIMA models.",
            "models": [{"model": "Prophet", "status": "ready"}, {"model": "ARIMA", "status": "ready"}],
            "forecast_performance": [],
            "warnings": [],
        }

    @staticmethod
    def analyze_record_sets(clean_data: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
        teachers = clean_data.get("teachers", []) or clean_data.get("teacher", []) or []
        schools = clean_data.get("schools", []) or clean_data.get("school", []) or []
        if not teachers and not schools:
            return {
                "retirement_outlook": {
                    "current_year": datetime.now().year,
                    "retirement_age": settings.RETIREMENT_AGE,
                    "forecast_horizon_years": [],
                    "yearly_counts": [],
                    "total_teachers_reaching_retirement_age": 0,
                    "teachers_considered_for_calculation": 0,
                    "excluded_dob_records": [],
                    "warnings": ["No teacher records were available for L4 retirement analysis."],
                },
                "future_staffing_risk": {
                    "target_ptr": settings.TARGET_PTR,
                    "schools": [],
                    "summary": {"low": 0, "moderate": 0, "high": 0, "critical": 0},
                    "warnings": ["No school records were available for staffing risk analysis."],
                },
                "school_clusters": {
                    "available": False,
                    "message": "Insufficient school records for reliable clustering.",
                    "clusters": [],
                    "cluster_summary": [],
                    "warnings": ["Insufficient school records for reliable clustering."],
                },
                "forecast": L4AnalysisService._calculate_forecast_information(clean_data),
                "warnings": ["No valid teacher or school data was available for L4 analysis."],
                "metadata": {
                    "analysis_date": datetime.utcnow().isoformat(),
                    "dataset_type": "cleaned_records",
                },
            }

        l3_analysis = L3AnalysisService.analyze_record_sets(clean_data)
        retirement_outlook = L4AnalysisService.calculate_retirement_outlook(teachers)
        risk_result = L4AnalysisService._calculate_future_staffing_risk(clean_data, l3_analysis, retirement_outlook)
        cluster_result = L4AnalysisService._calculate_school_clusters(risk_result.get("schools", []))
        forecast = L4AnalysisService._calculate_forecast_information(clean_data)

        warnings = []
        warnings.extend(retirement_outlook.get("warnings", []))
        warnings.extend(risk_result.get("warnings", []))
        warnings.extend(cluster_result.get("warnings", []))
        warnings.extend(forecast.get("warnings", []))
        warnings = list(dict.fromkeys(warnings))

        return {
            "retirement_outlook": retirement_outlook,
            "future_staffing_risk": {
                **risk_result,
                "risk_score_formula": "0.40 * Shortage_Score + 0.30 * Retirement_Score + 0.20 * PTR_Score + 0.10 * Gap_Score",
            },
            "school_clusters": cluster_result,
            "forecast": forecast,
            "warnings": warnings,
            "metadata": {
                "analysis_date": datetime.utcnow().isoformat(),
                "retirement_age": settings.RETIREMENT_AGE,
                "forecast_horizon_years": settings.FORECAST_HORIZON_YEARS,
                "target_ptr": settings.TARGET_PTR,
                "l3_reused": True,
            },
        }
