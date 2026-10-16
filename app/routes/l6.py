from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.database.mongodb import db_client
from app.models.l6_schemas import L6AskRequest, L6AskResponse, L6ReviewRequest
from app.services.rag_service import RAGService

router = APIRouter(prefix="/l6", tags=["Layer 6 Copilot"])
rag_service = RAGService()


@router.post("/ask", response_model=L6AskResponse)
async def ask_copilot(request: L6AskRequest):
    """Read-only, evidence-grounded copilot response. No authentication exists in this prototype."""
    return rag_service.answer(request.question, request.dataset_id, request.scenario_id)


@router.post("/scenarios/{scenario_id}/review")
async def review_scenario(scenario_id: str, request: L6ReviewRequest):
    """Append an advisory review event; this never executes a transfer or posting."""
    scenario = db_client.get_l5_scenario(scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found.")
    event = {
        "decision": request.decision,
        "reviewer_id": request.reviewer_id,
        "reason": request.reason,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "scenario_id": scenario_id,
        "input_snapshot_reference": scenario.get("input_snapshot_reference"),
        "constraint_registry_version": scenario.get("constraint_registry_version"),
        "solver_status": scenario.get("status"),
    }
    return db_client.append_l5_review_event(scenario_id, event)


@router.get("/scenarios/{scenario_id}/reviews")
async def get_scenario_reviews(scenario_id: str):
    if not db_client.get_l5_scenario(scenario_id):
        raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found.")
    return {"scenario_id": scenario_id, "events": db_client.get_l5_review_events(scenario_id)}
