"""Local-only research admission and metadata audit; never a monetary budget."""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from agent_runtime.research import EVIDENCE_KIND, validate_bundle, validate_findings
from app import config
from app.models.audit_log import AuditLog
from app.models.organization import Organization
from app.services.audit_service import log_change
from app.services.eval_workflows import EvalExecutionError, execute_live
from app.services.research_process import run_research_process

log = logging.getLogger(__name__)
USAGE_FIELDS = {'requested_model', 'served_model', 'provider', 'latency_ms', 'prompt_tokens',
                'completion_tokens', 'total_tokens', 'cost', 'response_id'}


def _now():
    return datetime.now(timezone.utc)


def _day(now):
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


def available(db: Session) -> bool:
    executable = Path(config.AGENT_RESEARCH_PYTHON)
    return bool(
        not config.IS_DEPLOYED and config.AGENT_RESEARCH_API_ENABLED
        and config.AGENT_RESEARCH_CONTEXT_ENABLED and config.OPENROUTER_API_KEY
        and 1 <= config.AGENT_RESEARCH_DAILY_RUN_LIMIT <= 100
        and executable.is_absolute() and executable.is_file() and os.access(executable, os.X_OK)
        and db.get_bind().dialect.name in {'sqlite', 'postgresql'}
    )


def _reservations(db, org_id):
    return db.query(AuditLog).filter(
        AuditLog.organization_id == org_id, AuditLog.entity_type == 'research_run',
        AuditLog.action == 'research_reserved',
    )


def used_today(db, org_id, now):
    start, end = _day(now)
    return _reservations(db, org_id).filter(
        AuditLog.created_at >= start, AuditLog.created_at < end,
    ).count()


def capabilities(db, org_id):
    enabled = available(db)
    limit = config.AGENT_RESEARCH_DAILY_RUN_LIMIT if enabled else 0
    return {'enabled': enabled, 'daily_run_limit': limit,
            'remaining_runs': max(0, limit - used_today(db, org_id, _now())) if enabled else 0}


def _context(db, org_id, deal_id):
    try:
        _, evidence = execute_live(db, org_id, 'score_explanation', {'deal_id': deal_id})
    except EvalExecutionError as exc:
        code = 404 if exc.code == 'workflow_input_not_found' else 422
        raise HTTPException(status_code=code, detail='Research context unavailable') from None
    bundle = {'schema_version': 'research-context-v1', 'evidence_kind': EVIDENCE_KIND,
              'evidence': [{'id': row.id, 'text': row.text} for row in evidence]}
    try:
        validate_bundle(bundle)
    except ValueError:
        raise HTTPException(status_code=422, detail='Research context unavailable') from None
    return bundle


def _lock_organization(db, org_id):
    if db.new or db.dirty or db.deleted:
        raise ValueError('pending_session_writes')
    # Discard only this route's read transaction before acquiring an authoritative lock.
    db.rollback()
    dialect = db.get_bind().dialect.name
    if dialect == 'sqlite':
        db.connection().exec_driver_sql('BEGIN IMMEDIATE')
    elif dialect == 'postgresql':
        db.execute(text("SET LOCAL lock_timeout = '5s'"))
        db.execute(text("SET LOCAL statement_timeout = '10s'"))
    else:
        raise ValueError('unsupported_database')
    org = db.scalar(select(Organization).where(
        Organization.id == org_id, Organization.is_active.is_(True),
    ).with_for_update().execution_options(populate_existing=True))
    if org is None:
        raise HTTPException(status_code=404, detail='Organization unavailable')


def reserve(db, *, org_id, user_id, deal_id, request_id):
    """Commit a nonrefundable attempt before dispatch; callers never retry dispatch."""
    try:
        _lock_organization(db, org_id)
        now = _now()  # UTC day must be measured after any lock wait.
        if _reservations(db, org_id).filter(AuditLog.request_id == request_id).first():
            raise HTTPException(status_code=409, detail='This research request was already attempted')
        if used_today(db, org_id, now) >= config.AGENT_RESEARCH_DAILY_RUN_LIMIT:
            _, end = _day(now)
            raise HTTPException(status_code=429, detail='Daily research run limit reached',
                                headers={'Retry-After': str(max(1, math.ceil((end - now).total_seconds())))})
        bundle = _context(db, org_id, deal_id)
        digest = hashlib.sha256(json.dumps(bundle, sort_keys=True).encode()).hexdigest()
        run_id = str(uuid4())
        row = log_change(db, 'research_run', run_id, 'research_reserved', actor_id=user_id,
                         organization_id=org_id, request_id=request_id,
                         new_values={'deal_id': deal_id, 'context_sha256': digest,
                                     'policy': 'local-count-limit-v1',
                                     'daily_run_limit': config.AGENT_RESEARCH_DAILY_RUN_LIMIT})
        row.created_at = now
        db.commit()
        return run_id, bundle
    except BaseException:
        db.rollback()
        raise


