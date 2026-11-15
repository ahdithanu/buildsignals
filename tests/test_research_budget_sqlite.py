"""Independent physical SQLite connections prove the explicit writer lock."""
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.db import Base
from app.models.audit_log import AuditLog
from app.models.deal import Deal
from app.models.organization import Organization
from app.models.user import User
from app.services import research_service


@pytest.mark.parametrize('same_request,expected', [(True, 409), (False, 429)])
def test_independent_sqlite_writer_cannot_over_admit(tmp_path, monkeypatch, same_request, expected):
    engine = create_engine(f'sqlite:///{tmp_path}/quota.db', poolclass=NullPool,
                           connect_args={'timeout': 0})
    Base.metadata.create_all(engine)
    org, user, deal_id, request_id = (str(uuid4()) for _ in range(4))
    waiting_id = request_id if same_request else str(uuid4())
    monkeypatch.setattr(research_service.config, 'AGENT_RESEARCH_DAILY_RUN_LIMIT', 1)
    with Session(engine) as setup:
        setup.add_all([Organization(id=org, name='Synthetic SQLite quota', slug=org),
                       User(id=user, email=f'{user}@example.invalid', full_name='Synthetic researcher',
                            password_hash='!nologin')])
        setup.flush()
        setup.add(Deal(id=deal_id, organization_id=org, name='Synthetic quota deal',
                       city='Austin', state='TX', property_type='retail', asking_price=1500000))
        setup.commit()
    original = research_service._context
    blocked = []
    with Session(engine) as winner, Session(engine) as loser:
        def snapshot(db, org_id, target_deal):
            if db is winner:
                # First admission already holds BEGIN IMMEDIATE. A fresh physical
                # connection with zero busy timeout must be denied by SQLite.
                with pytest.raises(OperationalError, match='locked'):
                    research_service.reserve(loser, org_id=org, user_id=user,
                                             deal_id=deal_id, request_id=waiting_id)
                assert not loser.in_transaction()
                blocked.append(True)
            return original(db, org_id, target_deal)

        monkeypatch.setattr(research_service, '_context', snapshot)
        research_service.reserve(winner, org_id=org, user_id=user,
                                 deal_id=deal_id, request_id=request_id)
        assert not winner.in_transaction()
    try:
        with Session(engine) as verify:
            with pytest.raises(HTTPException) as failure:
                research_service.reserve(verify, org_id=org, user_id=user,
                                         deal_id=deal_id, request_id=waiting_id)
            assert failure.value.status_code == expected
            assert verify.query(AuditLog).filter_by(action='research_reserved').count() == 1
        assert blocked == [True]
    finally:
        engine.dispose()
