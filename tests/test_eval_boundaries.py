"""Regression tests for persisted payload budgets and inclusive float thresholds."""
import json

from app.schemas.evaluation import Citation, EvalOutput, Evidence, ExpectedOutput, Thresholds
from app.services.eval_scoring import result_passes, score_output
from app.services.rate_limiter import limiter


def _admin(client):
    limiter.clear()
    response = client.post("/v1/auth/register", json={
        "email": "boundary@example.com", "password": "CorrectHorseBattery42",
        "full_name": "Boundary Admin", "organization_name": "Boundary Tests",
    })
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_near_limit_case_remains_readable_after_database_adds_metadata(client):
    from app.schemas.evaluation import CaseCreate

    case = CaseCreate(name="Large input", input_json={"padding": ""},
                      expected_output=ExpectedOutput(required_phrases=["present"]))
    size = len(json.dumps(case.model_dump(mode="json")))
    case.input_json["padding"] = "x" * (99990 - size)
    assert len(json.dumps(case.model_dump(mode="json"))) == 99990
    headers = _admin(client)
    response = client.post("/v1/evals/datasets", headers=headers, json={
        "name": "Near limit", "workflow": "copilot_answer",
        "cases": [case.model_dump(mode="json")],
    })
    assert response.status_code == 201, response.text
    dataset = response.json()
    assert client.get(f"/v1/evals/datasets/{dataset['id']}", headers=headers).json() == dataset


def test_six_passing_eight_tenths_cases_do_not_fail_aggregate_gate(client):
    headers = _admin(client)
    case = {
        "name": "Threshold case", "expected_output": {"required_phrases": ["a", "b", "c", "d", "z"]},
        "retrieved_context": [{"id": "evidence", "text": "a b c d"}],
    }
    response = client.post("/v1/evals/datasets", headers=headers, json={
        "name": "Fraction boundary", "workflow": "copilot_answer", "cases": [case] * 6,
    })
    assert response.status_code == 201
    dataset = response.json()
    output = {"text": "a b c d", "citations": [{"source_id": "evidence"}]}
    response = client.post(f"/v1/evals/datasets/{dataset['id']}/runs", headers=headers, json={
        "mode": "replay", "model": "fixture", "prompt_version": "v1",
        "outputs": {case["id"]: output for case in dataset["cases"]},
    })
    assert response.status_code == 201, response.text
    run = response.json()
    assert all(result["status"] == "passed" for result in run["results"])
    assert run["summary"]["metrics"]["quality"] == 0.8
    assert run["gate_passed"] is True


def test_three_invalid_references_out_of_ten_meets_inclusive_risk_boundary():
    output = EvalOutput(text="present", citations=[Citation(source_id=str(i)) for i in range(10)])
    context = [Evidence(id=str(i), text="present") for i in range(7)]
    metrics = score_output(output, ExpectedOutput(required_phrases=["present"]), context)
    assert metrics["hallucination_risk"] == 0.3
    assert result_passes(metrics, Thresholds(
        minimum_quality=0.7, minimum_citation_accuracy=0.7,
        minimum_factual_coverage=1, maximum_hallucination_risk=0.3,
    ))
