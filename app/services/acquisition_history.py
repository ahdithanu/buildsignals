"""Store the exact bytes delivered to the analyst, not a recomputed screen."""
import hashlib

from sqlalchemy.orm import Session

from app.models.acquisition_screen import AcquisitionScreenSnapshot
from app.utils.org_scope import get_org_id


def save_screen_snapshot(db: Session, deal_id: str, author_id: str, content: str):
    row = AcquisitionScreenSnapshot(
        organization_id=get_org_id(), deal_id=deal_id, author_id=author_id,
        content=content, content_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
    )
    db.add(row)
    db.flush()
    return row


def verified_snapshot_content(row: AcquisitionScreenSnapshot) -> str:
    if hashlib.sha256(row.content.encode("utf-8")).hexdigest() != row.content_sha256:
        raise ValueError("Stored acquisition snapshot integrity check failed")
    return row.content
