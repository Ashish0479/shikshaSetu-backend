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
All 16+ tests validate subject normalization, qualification mapping, duplicate detection, experience constraints, email/phone verification, quality score calculations, and full pipeline execution.
