"""Routes for deal enrichment and scoring."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import UUID4, BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app import config
from app.db import get_db
from app.models.deal import Deal
from app.models.organization_membership import MemberRole
from app.schemas.deal import DealResponse
from app.services import research_service
from app.services.enrichment_service import enrich_deal
from app.services.eval_workflows import EvalExecutionError, execute_live
from app.services.llm_client import is_openrouter_service_error
from app.services.rate_limiter import AI_LIMIT, AI_WINDOW, limiter, rate_limit_headers
from app.services.scoring_service import score_deal, score_deal_deterministic
from app.utils.auth_deps import require_role, require_role_strict
from app.utils.org_scope import active_query, get_org_id

router = APIRouter(tags=["deal-intelligence"])
log = logging.getLogger(__name__)


class ResearchRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID4


@router.get('/deals/{deal_id}/research/capabilities')
def research_capabilities(
    deal_id: str, response: Response,
    principal: dict = Depends(require_role_strict(MemberRole.admin, MemberRole.editor)),
    db: Session = Depends(get_db),
):
    if principal.get('is_demo'):
        raise HTTPException(status_code=403, detail='Research unavailable in demo')
    _get_deal(deal_id, db)
    response.headers['Cache-Control'] = 'no-store'
    return research_service.capabilities(db, principal['org_id'])


@router.post('/deals/{deal_id}/research')
def research(
    deal_id: str, payload: ResearchRequest, response: Response,
    principal: dict = Depends(require_role_strict(MemberRole.admin, MemberRole.editor)),
    db: Session = Depends(get_db),
):
    if principal.get('is_demo'):
        raise HTTPException(status_code=403, detail='Research unavailable in demo')
    response.headers['Cache-Control'] = 'no-store'
    return research_service.run(db, org_id=principal['org_id'], user_id=principal['user_id'],
                                deal_id=deal_id, request_id=str(payload.request_id))


@router.get("/deals/{deal_id}/research-context")
def research_context(
    deal_id: str,
    response: Response,
    principal: dict = Depends(require_role_strict(MemberRole.admin, MemberRole.editor)),
    db: Session = Depends(get_db),
):
    """Export a bounded saved-deal snapshot; never call a model or mutate a deal."""
    if not config.AGENT_RESEARCH_CONTEXT_ENABLED:
        raise HTTPException(status_code=404, detail="Not found")
    if principal.get('is_demo'):
        raise HTTPException(status_code=403, detail="Research export unavailable in demo")
    try:
        _, evidence = execute_live(db, principal['org_id'], 'score_explanation', {'deal_id': deal_id})
    except EvalExecutionError as exc:
        if exc.code == 'workflow_input_not_found':
            raise HTTPException(status_code=404, detail='Deal not found') from None
        raise HTTPException(status_code=422, detail='Research context unavailable') from None
    response.headers['Cache-Control'] = 'no-store'
    return {'schema_version': 'research-context-v1',
            'evidence_kind': 'saved_workspace_facts_not_independently_verified',
            'evidence': [{'id': row.id, 'text': row.text} for row in evidence]}


class ScoreResponse(BaseModel):
    deal_id: str
    score: float
    risk_level: str
    breakdown: dict
    scoring_method: str
    fallback_reason: str | None = None


def _get_deal(deal_id: str, db: Session) -> Deal:
    deal = active_query(db.query(Deal), Deal).filter(Deal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    return deal


@router.post(
    "/deals/{deal_id}/enrich",
    response_model=DealResponse,
    dependencies=[Depends(require_role(MemberRole.admin, MemberRole.editor))],
)
def enrich(deal_id: str, response: Response, db: Session = Depends(get_db)):
    """Run deterministic mock enrichment on a deal, filling missing fields."""
    decision = limiter.check(key=f"ai:{get_org_id()}", limit=AI_LIMIT, window_seconds=AI_WINDOW)
    if not decision.allowed:
        raise HTTPException(
            status_code=429,
            detail="AI rate limit exceeded. Try again shortly.",
            headers=rate_limit_headers(
                prefix="X-AI-RateLimit",
                limit=AI_LIMIT,
                decision=decision,
                include_retry_after=True,
            ),
        )
    response.headers.update(
        rate_limit_headers(prefix="X-AI-RateLimit", limit=AI_LIMIT, decision=decision)
    )
    deal = _get_deal(deal_id, db)
    enriched = enrich_deal(db, deal)
    return enriched


@router.post(
    "/deals/{deal_id}/score",
    response_model=ScoreResponse,
    dependencies=[Depends(require_role(MemberRole.admin, MemberRole.editor))],
)
def score(deal_id: str, response: Response, db: Session = Depends(get_db)):
    """Score a deal 0-100 and assign a risk level."""
    decision = limiter.check(key=f"ai:{get_org_id()}", limit=AI_LIMIT, window_seconds=AI_WINDOW)
    if not decision.allowed:
        raise HTTPException(
            status_code=429,
            detail="AI rate limit exceeded. Try again shortly.",
            headers=rate_limit_headers(
                prefix="X-AI-RateLimit",
                limit=AI_LIMIT,
                decision=decision,
                include_retry_after=True,
            ),
        )
    response.headers.update(
        rate_limit_headers(prefix="X-AI-RateLimit", limit=AI_LIMIT, decision=decision)
    )
    deal = _get_deal(deal_id, db)
    try:
        result = score_deal(db, deal)
        result.setdefault("scoring_method", "deterministic")
    except Exception as exc:
        if not is_openrouter_service_error(exc):
            raise
        status_code = getattr(exc, "status_code", None)
        reason = f"OpenRouter returned HTTP {status_code}" if status_code else "OpenRouter request unavailable"
        log.warning("score_openrouter_unavailable_falling_back", extra={"reason": reason})
        result = score_deal_deterministic(db, deal)
        result.update(scoring_method="deterministic_fallback", fallback_reason=reason)
    return result