def validate_result(value, bundle):
    fields = {'schema_version', 'model_generated', 'research_only', 'evidence_kind',
              'context_authenticity', 'stages', 'usage', 'limitations'}
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError('invalid_result_fields')
    if (value['schema_version'] != 'research-output-v1' or value['model_generated'] is not True
            or value['research_only'] is not True or value['evidence_kind'] != EVIDENCE_KIND
            or value['context_authenticity'] != 'not_verified_by_local_runner'):
        raise ValueError('invalid_result_version')
    evidence = validate_bundle(bundle)
    stages, usage = value['stages'], value['usage']
    if not isinstance(stages, list) or len(stages) != 2 or not isinstance(usage, list) or len(usage) != 2:
        raise ValueError('invalid_stage_count')
    for stage, name in zip(stages, ('Evidence analyst', 'Diligence reviewer')):
        if not isinstance(stage, dict) or set(stage) != {'stage', 'findings'} or stage['stage'] != name:
            raise ValueError('invalid_stage')
        validate_findings(json.dumps(stage['findings'], allow_nan=False), evidence)
    for receipt in usage:
        if not isinstance(receipt, dict) or set(receipt) != USAGE_FIELDS:
            raise ValueError('invalid_usage_fields')
        for key in ('requested_model', 'served_model', 'provider', 'response_id'):
            item = receipt[key]
            if item is None and key != 'requested_model':
                continue
            if not isinstance(item, str) or not 1 <= len(item) <= 200 or not item.isprintable():
                raise ValueError('invalid_usage_text')
        for key in ('latency_ms', 'prompt_tokens', 'completion_tokens', 'total_tokens'):
            item = receipt[key]
            if item is None and key != 'latency_ms':
                continue
            if type(item) is not int or not 0 <= item <= 10**9:
                raise ValueError('invalid_usage_number')
        cost = receipt['cost']
        if cost is not None and (type(cost) not in (int, float) or not math.isfinite(cost) or cost < 0):
            raise ValueError('invalid_usage_cost')
    limits = value['limitations']
    if (not isinstance(limits, list) or not 1 <= len(limits) <= 10
            or any(not isinstance(item, str) or not 1 <= len(item) <= 500 for item in limits)):
        raise ValueError('invalid_limitations')
    return value


def _unavailable():
    return HTTPException(status_code=503, detail={
        'error': 'research_unavailable', 'message': 'Research is temporarily unavailable.'},
        headers={'Retry-After': '60'})


def run(db, *, org_id, user_id, deal_id, request_id):
    if not available(db):
        raise HTTPException(status_code=404, detail='Not found')
    try:
        run_id, bundle = reserve(db, org_id=org_id, user_id=user_id, deal_id=deal_id,
                                 request_id=request_id)
    except HTTPException:
        raise
    except Exception:
        log.warning('research_admission_failed')
        raise _unavailable() from None
    result = None
    reason = 'runtime_or_validation_failure'
    try:
        result = validate_result(run_research_process(
            bundle, python_executable=config.AGENT_RESEARCH_PYTHON,
            api_key=config.OPENROUTER_API_KEY, primary_model=config.OPENROUTER_PRIMARY_MODEL,
            fallback_models=config.OPENROUTER_FALLBACK_MODELS,
        ), bundle)
    except Exception:
        log.warning('research_run_failed', extra={'reason': reason})
    try:
        metadata = {'status': 'completed' if result is not None else 'failed'}
        if result is None:
            metadata['reason'] = reason
        else:
            metadata['usage'] = [{k: v for k, v in row.items() if k != 'response_id'}
                                 for row in result['usage']]
        log_change(db, 'research_run', run_id,
                   'research_completed' if result is not None else 'research_failed',
                   actor_id=user_id, organization_id=org_id, request_id=request_id,
                   new_values=metadata)
        db.commit()
    except Exception:
        db.rollback()
        log.warning('research_outcome_audit_failed')
        raise _unavailable() from None
    if result is None:
        raise _unavailable()
    return {'run_id': run_id, 'result': result}
