"""Read-only adapters to installed product workflows. No model calls are simulated."""

from __future__ import annotations

import json
from types import SimpleNamespace

from sqlalchemy.orm import Session

from app.models.contact import Contact
from app.models.deal import Deal
from app.models.deal_assumptions import DealAssumptions
from app.models.deal_outputs import DealOutputs
from app.models.outreach_activity import OutreachActivity
from app.models.signal import Signal
from app.schemas.evaluation import Citation, EvalOutput, Evidence
from app.services.memo_service import generate_memo_content
from app.services.scoring_service import evaluate_deal_score
from app.utils.org_scope import active_query

LIVE_WORKFLOWS = {
    "opportunity_memo": ("rules/memo-v1", "memo-template-v1"),
    "score_explanation": ("rules/scoring-v1", "score-explanation-v1"),
}


class EvalExecutionError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _snapshot_deal(db: Session, org_id: str, deal_id: str):
    deal = active_query(db.query(Deal), Deal, org_id).filter_by(id=deal_id).first()
    if deal is None:
        raise EvalExecutionError("workflow_input_not_found")
    fields = (
        "id",
        "name",
        "address",
        "city",
        "state",
        "zip_code",
        "property_type",
        "units",
        "sq_ft",
        "year_built",
        "asking_price",
        "source",
        "status",
        "score",
        "risk_level",
    )
    data = {field: getattr(deal, field) for field in fields}
    # Scope every relationship independently, including rows with drifted ownership.
    data["outputs"] = (
        active_query(db.query(DealOutputs), DealOutputs, org_id).filter_by(deal_id=deal_id).first()
    )
    data["assumptions"] = (
        active_query(db.query(DealAssumptions), DealAssumptions, org_id)
        .filter_by(deal_id=deal_id)
        .first()
    )
    data["contacts"] = (
        active_query(db.query(Contact), Contact, org_id)
        .filter_by(deal_id=deal_id)
        .order_by(Contact.id)
        .limit(1001)
        .all()
    )
    data["activities"] = (
        active_query(db.query(OutreachActivity), OutreachActivity, org_id)
        .filter_by(deal_id=deal_id)
        .order_by(OutreachActivity.id)
        .limit(1001)
        .all()
    )
    data["signals"] = (
        active_query(db.query(Signal), Signal, org_id)
        .filter_by(deal_id=deal_id)
        .order_by(Signal.id)
        .limit(1001)
        .all()
    )
    if any(len(data[key]) > 1000 for key in ("contacts", "activities", "signals")):
        raise EvalExecutionError("context_too_large")
    return SimpleNamespace(**data)


def execute_live(
    db: Session, org_id: str, workflow: str, input_json: dict
) -> tuple[EvalOutput, list[Evidence]]:
    if workflow not in LIVE_WORKFLOWS:
        raise EvalExecutionError("workflow_not_available")
    deal_id = input_json.get("deal_id")
    if not isinstance(deal_id, str) or not deal_id or len(deal_id) > 36:
        raise EvalExecutionError("deal_id_required")
    deal = _snapshot_deal(db, org_id, deal_id)
    source_id = f"deal:{deal_id}"
    snapshot = {
        key: getattr(deal, key)
        for key in (
            "id",
            "name",
            "address",
            "city",
            "state",
            "property_type",
            "units",
            "sq_ft",
            "year_built",
            "asking_price",
            "source",
            "score",
            "status",
            "risk_level",
            "zip_code",
        )
    }
    snapshot["contacts_count"] = len(deal.contacts)
    snapshot["contact_statuses"] = [contact.status.value for contact in deal.contacts]
    snapshot["activity_types"] = [activity.activity_type.value for activity in deal.activities]
    snapshot["signals"] = [
        {"type": signal.signal_type, "description": signal.description, "severity": signal.severity}
        for signal in deal.signals
    ]
    snapshot["has_assumptions"] = deal.assumptions is not None
    snapshot["outputs"] = (
        {
            key: getattr(deal.outputs, key)
            for key in (
                "noi",
                "dscr",
                "cash_on_cash",
                "cap_rate",
                "irr",
                "equity_multiple",
                "total_project_cost",
                "equity_required",
                "annual_debt_service",
                "net_cash_flow",
                "exit_value",
                "profit",
            )
        }
        if deal.outputs
        else None
    )
    evidence_text = json.dumps(snapshot, sort_keys=True, default=str)
    if len(evidence_text) > 10000:
        raise EvalExecutionError("context_too_large")
    context = [Evidence(id=source_id, text=evidence_text)]
    if workflow == "opportunity_memo":
        text = generate_memo_content(deal)
        score = None
    else:
        scored = evaluate_deal_score(deal)
        text = json.dumps(scored, sort_keys=True)
        score = scored["score"]
    return EvalOutput(
        text=text,
        score=score,
        citations=[Citation(source_id=source_id)],
        tokens_input=0,
        tokens_output=0,
        cost_usd=0,
    ), context
