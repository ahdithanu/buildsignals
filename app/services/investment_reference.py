"""Offline annual-2025 release reference; never fetches or joins tenant records."""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime
from pathlib import Path

from app.services import investment_inputs
from app.services.investment_model import MIN_COHORT, MODEL_VERSION, rank_metros

SCHEMA_VERSION = "investment-reference-2025-v1"
INPUT_VERSION = "official-current-vintage-2025-v2"
YEAR = 2025
MAX_ARTIFACT_BYTES = 2_000_000
MAX_MANIFEST_BYTES = 4096
REFERENCE_PATH = Path(__file__).resolve().parents[1] / "data" / "investment-reference-2025.json"
MANIFEST_PATH = REFERENCE_PATH.with_suffix(".manifest.json")
SOURCES = (
    (investment_inputs.HPI_URL, "2023,2025"),
    (investment_inputs.POP_URL, "2025 vintage; 2024-2025"),
    *((url, str(year)) for year, url in investment_inputs.PERMIT_URLS.items()),
)
_CONTEXT_FIELDS = {"name", "population_2024", "population_2025", "net_migration_2025"}


class ReferenceUnavailable(RuntimeError):
    """The packaged reference failed an offline identity or data contract check."""


def code_version() -> dict:
    """Bind the exact input transforms and ranking code, independent of Git at runtime."""
    directory = Path(__file__).resolve().parent
    return {"input_version": INPUT_VERSION, "model_version": MODEL_VERSION,
            **{name: hashlib.sha256((directory / filename).read_bytes()).hexdigest()
               for name, filename in (("inputs_sha256", "investment_inputs.py"),
                                      ("model_sha256", "investment_model.py"))}}


def _require(condition, reason):
    if not condition:
        raise ReferenceUnavailable(reason)


def _fields(value, expected):
    _require(type(value) is dict and set(value) == expected, "Invalid reference fields")


def _hash(value):
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _code(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9]{5}", value) is not None


def _integer(value, *, signed=False):
    return type(value) is int and abs(value) <= 2**63 - 1 and (signed or value >= 0)


def _context(value):
    _fields(value, _CONTEXT_FIELDS)
    name = value["name"]
    _require(isinstance(name, str) and 0 < len(name.strip()) <= 300, "Invalid metro name")
    for field in ("population_2024", "population_2025", "net_migration_2025"):
        number = value[field]
        _require(number is None or _integer(number, signed=field == "net_migration_2025"),
                 "Invalid context number")


def _timestamp(value):
    _require(isinstance(value, str), "Invalid reference capture timestamp")
    parsed = datetime.fromisoformat(value)
    _require(parsed.tzinfo is not None and parsed.utcoffset() is not None,
             "Reference capture timestamp requires timezone")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "Duplicate JSON key")
        result[key] = value
    return result


def _json(body):
    def invalid_constant(_value):
        raise ReferenceUnavailable("Nonfinite JSON number")
    return json.loads(body.decode("utf-8"), object_pairs_hook=_unique_object,
                      parse_constant=invalid_constant)


def _read(path, limit):
    with path.open("rb") as stream:
        body = stream.read(limit + 1)
    _require(0 < len(body) <= limit, "Invalid reference file size")
    return body


