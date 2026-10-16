from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List

from app.database.mongodb import db_client
from app.services.l3_analysis_service import L3AnalysisService
from app.services.l4_analysis_service import L4AnalysisService
from app.services.intent_router import Intent


class RetrievalService:
    """Bounded, metadata-aware retrieval over trusted app outputs and local docs."""

    _document_names = ("README.md", "ARCHITECTURE.md", "DATA_DICTIONARY.md")
    _private_fields = {"Teacher_Name", "Contact_Number", "Email_Address", "phone", "email"}

    def retrieve(self, question: str, intent: Intent, dataset_id: str | None = None) -> Dict[str, Any]:
        evidence: List[Dict[str, Any]] = []
        limitations: List[str] = []
        provenance: List[str] = []
        resolved_dataset = dataset_id

        if intent.name == "L5_SCENARIO_EXPLANATION":
            scenario_id = intent.entities.get("scenario_id")
            scenario = db_client.get_l5_scenario(scenario_id) if scenario_id else None
            if scenario:
                evidence.append(self._evidence("scenario", scenario_id, "Saved L5 advisory scenario", self._sanitize(scenario)))
                provenance.append("Persisted L5 scenario output")
            else:
                limitations.append("The requested saved L5 scenario was not found.")
        elif intent.name in {"DATA_QUERY", "L3_EXPLANATION", "L4_EXPLANATION"}:
            if not resolved_dataset and intent.name != "L5_SCENARIO_EXPLANATION":
                limitations.append("A dataset_id is required for current staffing and analysis evidence.")
            elif resolved_dataset:
                metadata = db_client.get_dataset(resolved_dataset)
                if not metadata:
                    limitations.append(f"Dataset '{resolved_dataset}' was not found.")
                else:
                    clean = db_client.get_all_clean_records(resolved_dataset)
                    if intent.name in {"DATA_QUERY", "L3_EXPLANATION", "L4_EXPLANATION"}:
                        l3 = L3AnalysisService.analyze_record_sets(clean)
                        evidence.append(self._evidence("analysis", f"{resolved_dataset}:l3", "Layer 3 analysis", self._focus_l3(l3, question)))
                        provenance.append("L3AnalysisService.analyze_record_sets(clean_records)")
                    if intent.name == "L4_EXPLANATION":
                        l4 = L4AnalysisService.analyze_record_sets(clean)
                        evidence.append(self._evidence("analysis", f"{resolved_dataset}:l4", "Layer 4 analysis", self._focus(l4, question)))
                        provenance.append("L4AnalysisService.analyze_record_sets(clean_records)")
                    if intent.name == "DATA_QUERY":
                        rows = self._matching_rows(clean, question)
                        if rows:
                            evidence.append(self._evidence("dataset", resolved_dataset, "Cleaned dataset records", rows))
                        else:
                            limitations.append("No matching cleaned records were found for the supplied terms.")
        if intent.name in {"POLICY_QUERY", "GENERAL_PROJECT_HELP", "UNKNOWN_OR_UNSUPPORTED"}:
            documents = self._search_documents(question)
            evidence.extend(documents)
            if not documents:
                limitations.append("No relevant approved or repository methodology documents were found.")

        if not evidence:
            limitations.append("No authoritative evidence was available to ground an answer.")
        return {"evidence": evidence[:10], "limitations": list(dict.fromkeys(limitations)), "provenance": provenance, "dataset_id": resolved_dataset}

    def _focus_l3(self, result: Dict[str, Any], question: str) -> Dict[str, Any]:
        return {
            "summary": result.get("summary", {}),
            "metadata": result.get("metadata", {}),
            "ptr_analysis": self._focus(result.get("ptr_analysis", {}), question),
            "qualification_analysis": self._focus(result.get("qualification_analysis", {}), question),
            "geographic_analysis": self._focus(result.get("geographic_analysis", {}), question),
        }

    def _focus(self, value: Any, question: str) -> Any:
        if isinstance(value, dict):
            return {key: self._focus(item, question) for key, item in list(value.items())[:20]}
        if isinstance(value, list):
            return [self._focus(item, question) for item in value[:12]]
        return value

    def _matching_rows(self, clean: Dict[str, List[Dict[str, Any]]], question: str) -> List[Dict[str, Any]]:
        tokens = {token.lower() for token in re.findall(r"[A-Za-z0-9_-]{2,}", question)}
        rows: List[Dict[str, Any]] = []
        for entity, records in clean.items():
            for record in records:
                searchable = " ".join(str(value) for key, value in record.items() if key not in self._private_fields).lower()
                if not tokens or any(token in searchable for token in tokens):
                    rows.append({"entity": entity, "record": self._sanitize(record)})
                if len(rows) >= 12:
                    return rows
        return rows

    def _sanitize(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {key: self._sanitize(item) for key, item in value.items() if key not in self._private_fields}
        if isinstance(value, list):
            return [self._sanitize(item) for item in value[:20]]
        return value

    def _evidence(self, source_type: str, source_id: str, title: str, payload: Any) -> Dict[str, Any]:
        return {"source_type": source_type, "source_id": source_id, "title": title, "excerpt": str(payload)[:4000], "metadata": {"payload": payload}}

    def _search_documents(self, question: str) -> List[Dict[str, Any]]:
        root = Path(__file__).resolve().parents[3]
        terms = {term.lower() for term in re.findall(r"[A-Za-z0-9_-]{3,}", question)}
        matches = []
        for name in self._document_names:
            path = root / name
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
            ranked = sorted(paragraphs, key=lambda part: sum(term in part.lower() for term in terms), reverse=True)
            for paragraph in ranked[:2]:
                score = sum(term in paragraph.lower() for term in terms)
                if score:
                    matches.append(self._evidence("document", str(path.relative_to(root)), name, paragraph[:3000]))
        return matches[:8]
