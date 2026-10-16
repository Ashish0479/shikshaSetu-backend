# ShikshaSetu - Teacher Data Quality System (Backend)

Layer 1 & Layer 2 Data Quality, Ingestion, Validation, and Standardization Engine for the Haryana School Education Department AI Sandbox architecture.

## Overview

This backend micro-service provides an explainable, deterministic REST API to ingest teacher records (CSV/Excel), perform schema validation, detect missing values & duplicates, apply Haryana curriculum standardizations, compute transparent data quality scores, and export cleaned datasets.

## Setup Instructions

### 1. Create and Activate Virtual Environment

```bash
cd backend
python -m venv venv

# Windows:
.\venv\Scripts\activate

# macOS / Linux:
source venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Default parameters are pre-configured. If a local MongoDB daemon is running at `mongodb://localhost:27017`, the system connects to it automatically; if MongoDB is not present, the backend automatically operates in resilient in-memory cache mode without failing.

### 4. Run the API Server

```bash
uvicorn app.main:app --reload --port 8000
```

Interactive Swagger Documentation: `http://localhost:8000/docs`

### 5. Run the Pytest Test Suite

```bash
pytest tests/ -v
```

All existing tests validate subject normalization, qualification mapping, duplicate detection, experience constraints, email/phone verification, quality score calculations, and full pipeline execution. `tests/test_l6.py` validates deterministic routing, evidence grounding, provider-unavailable behavior, PII minimization, Override validation, and append-only review history.

## Layer 6 Copilot

Layer 6 adds a read-only, advisory copilot at `POST /api/l6/ask`. The deterministic intent router supports `DATA_QUERY`, `L3_EXPLANATION`, `L4_EXPLANATION`, `L5_SCENARIO_EXPLANATION`, `POLICY_QUERY`, `GENERAL_PROJECT_HELP`, `REVIEW_ACTION`, and `UNKNOWN_OR_UNSUPPORTED`. Current staffing questions require `dataset_id`; saved scenario questions require a scenario ID.

Structured evidence is taken from the existing cleaned records, `L3AnalysisService`, `L4AnalysisService`, and persisted L5 scenario outputs. Policy and methodology retrieval searches the repository's `README.md`, `ARCHITECTURE.md`, and `DATA_DICTIONARY.md` with bounded keyword retrieval. Each response returns intent, language, evidence source IDs, calculation provenance, limitations, provider status, and a timestamp. Retrieved records exclude common teacher PII fields before entering the Gemini context.

Gemini is configured server-side only:

```text
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-2.0-flash
```

Install `google-genai` from `requirements.txt`. The SDK is loaded lazily. Missing credentials, missing SDK, provider errors, empty responses, and quota or model failures produce an explicit provider-unavailable response; they do not block L1-L5 deterministic workflows or invent an answer. No frontend `VITE_*` variable contains the key.

`POST /api/l6/scenarios/{scenario_id}/review` appends an `ACCEPT`, `REJECT`, or `OVERRIDE` event. Override requires a non-empty reason, and each event preserves the scenario input snapshot, registry version, and solver status. The current application has no authentication/RBAC middleware, so `reviewer_id` is a required caller-supplied field rather than a server-authenticated identity; this limitation must be resolved before production use. Review events are advisory and never execute transfers, postings, or HR actions.
