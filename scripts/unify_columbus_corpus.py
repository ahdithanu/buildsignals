"""Build a NEW local, timestamp-preserving snapshot from audited Columbus shards.

This copies trusted capture evidence; it does not record fresh knowledge, backdate
observations, activate a source, or qualify historical predictive validation.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import tempfile
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import create_engine

from app.db import Base
from app.services.temporal_service import observation_series_key
from scripts.audit_columbus_corpus import audit_corpus
from scripts.columbus_corpus_capture import _file_hash
from scripts.columbus_corpus_preflight import _digest

TABLES = ("ingestion_runs", "raw_source_records", "raw_source_record_observations",
          "permit_records", "permit_events", "temporal_observations", "temporal_events")


def _rows(db, table):
    return [dict(row) for row in db.execute(f'SELECT * FROM "{table}"')]


def build_snapshot(preflight, directory, database):
    directory, database = Path(directory).resolve(), Path(database).absolute()
    sidecar = database.with_suffix(".snapshot.json")
    if any(p.exists() or p.is_symlink() for p in (database, sidecar)):
        raise FileExistsError("Snapshot database and sidecar must both be new")
    audit = audit_corpus(preflight, directory)
    if not audit["audit_passed"]:
        raise ValueError("All pinned months must pass local shard audit")
    org_id = str(uuid5(NAMESPACE_URL, "buildsignals:local:columbus-corpus-snapshot-v0"))
    source_id = str(uuid5(NAMESPACE_URL, "buildsignals:local:" + preflight["source_key"]))
    combined = {table: [] for table in TABLES}
    lineage = []
    source = organization = mappings = None
    for path in sorted(directory.rglob("*.qualification.json")):
        if not path.read_text().strip():
            continue
        receipt = json.loads(path.read_text())
        if receipt.get("status") != "completed":
            continue
        shard = path.with_suffix("").with_suffix(".db")
        before = _file_hash(shard)
        month = receipt["scope"]["settings"]["historical_qualification"]["start_inclusive"][:7]
        audited = next(row for row in audit["months"] if row["month"] == month)
        if before != audited["database_sha256"] or _file_hash(path) != audited["receipt_sha256"]:
            raise ValueError("Input evidence changed after audit")
        with sqlite3.connect(shard.resolve().as_uri() + "?mode=ro", uri=True) as db:
            db.row_factory = sqlite3.Row
            sources, orgs = _rows(db, "ingestion_sources"), _rows(db, "organizations")
            if len(sources) != 1 or len(orgs) != 1 or sources[0]["key"] != preflight["source_key"]:
                raise ValueError("Shard must contain one pinned source and one local organization")
            old_source, old_org = sources[0]["id"], orgs[0]["id"]
            if sources[0]["organization_id"] != old_org:
                raise ValueError("Source tenant mismatch")
            if any(sources[0][key] != receipt["scope"][key] for key in ("adapter", "base_url", "record_type")):
                raise ValueError("Source table disagrees with pinned receipt scope")
            shard_mappings = _rows(db, "source_field_mappings")
            if any(row["organization_id"] != old_org or row["source_id"] != old_source for row in shard_mappings):
                raise ValueError("Cross-tenant/source field mapping refused")
            if source is None:
                source, organization, mappings = sources[0], orgs[0], shard_mappings
            raw_identity = {r["id"]: r["external_record_id"] for r in _rows(db, "raw_source_records")}
            for table in TABLES:
                for row in _rows(db, table):
                    if row.get("organization_id") != old_org:
                        raise ValueError("Cross-tenant shard row refused")
                    if "source_id" in row and row["source_id"] != old_source:
                        raise ValueError("Cross-source shard row refused")
                    row["organization_id"] = org_id
                    if "source_id" in row:
                        row["source_id"] = source_id
                    if table == "temporal_observations":
                        row["series_key"] = observation_series_key(
                            row["entity_id"], source_id, raw_identity[row["raw_source_record_id"]],
                            row["attribute"], row["methodology_version"])
                    combined[table].append(row)
        if _file_hash(shard) != before or _file_hash(path) != audited["receipt_sha256"]:
            raise ValueError("Input shard changed during snapshot read")
        lineage.append({"month": receipt["scope"]["settings"]["historical_qualification"]["start_inclusive"][:7],
                        "database": str(shard.relative_to(directory)), "database_sha256": before,
                        "receipt_sha256": _file_hash(path)})
    organization.update(id=org_id, name="Columbus local evidence snapshot", slug="columbus-local-snapshot")
    source.update(id=source_id, organization_id=org_id, is_active=0)
    settings = json.loads(source["settings"]) if isinstance(source["settings"], str) else source["settings"]
    settings["schedule_mode"] = "manual"
    settings["historical_qualification"] = {
        "start_inclusive": preflight["start_inclusive"], "end_exclusive": preflight["end_exclusive"],
        "date_field": preflight["date_field"], "coverage_verified": False}
    settings["local_snapshot_import"] = {"timestamp_preservation": True, "production_admission": False}
    settings["connector"]["where"] = " OR ".join(
        "(" + month["query"]["where"] + ")" for month in preflight["months"])
    source["settings"] = json.dumps(settings, sort_keys=True)
    for row in mappings:
        row.update(organization_id=org_id, source_id=source_id)
    combined = {"organizations": [organization], "ingestion_sources": [source],
                "source_field_mappings": mappings, **combined}
    for table, rows in combined.items():
        key = "raw_source_record_id" if table == "raw_source_record_observations" else "id"
        rows.sort(key=lambda row: row[key])
        if len({r[key] for r in rows}) != len(rows):
            raise ValueError("Evidence ID collision between shards")
    manifest = {"method": "columbus-local-evidence-snapshot-v0", "plan_sha256": preflight["plan_sha256"],
                "audit_evidence_sha256": audit["evidence_sha256"], "lineage": lineage,
                "counts": {table: len(rows) for table, rows in combined.items()},
                "content_sha256": _digest(combined), "coverage_verified": False,
                "organization_id": org_id, "source_id": source_id,
                "source_key": preflight["source_key"],
                "methodology_versions": sorted({row["methodology_version"] for row in combined["temporal_observations"]}),
                "attribute_counts": {attribute: sum(row["attribute"] == attribute for row in combined["temporal_observations"])
                                     for attribute in sorted({row["attribute"] for row in combined["temporal_observations"]})},
                "known_then_verified": False,
                "semantics": "Trusted local evidence copy: original IDs, payloads, hashes and capture times preserved; only local tenant/source namespaces and dependent series keys remapped. No fresh observation recorded."}
    with tempfile.TemporaryDirectory(prefix=".columbus-snapshot-", dir=database.parent) as temporary:
        temp_database = Path(temporary) / "snapshot.db"
        engine = create_engine("sqlite:///" + str(temp_database))
        try:
            Base.metadata.create_all(engine)
        finally:
            engine.dispose()
        with sqlite3.connect(temp_database) as db:
            db.execute("PRAGMA foreign_keys=ON")
            for table, rows in combined.items():
                for row in rows:
                    columns = ",".join(f'"{name}"' for name in row)
                    placeholders = ",".join("?" for _ in row)
                    db.execute(f'INSERT INTO "{table}" ({columns}) VALUES ({placeholders})', tuple(row.values()))
            if db.execute("PRAGMA foreign_key_check").fetchall():
                raise ValueError("Unified snapshot failed foreign-key check")
        manifest["database_sha256"] = _file_hash(temp_database)
        temporary_sidecar = Path(temporary) / "snapshot.json"
        temporary_sidecar.write_text(json.dumps(manifest, indent=2) + "\n")
        # Hard links publish complete files exclusively; no partially copied final database.
        os.link(temp_database, database)
        try:
            os.link(temporary_sidecar, sidecar)
        except BaseException:
            database.unlink()
            raise
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    args = parser.parse_args()
    manifest = build_snapshot(json.loads(args.preflight.read_text()), args.directory, args.database)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
