from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.models.brand import BrandAlias, BrandProfile
from app.models.ingestion import IngestionSource
from app.models.organization import Organization
from scripts import recurring_regions as job


@pytest.mark.parametrize("catalog_fails", [False, True])
def test_region_initializes_catalog_before_direct_ingestion(db, monkeypatch, catalog_fails):
    db.add(Organization(id="default-org", name="Synthetic worker", slug="synthetic-worker"))
    db.commit()
    lease = Mock()
    lease.scalar.return_value = True

    @contextmanager
    def connect():
        yield lease

    class WorkerSession:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            db.rollback()

        def __getattr__(self, key):
            return getattr(db, key)

        def get_bind(self):
            # The scheduler's advisory-lock connection is independent of ORM I/O.
            return SimpleNamespace(connect=connect, dialect=db.get_bind().dialect)

    monkeypatch.setattr(job, "SessionLocal", WorkerSession)
    monkeypatch.setattr(job, "verify", lambda entry: (1, {}))
    monkeypatch.setattr(job, "reconcile_after_refresh", lambda *args: (1, True))
    executed = Mock()

    def execute(session, source):
        assert session.query(BrandProfile).filter_by(organization_id="default-org").count() > 0
        assert session.query(BrandAlias).filter_by(organization_id="default-org").count() > 0
        executed()
        return SimpleNamespace(status="completed", id="synthetic-run", run_ids=["synthetic-run"],
                               records_seen=1, records_inserted=1, records_updated=0, records_failed=0)

    monkeypatch.setattr(job, "execute_regional_refresh", execute)
    if catalog_fails:
        def fail(*args):
            raise PermissionError("Synthetic ineffective RLS")
        monkeypatch.setattr(job, "ensure_company_catalog", fail)
        with pytest.raises(PermissionError, match="ineffective"):
            job.refresh("fort_worth_tx_civic_commercial_permits", "default-org")
        assert not executed.called and db.query(IngestionSource).count() == 0
    else:
        job.refresh("fort_worth_tx_civic_commercial_permits", "default-org")
        assert executed.call_count == 1
