"""Bounded company enrichment of tenant-scoped, already captured planning evidence."""
from datetime import datetime, timezone

from sqlalchemy.orm import Session, joinedload
from sqlalchemy.orm.attributes import flag_modified

from app.models.graph import GraphRelationship, GraphRelationshipType
from app.models.planning import PlanningCompanyMatch, PlanningRecord
from app.services.brand_intelligence import BrandMatchBackfillBatchResult
from app.services.demo_access import demo_read_only
from app.services.ingestion.service import _project_planning_to_graph
from app.services.planning_intelligence import enrich_planning_record
from app.utils.org_scope import active_query, get_org_id


def backfill_planning_company_matches_batch(
    db: Session,
    *,
    after_id: str | None = None,
    batch_size: int = 500,
) -> BrandMatchBackfillBatchResult:
    """Replay stored planning after catalog sync; the caller owns commit/rollback."""
    if type(batch_size) is not int or not 1 <= batch_size <= 5000:
        raise ValueError("batch_size must be between 1 and 5000")
    if after_id is not None and (not isinstance(after_id, str) or not 1 <= len(after_id) <= 36):
        raise ValueError("after_id must be a nonempty record ID of at most 36 characters")
    if demo_read_only.get():
        raise PermissionError("Demo sessions cannot replay company intelligence")

    query = active_query(db.query(PlanningRecord), PlanningRecord).options(
        joinedload(PlanningRecord.source), joinedload(PlanningRecord.latest_raw_record),
    )
    if after_id is not None:
        query = query.filter(PlanningRecord.id > after_id)
    rows = query.order_by(PlanningRecord.id).limit(batch_size + 1).with_for_update(
        of=PlanningRecord,
    ).populate_existing().all()
    records = rows[:batch_size]
    if not records:
        return BrandMatchBackfillBatchResult(0, 0, 0, 0, after_id, False)

    org_id = get_org_id()
    for record in records:
        source, raw = record.source, record.latest_raw_record
        if (source is None or raw is None or record.organization_id != org_id
                or source.organization_id != org_id or raw.organization_id != org_id
                or source.id != record.source_id or raw.source_id != record.source_id
                or source.record_type != "planning" or raw.record_type != "planning"
                or raw.external_record_id != record.external_record_id):
            raise ValueError("Stored planning provenance does not match tenant/source scope")

    created = refreshed = retracted = 0
    for record in records:
        matches_query = active_query(db.query(PlanningCompanyMatch), PlanningCompanyMatch).filter(
            PlanningCompanyMatch.planning_record_id == record.id,
        )
        existing = matches_query.with_for_update().populate_existing().all()
        previous = {match.id: match.review_status for match in existing}
        # Enrichment is not a new source observation, including the ORM update timestamp.
        with db.no_autoflush:
            flag_modified(record, "updated_at")
            detected = enrich_planning_record(db, record, record.latest_raw_record)
        detected_ids = {match.id for match in detected}
        created += len(detected_ids - previous.keys())
        refreshed += len(detected_ids & previous.keys())
        current = matches_query.options(joinedload(PlanningCompanyMatch.brand)).order_by(
            PlanningCompanyMatch.brand_id,
        ).all()
        retracted += sum(
            previous.get(match.id) == "candidate" and match.review_status == "retracted"
            for match in current
        )
        eligible = [match for match in current if match.review_status in {"candidate", "confirmed"}]
        # Positional projection keys can change; retain old edges as inactive history.
        prior_edges = active_query(db.query(GraphRelationship), GraphRelationship).filter(
            GraphRelationship.source_system == record.source.key,
            GraphRelationship.relationship_type == GraphRelationshipType.related_to,
            GraphRelationship.attributes["planning_record_id"].as_string() == record.id,
            GraphRelationship.attributes["role"].as_string().in_(
                ("tracked_company", "applicant", "owner", "developer"),
            ),
            GraphRelationship.is_current.is_(True),
        ).with_for_update().populate_existing().all()
        retired_at = datetime.now(timezone.utc)
        for edge in prior_edges:
            edge.is_current = False
            edge.valid_to = retired_at
        _project_planning_to_graph(db, record.source, record, record.latest_raw_record, eligible)

    db.flush()
    return BrandMatchBackfillBatchResult(
        scanned=len(records), matches_created=created, matches_refreshed=refreshed,
        matches_retracted=retracted, next_cursor=records[-1].id, has_more=len(rows) > batch_size,
    )
