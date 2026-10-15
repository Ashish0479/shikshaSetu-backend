import pytest

from app.services.l5_optimization_service import (
    ConstraintRegistry,
    L5ConfigurationError,
    L5OptimizationService,
)


def rule(rule_id, hard=True, parameters=None, policy_reference="approved-test-policy"):
    return {
        "rule_id": rule_id,
        "name": rule_id,
        "hard": hard,
        "enabled": True,
        "parameters": parameters or {},
        "description": "Test-only configured rule",
        "policy_reference": policy_reference,
        "version": "test-v1",
    }


def dataset(demand_subject="Mathematics", destination_category="urban"):
    return {
        "teachers": [
            {
                "Teacher_ID": "T1",
                "School_Code": "S1",
                "Subject": "Mathematics",
                "Eligible_Subjects": ["Mathematics"],
            },
            {
                "Teacher_ID": "T2",
                "School_Code": "S1",
                "Subject": "English",
                "Eligible_Subjects": ["English"],
            },
        ],
        "schools": [
            {
                "School_Code": "S1",
                "School_Type": "urban",
                "Latitude": 29.0,
                "Longitude": 76.0,
            },
            {
                "School_Code": "S2",
                "School_Type": destination_category,
                "Latitude": 29.01,
                "Longitude": 76.01,
                "Subject_Demand": {demand_subject: 1},
            },
        ],
    }


def test_feasible_scenario_reduces_subject_shortage_and_has_unique_plans():
    result = L5OptimizationService.generate_scenarios(
        dataset(), ConstraintRegistry([], "test-v1"), scenario_count=3
    )
    assert result["status"] == "OPTIMAL"
    assert result["scenarios"][0]["metrics"]["remaining_shortages"]["S2:mathematics"] == 0
    signatures = [scenario["scenario_id"] for scenario in result["scenarios"]]
    assert len(signatures) == len(set(signatures))


def test_teacher_is_not_assigned_twice_and_ineligible_subject_is_rejected():
    result = L5OptimizationService.generate_scenarios(
        dataset(demand_subject="Science"), ConstraintRegistry([], "test-v1")
    )
    assert result["scenarios"][0]["assignment_plan"] == []

    result = L5OptimizationService.generate_scenarios(
        dataset(), ConstraintRegistry([], "test-v1")
    )
    teacher_ids = [move["teacher_id"] for move in result["scenarios"][0]["assignment_plan"]]
    assert len(teacher_ids) == len(set(teacher_ids))


def test_l3_qualification_mismatch_is_not_reused_as_eligible():
    result = L5OptimizationService.generate_scenarios(
        dataset(),
        ConstraintRegistry([], "test-v1"),
        l3_analysis={
            "qualification_analysis": {
                "records": [
                    {"Teacher_ID": "T1", "qualification_match": "MISMATCH"},
                ]
            }
        },
    )
    assert result["scenarios"][0]["assignment_plan"] == []


def test_source_minimum_and_rural_protection_are_hard_constraints():
    registry = ConstraintRegistry(
        [
            rule("source_school_minimum_staffing", parameters={"minimum_staffing": 2}),
            rule("rural_remote_protection", parameters={"protected_categories": ["rural"]}),
        ],
        "test-v1",
    )
    protected = dataset(destination_category="urban")
    protected["schools"][0]["School_Type"] = "rural"
    result = L5OptimizationService.generate_scenarios(protected, registry)
    assert result["scenarios"][0]["assignment_plan"] == []


def test_max_distance_and_missing_coordinates_never_create_fake_distance():
    registry = ConstraintRegistry(
        [rule("max_distance", parameters={"max_distance_km": 1})], "test-v1"
    )
    result = L5OptimizationService.generate_scenarios(dataset(), registry)
    assert result["scenarios"][0]["assignment_plan"] == []
    assert any("exceeds maximum distance" in item for item in result["exclusions"])

    missing = dataset()
    missing["schools"][1].pop("Latitude")
    result = L5OptimizationService.generate_scenarios(missing, ConstraintRegistry([], "test-v1"))
    assert result["scenarios"][0]["assignment_plan"][0]["distance_km"] is None
    assert result["scenarios"][0]["metrics"]["total_distance_km"] == 0


def test_missing_policy_parameters_raise_configuration_error():
    with pytest.raises(L5ConfigurationError):
        ConstraintRegistry([rule("max_distance")], "test-v1")


def test_infeasible_status_and_l4_absence_are_explicit():
    result = L5OptimizationService.generate_scenarios(
        dataset(demand_subject="Science"),
        ConstraintRegistry([], "test-v1"),
        l4_analysis=None,
    )
    assert result["status"] == "OPTIMAL"
    assert result["future_risk_inputs_available"] is False
    assert result["limitations"]
