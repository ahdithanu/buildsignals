"""Reviewed export inventory, deliberately independent of organization deletion.

Adding a model/column to the database never opts it into a download. Unstructured
source payloads are excluded; assessment snapshots use their strict V1 schema.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session, load_only

from app.models.audit_log import AuditLog
from app.models.buildsignal import BuildSignalPublication, BuildSignalReview, BuildSignalRevision
from app.models.buy_box import BuyBox
from app.models.contact import Contact
from app.models.deal import Deal
from app.models.deal_assumptions import DealAssumptions
from app.models.deal_distribution import DealDistribution
from app.models.deal_outputs import DealOutputs
from app.models.document import Document
from app.models.graph import (
    GraphEntity,
    GraphEntityAlias,
    GraphEntityLink,
    GraphEntityMerge,
    GraphEntitySourceIdentity,
    GraphRelationship,
    GraphRelationshipEvidence,
)
from app.models.ingestion import PermitRecord
from app.models.memo import Memo
from app.models.organization import Organization
from app.models.outreach_activity import OutreachActivity
from app.models.parcel import ParcelRecord
from app.models.pipeline_event import PipelineEvent
from app.models.planning import PlanningRecord
from app.models.signal import Signal
from app.models.user import User
from app.schemas.buildsignal import BuildSignalAssessmentResponse

EXPORT_SCHEMA_VERSION = "2"
ORGANIZATION_FIELDS = ("id", "name", "slug", "is_active", "created_at", "updated_at")
USER_FIELDS = ("id", "email", "full_name", "is_active", "totp_enabled",
               "last_login_at", "created_at", "updated_at")
MEMBER_FIELDS = ("user", "role", "is_default", "joined_at", "membership_id")


@dataclass(frozen=True)
class ExportTable:
    model: type
    scope: str
    columns: tuple[str, ...]
    references: tuple[tuple[str, type], ...] = ()
    member_references: tuple[str, ...] = ()

    @property
    def name(self) -> str:
        return self.model.__tablename__

    def query(self, db: Session, org_id: str):
        return (db.query(self.model)
                .options(load_only(*(getattr(self.model, field) for field in self.columns), raiseload=True))
                .filter(self.model.organization_id == org_id).order_by(self.model.id))


_OWNERS = ("created_by", "updated_by")

# Stable order and explicit columns, including inherited tenant/ownership fields.
EXPORT_TABLES = (
    ExportTable(Deal, "deal_workflows", (
        "id", "organization_id", "name", "address", "city", "state", "zip_code",
        "property_type", "units", "sq_ft", "year_built", "asking_price", "status",
        "risk_level", "score", "source", "notes", "created_at", "updated_at",
        "deleted_at", "created_by", "updated_by",
    ), member_references=_OWNERS),
    ExportTable(DealAssumptions, "deal_workflows", (
        "id", "organization_id", "deal_id", "purchase_price", "closing_costs_pct",
        "renovation_cost", "loan_amount", "interest_rate", "loan_term_years",
        "gross_rental_income", "vacancy_pct", "opex_pct", "cap_rate_market",
        "exit_cap_rate", "hold_period_years", "rent_growth_pct", "created_at", "updated_at",
    ), (("deal_id", Deal),)),
    ExportTable(DealOutputs, "deal_workflows", (
        "id", "organization_id", "deal_id", "noi", "dscr", "cash_on_cash", "cap_rate",
        "irr", "equity_multiple", "total_project_cost", "equity_required", "annual_debt_service",
        "net_cash_flow", "exit_value", "profit", "created_at", "updated_at",
    ), (("deal_id", Deal),)),
    ExportTable(Contact, "deal_workflows", (
        "id", "organization_id", "deal_id", "name", "role", "email", "phone", "company",
        "status", "notes", "created_at", "updated_at", "deleted_at", "created_by", "updated_by",
    ), (("deal_id", Deal),), _OWNERS),
    ExportTable(OutreachActivity, "deal_workflows", (
        "id", "organization_id", "deal_id", "contact_id", "activity_type", "subject",
        "body", "follow_up_date", "completed", "created_at",
    ), (("deal_id", Deal), ("contact_id", Contact))),
    ExportTable(Signal, "deal_workflows", (
        "id", "organization_id", "deal_id", "signal_type", "source", "description",
        "severity", "created_at",
    ), (("deal_id", Deal),)),
    ExportTable(Document, "deal_workflows", (
        "id", "organization_id", "deal_id", "filename", "doc_type", "size_bytes",
        "uploaded_at", "deleted_at", "created_by", "updated_by",
    ), (("deal_id", Deal),), _OWNERS),
    ExportTable(Memo, "deal_workflows", (
        "id", "organization_id", "deal_id", "title", "content", "version", "created_at",
        "updated_at", "deleted_at", "created_by", "updated_by",
    ), (("deal_id", Deal),), _OWNERS),
    ExportTable(PipelineEvent, "deal_workflows", (
        "id", "organization_id", "deal_id", "from_stage", "to_stage", "changed_by", "created_at",
    ), (("deal_id", Deal),)),
    ExportTable(BuyBox, "deal_workflows", (
        "id", "organization_id", "user_id", "asset_type", "locations", "min_price",
        "max_price", "min_irr", "deal_type", "notes", "created_at",
    ), member_references=("user_id",)),
    ExportTable(DealDistribution, "deal_workflows", (
        "id", "organization_id", "deal_id", "recipient_name", "recipient_email",
        "sent_at", "status", "notes",
    ), (("deal_id", Deal),)),
    ExportTable(AuditLog, "audit_metadata", (
        "id", "organization_id", "entity_type", "entity_id", "action", "actor_id", "created_at",
    ), member_references=("actor_id",)),
    ExportTable(GraphEntity, "knowledge_graph", (
        "id", "organization_id", "entity_type", "display_name", "normalized_name",
        "normalized_address", "source_system", "source_id", "address", "city", "state",
        "zip_code", "confidence", "created_at", "updated_at", "last_verified_at",
    )),
    ExportTable(GraphEntityAlias, "knowledge_graph", (
        "id", "organization_id", "entity_id", "alias", "normalized_alias", "source_system",
        "source_id", "confidence", "created_at",
    ), (("entity_id", GraphEntity),)),
    ExportTable(GraphEntitySourceIdentity, "knowledge_graph", (
        "id", "organization_id", "entity_id", "source_system", "source_id", "confidence",
        "created_at", "last_verified_at",
    ), (("entity_id", GraphEntity),)),
    ExportTable(GraphEntityLink, "knowledge_graph", (
        "id", "organization_id", "entity_id", "record_type", "record_id", "source_system", "created_at",
    ), (("entity_id", GraphEntity),)),
    ExportTable(GraphEntityMerge, "knowledge_graph", (
        "id", "organization_id", "survivor_entity_id", "merged_entity_id", "entity_type",
        "merged_display_name", "reason", "created_at",
    )),
    ExportTable(GraphRelationship, "knowledge_graph", (
        "id", "organization_id", "source_entity_id", "target_entity_id", "relationship_type",
        "confidence", "source_system", "source_id", "is_current", "valid_from", "valid_to",
        "created_at", "updated_at", "last_verified_at", "verification_due_at",
    ), (("source_entity_id", GraphEntity), ("target_entity_id", GraphEntity))),
    ExportTable(GraphRelationshipEvidence, "knowledge_graph", (
        "id", "organization_id", "relationship_id", "source_system", "source_id", "source_url",
        "evidence_type", "excerpt", "observed_at", "confidence", "created_at",
    ), (("relationship_id", GraphRelationship),)),
    ExportTable(BuildSignalRevision, "saved_assessments", (
        "id", "organization_id", "signal_id", "author_id", "snapshot", "created_at",
    ), (("signal_id", Signal),), ("author_id",)),
    ExportTable(BuildSignalReview, "saved_assessments", (
        "id", "organization_id", "revision_id", "reviewer_id", "decision", "rationale", "created_at",
    ), (("revision_id", BuildSignalRevision),), ("reviewer_id",)),
    ExportTable(BuildSignalPublication, "saved_assessments", (
        "id", "organization_id", "revision_id", "actor_id", "review_id", "version", "action",
        "rationale", "created_at",
    ), (("revision_id", BuildSignalRevision), ("review_id", BuildSignalReview)), ("actor_id",)),
)

_FIELDS = {entry.model: entry.columns for entry in EXPORT_TABLES}
_FIELDS.update({Organization: ORGANIZATION_FIELDS, User: USER_FIELDS})

# Only these polymorphic link contracts are known. Normalized ingestion targets
# are ownership-checked by ID, never loaded or recursively added to the export.
LINK_TARGETS = {
    "deal": Deal, "contact": Contact, "document": Document, "signal": Signal,
    "permit": PermitRecord, "parcel": ParcelRecord, "planning": PlanningRecord,
}

EXCLUSIONS = (
    "Unlisted tables and columns are not exported; this is not a complete account copy or GDPR export.",
    "Credentials, MFA secrets, sessions, reset tokens, and operational security records are excluded.",
    "Ingestion configuration, runs, raw records, observations, and blobs are excluded.",
    "Normalized permit, parcel, planning, brand, acquisition, and onboarding tables are excluded.",
    "Graph entity/relationship attributes, evidence payloads, and merge snapshots are excluded.",
    "Document file contents and storage paths are excluded; only document metadata is exported.",
    "Audit rows contain metadata only; old_values, new_values, and request_id are excluded.",
    "User references outside current organization membership are null; no external profiles are resolved.",
    "Unknown graph link record types retain their row/type but have a null record_id.",
    "Historical graph references must resolve to this tenant's graph or merge history; otherwise export fails.",
    "Owned merge history is trusted for retired identities; current-row checks cannot prove historical ownership under RLS.",
    "This export's own audit receipt is written after serialization and is not included.",
)


def serialize(obj: Any) -> dict:
    result = {}
    for field in _FIELDS[type(obj)]:
        value = getattr(obj, field)
        if hasattr(value, "value") and hasattr(value, "name"):
            value = value.value
        elif hasattr(value, "isoformat"):
            value = value.isoformat()
        result[field] = value
    return result


def prepare_row(entry: ExportTable, row: dict, member_ids: set[str], redactions: dict) -> dict:
    for field in entry.member_references:
        if row[field] is not None and row[field] not in member_ids:
            row[field] = None
            redactions["nonmember_user_references"] += 1
    if entry.model is GraphEntityLink and row["record_type"] not in LINK_TARGETS:
        row["record_id"] = None
        redactions["unsupported_graph_link_targets"] += 1
    return row


def validate_references(db: Session, org_id: str, export: dict) -> None:
    """Fail closed on corrupt ownership without filtering rows out of the copy.

    All indexes are bounded by the shared row cap. Additional lookups project
    only IDs in batches; they cannot hydrate unbounded ingestion rows or blobs.
    """
    indexes = {entry.model: {row["id"]: row for row in export[entry.name]} for entry in EXPORT_TABLES}

    def require(model, identity):
        if identity not in indexes[model]:
            raise ValueError("Organization export reference is unavailable")
        return indexes[model][identity]

    for entry in EXPORT_TABLES:
        for row in export[entry.name]:
            for field, target in entry.references:
                if row[field] is not None:
                    require(target, row[field])

    external_targets: dict[type, set[str]] = {}
    for link in export[GraphEntityLink.__tablename__]:
        target = LINK_TARGETS.get(link["record_type"])
        if target is None:
            continue
        if target in indexes:
            require(target, link["record_id"])
        else:
            external_targets.setdefault(target, set()).add(link["record_id"])
    for model, identities in external_targets.items():
        ordered = sorted(identities)
        for offset in range(0, len(ordered), 400):
            batch = ordered[offset:offset + 400]
            found = {identity for identity, in db.query(model.id).filter(
                model.organization_id == org_id, model.id.in_(batch),
            ).limit(len(batch))}
            if found != set(batch):
                raise ValueError("Organization export link target is unavailable")

    # Merges may form a chain of retired IDs. Every chain must end at an owned
    # live entity. Do not require the intentionally deleted duplicate to exist.
    retired = {row["merged_entity_id"]: row for row in export[GraphEntityMerge.__tablename__]}
    resolved_entities = set(indexes[GraphEntity])

    def require_entity(identity):
        visited = set()
        while identity not in resolved_entities:
            if identity in visited or identity not in retired:
                raise ValueError("Organization export historical entity is unavailable")
            visited.add(identity)
            identity = retired[identity]["survivor_entity_id"]
        resolved_entities.update(visited)

    for merge in retired.values():
        require_entity(merge["survivor_entity_id"])
        if merge["merged_entity_id"] in indexes[GraphEntity]:
            raise ValueError("Organization export retired entity is still live")
    # Defense in depth for databases without RLS: reject visible foreign ID
    # collisions. Forced RLS hides those rows, so this is not ownership proof.
    # The tenant-owned merge record is the trust boundary for retired IDs.
    retired_ids = sorted(retired)
    for offset in range(0, len(retired_ids), 400):
        if db.query(GraphEntity.id).filter(
            GraphEntity.organization_id != org_id,
            GraphEntity.id.in_(retired_ids[offset:offset + 400]),
        ).limit(1).first():
            raise ValueError("Organization export retired entity is unavailable")

    for revision in export[BuildSignalRevision.__tablename__]:
        snapshot = BuildSignalAssessmentResponse.model_validate(revision["snapshot"])
        if snapshot.signal_id != revision["signal_id"]:
            raise ValueError("Organization export assessment signal mismatch")
        for citation in snapshot.citations:
            require(GraphRelationshipEvidence, citation.evidence_id)
            require(GraphRelationship, citation.relationship_id)
        for implication in snapshot.implications:
            require_entity(implication.entity_id)
            for evidence_id in implication.evidence_ids:
                require(GraphRelationshipEvidence, evidence_id)
        if snapshot.source_precondition is not None:
            for source in snapshot.source_precondition.evidence:
                require(GraphRelationshipEvidence, source.evidence_id)
                require(GraphRelationship, source.relationship_id)
                require_entity(source.source_entity_id)
                require_entity(source.target_entity_id)

    for publication in export[BuildSignalPublication.__tablename__]:
        if publication["review_id"] is not None:
            review = require(BuildSignalReview, publication["review_id"])
            if review["revision_id"] != publication["revision_id"]:
                raise ValueError("Organization export publication review mismatch")


def build_manifest(export: dict, *, row_count: int, row_cap: int, byte_cap: int, redactions: dict) -> dict:
    return {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "scope": "bounded_organization_data",
        "scopes": ["organization", "members", *dict.fromkeys(entry.scope for entry in EXPORT_TABLES)],
        "complete_account_export": False,
        "includes_soft_deleted_rows": True,
        "limits": {"total_database_rows": row_cap, "encoded_json_bytes": byte_cap,
                   "overflow": "all_or_nothing"},
        "row_count": row_count,
        "tables": {
            "organization": {"table": "organizations", "columns": list(ORGANIZATION_FIELDS), "row_count": 1},
            "members": {"tables": ["organization_memberships", "users"],
                        "fields": list(MEMBER_FIELDS),
                        "membership_columns": ["id", "user_id", "role", "is_default", "joined_at"],
                        "user_columns": list(USER_FIELDS),
                        "item_count": len(export["members"]), "row_count": 2 * len(export["members"])},
            **{entry.name: {"table": entry.name, "scope": entry.scope, "columns": list(entry.columns),
                           "row_count": len(export[entry.name])} for entry in EXPORT_TABLES},
        },
        "assessment_snapshot_schema": "1",
        "graph_link_target_tables": {kind: model.__tablename__ for kind, model in LINK_TARGETS.items()},
        "redactions": redactions,
        "exclusions": list(EXCLUSIONS),
    }