def _validate_snapshot(snapshot):
    _fields(snapshot, {"year", "captured_at", "snapshot_id", "provenance", "metros", "context_metros"})
    _require(type(snapshot["year"]) is int and snapshot["year"] == YEAR, "Invalid snapshot year")
    _timestamp(snapshot["captured_at"])
    _require(_hash(snapshot["snapshot_id"]), "Invalid snapshot identity")
    provenance = snapshot["provenance"]
    _require(type(provenance) is list and len(provenance) == len(SOURCES), "Invalid source count")
    for source, (url, period) in zip(provenance, SOURCES):
        _fields(source, {"url", "sha256", "captured_at", "period"})
        _require(source["url"] == url and source["period"] == period,
                 "Invalid official source provenance")
        _require(_hash(source["sha256"]), "Invalid source hash")
        _require(source["captured_at"] == snapshot["captured_at"], "Inconsistent source capture timestamp")
    context = snapshot["context_metros"]
    _require(type(context) is dict and 0 < len(context) <= 2000, "Invalid context metros")
    for cbsa, values in context.items():
        _require(_code(cbsa), "Invalid context CBSA")
        _context(values)
    metros = snapshot["metros"]
    _require(type(metros) is list and MIN_COHORT <= len(metros) <= 1000, "Invalid metro cohort size")
    counties_seen = set()
    for metro in metros:
        _fields(metro, {"cbsa", "hpi", "units", "counties"} | _CONTEXT_FIELDS)
        cbsa = metro["cbsa"]
        _require(_code(cbsa) and cbsa in context, "Invalid ranked CBSA")
        values = {field: metro[field] for field in _CONTEXT_FIELDS}
        _context(values)
        _require(values == context[cbsa], "Rank/context mismatch")
        _require(all(type(metro[field]) is int and metro[field] > 0
                     for field in ("population_2024", "population_2025")),
                 "Invalid ranked population")
        counties = metro["counties"]
        _require(type(counties) is list and 0 < len(counties) <= 1000
                 and all(_code(county) for county in counties), "Invalid constituent counties")
        _require(len(set(counties)) == len(counties) and not counties_seen.intersection(counties),
                 "Duplicate constituent county")
        counties_seen.update(counties)
        # JSON year keys are strings. Normalize only the exact supported histories.
        for field, years in (("hpi", (2023, 2025)), ("units", (2022, 2023, 2024, 2025))):
            series = metro[field]
            _fields(series, {str(year) for year in years})
            for number in series.values():
                valid = (_integer(number) if field == "units" else
                         type(number) in {int, float} and math.isfinite(number) and number > 0)
                _require(valid, "Invalid annual input number")
            metro[field] = {int(year): number for year, number in series.items()}
    identity = {"version": INPUT_VERSION, "year": YEAR,
                "sources": [{"url": p["url"], "sha256": p["sha256"]} for p in provenance],
                "metros": metros}
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True, allow_nan=False,
                                       separators=(",", ":")).encode()).hexdigest()
    _require(digest == snapshot["snapshot_id"], "Snapshot identity mismatch")
    _require(len(rank_metros(snapshot)) == len(metros), "Incomplete eligible reference cohort")


def validate_reference_artifact(artifact: bytes, manifest: bytes) -> dict:
    """Validate the entire pinned payload and return normalized inputs with mode/identity."""
    try:
        _require(0 < len(artifact) <= MAX_ARTIFACT_BYTES and 0 < len(manifest) <= MAX_MANIFEST_BYTES,
                 "Invalid reference file size")
        pin = _json(manifest)
        _fields(pin, {"schema_version", "artifact_filename", "artifact_sha256"})
        _require(pin["schema_version"] == SCHEMA_VERSION
                 and pin["artifact_filename"] == REFERENCE_PATH.name, "Invalid reference manifest")
        digest = hashlib.sha256(artifact).hexdigest()
        _require(_hash(pin["artifact_sha256"]) and pin["artifact_sha256"] == digest,
                 "Reference artifact hash mismatch")
        payload = _json(artifact)
        _fields(payload, {"schema_version", "code_version", "year", "min_cohort", "snapshot"})
        _require(payload["schema_version"] == SCHEMA_VERSION, "Unsupported reference schema version")
        _require(payload["code_version"] == code_version(), "Reference code version mismatch")
        _require(type(payload["year"]) is int and payload["year"] == YEAR, "Unsupported reference year")
        _require(type(payload["min_cohort"]) is int and payload["min_cohort"] == MIN_COHORT,
                 "Reference minimum cohort mismatch")
        snapshot = payload["snapshot"]
        _validate_snapshot(snapshot)
        return {**snapshot, "input_mode": "release_reference", "artifact_sha256": digest}
    except ReferenceUnavailable:
        raise
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
        raise ReferenceUnavailable("Invalid packaged investment reference") from None


def load_reference_snapshot() -> dict:
    """Read only the fixed app/data package; callers may cache for the image lifetime."""
    try:
        return validate_reference_artifact(_read(REFERENCE_PATH, MAX_ARTIFACT_BYTES),
                                           _read(MANIFEST_PATH, MAX_MANIFEST_BYTES))
    except OSError:
        raise ReferenceUnavailable("Packaged investment reference is unavailable") from None
