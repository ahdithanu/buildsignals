import pytest
from sqlalchemy import create_engine, delete, event, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.organization import Organization
from app.models.temporal import TemporalEvent, TemporalObservation
from app.schemas.temporal import EventCreate
from app.services.temporal_service import record_event, record_observation
from app.utils.org_scope import RequestContext, reset_current_context, set_current_context
from tests.test_migration_reversibility import _alembic
from tests.test_temporal_foundation import _payload, _seed


def test_migrated_database_enforces_immutability_and_preserves_tenant_erasure(tmp_path):
    url = f"sqlite:///{tmp_path / 'temporal-migration.db'}"
    result = _alembic("upgrade", "head", db_url=url)
    assert result.returncode == 0, result.stderr
    engine = create_engine(url)

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    with Session(engine) as db:
        token = set_current_context(RequestContext("org-a", "system"))
        try:
            entity, raw = _seed(db, org_id="org-a")
            row, _ = record_observation(db, _payload(entity, raw))
            derived, _ = record_event(db, EventCreate(observation_id=row.id, event_type="capacity.reported"))
            db.commit()
            row_id, event_id = row.id, derived.id
        finally:
            reset_current_context(token)
    for model, key in [(TemporalObservation, row_id), (TemporalEvent, event_id)]:
        with pytest.raises(IntegrityError, match="immutable"):
            with engine.begin() as connection:
                connection.execute(delete(model).where(model.id == key))
        with pytest.raises(IntegrityError, match="immutable"):
            with engine.begin() as connection:
                connection.execute(update(model).where(model.id == key).values(organization_id="other"))
    with engine.begin() as connection:
        connection.execute(delete(Organization).where(Organization.id == "org-a"))
    with Session(engine) as db:
        assert db.get(TemporalObservation, row_id) is None
        assert db.get(TemporalEvent, event_id) is None
    engine.dispose()
