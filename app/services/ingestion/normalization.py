from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping, Optional

from dateutil import parser as date_parser


CANONICAL_FIELDS = {
    "source_record_id",
    "application_number",
    "permit_number",
    "approval_stage",
    "permit_type",
    "permit_subtype",
    "work_class",
    "review_type",
    "proposed_use",
    "occupancy_type",
    "status",
    "description",
    "project_name",
    "filed_at",
    "status_updated_at",
    "approved_at",
    "issued_at",
    "expires_at",
    "completed_at",
    "valuation",
    "address",
    "city",
    "state",
    "postal_code",
    "jurisdiction",
    "parcel_id",
    "latitude",
    "longitude",
    "owner_name",
    "applicant_name",
    "developer_name",
    "contractor_name",
    "contractor_license",
    "architect_name",
    "engineer_name",
    "square_feet",
    "units",
    "source_url",
}

PARCEL_CANONICAL_FIELDS = {
    "source_record_id",
    "parcel_group_id",
    "jurisdiction",
    "county",
    "state",
    "address",
    "city",
    "postal_code",
    "latitude",
    "longitude",
    "land_area_sq_ft",
    "improvement_area_sq_ft",
    "land_value",
    "improvement_value",
    "total_assessed_value",
    "land_use",
    "zoning_code",
    "owner_name",
    "owner_mailing_address",
    "last_sale_date",
    "last_sale_price",
    "tax_delinquent",
    "vacancy_indicator",
    "source_url",
    "observed_at",
}

DATE_FIELDS = {
    "filed_at",
    "status_updated_at",
    "approved_at",
    "issued_at",
    "expires_at",
    "completed_at",
}
DECIMAL_FIELDS = {"valuation", "latitude", "longitude"}
INTEGER_FIELDS = {"square_feet", "units"}
PERMIT_TEXT_FIELDS = CANONICAL_FIELDS - DATE_FIELDS - DECIMAL_FIELDS - INTEGER_FIELDS
PARCEL_DATE_FIELDS = {"last_sale_date", "observed_at"}
PARCEL_DECIMAL_FIELDS = {
    "latitude",
    "longitude",
    "land_area_sq_ft",
    "improvement_area_sq_ft",
    "land_value",
    "improvement_value",
    "total_assessed_value",
    "last_sale_price",
}
PARCEL_TEXT_FIELDS = PARCEL_CANONICAL_FIELDS - PARCEL_DATE_FIELDS - PARCEL_DECIMAL_FIELDS - {
    "tax_delinquent",
    "vacancy_indicator",
}
APPROVAL_STAGES = {"pre_approval", "approved"}
BLANKISH_NUMERIC_MARKERS = {"unknown", "n/a", "na", "none", "null"}


@dataclass(frozen=True)
class NormalizedPermit:
    source_record_id: str
    values: dict[str, Any]
    unmapped: dict[str, Any]
    fingerprint: str


@dataclass(frozen=True)
class NormalizedParcel:
    source_record_id: str
    values: dict[str, Any]
    unmapped: dict[str, Any]
    fingerprint: str


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def record_fingerprint(record: Mapping[str, Any]) -> str:
    """Return a stable content hash for idempotency and change detection."""
    encoded = json.dumps(record, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def normalize_permit(
    record: Mapping[str, Any],
    field_mapping: Mapping[str, str],
    *,
    source_record_id_field: Optional[str] = None,
    defaults: Optional[Mapping[str, Any]] = None,
) -> NormalizedPermit:
    """Map one source record into the canonical permit vocabulary.

    ``field_mapping`` maps source field names to canonical names. Unknown
    source fields remain in ``unmapped`` so no evidence is discarded.
    """
    invalid = set(field_mapping.values()) - CANONICAL_FIELDS
    if invalid:
        raise ValueError(f"Unknown canonical permit fields: {sorted(invalid)}")

    values = dict(defaults or {})
    mapped_source_fields: set[str] = set()
    for source_field, canonical_field in field_mapping.items():
        mapped_source_fields.add(source_field)
        raw_value = record.get(source_field)
        if raw_value is None or raw_value == "":
            continue
        values[canonical_field] = _coerce(canonical_field, raw_value)

    source_id = values.get("source_record_id")
    if not source_id and source_record_id_field:
        source_id = record.get(source_record_id_field)
    if source_id is None or str(source_id).strip() == "":
        raise ValueError("Source record does not contain a stable identifier")
    source_id = str(source_id).strip()
    values["source_record_id"] = source_id
    approval_stage = values.get("approval_stage")
    if approval_stage is not None and approval_stage not in APPROVAL_STAGES:
        raise ValueError(f"Unknown approval stage: {approval_stage!r}")

    unmapped = {key: value for key, value in record.items() if key not in mapped_source_fields}
    return NormalizedPermit(
        source_record_id=source_id,
        values=values,
        unmapped=unmapped,
        fingerprint=record_fingerprint(record),
    )


def normalize_parcel(
    record: Mapping[str, Any],
    field_mapping: Mapping[str, str],
    *,
    defaults: Optional[Mapping[str, Any]] = None,
) -> NormalizedParcel:
    """Map one source record into the canonical parcel and assessor vocabulary."""
    invalid = set(field_mapping.values()) - PARCEL_CANONICAL_FIELDS
    if invalid:
        raise ValueError(f"Unknown canonical parcel fields: {sorted(invalid)}")

    values = dict(defaults or {})
    mapped_source_fields: set[str] = set()
    for source_field, canonical_field in field_mapping.items():
        mapped_source_fields.add(source_field)
        raw_value = record.get(source_field)
        if raw_value is None or raw_value == "":
            continue
        if canonical_field in PARCEL_DATE_FIELDS and str(raw_value).strip() in {"0", "0.0"}:
            continue
        if canonical_field in PARCEL_DATE_FIELDS:
            values[canonical_field] = _parse_datetime(raw_value)
        elif canonical_field in PARCEL_DECIMAL_FIELDS:
            if _is_blankish_numeric(raw_value):
                continue
            values[canonical_field] = _parse_decimal(raw_value)
        elif canonical_field in PARCEL_TEXT_FIELDS:
            values[canonical_field] = " ".join(str(raw_value).strip().split())
        elif isinstance(raw_value, str):
            values[canonical_field] = " ".join(raw_value.strip().split())
        else:
            values[canonical_field] = raw_value

    source_id = values.get("source_record_id")
    if source_id is None or str(source_id).strip() == "":
        raise ValueError("Source parcel does not contain a stable identifier")
    source_id = str(source_id).strip()
    values["source_record_id"] = source_id
    latitude_value = values.get("latitude")
    longitude_value = values.get("longitude")
    if (latitude_value is None) != (longitude_value is None):
        raise ValueError("Parcel centroid latitude and longitude must be supplied together")
    if latitude_value is not None and longitude_value is not None:
        latitude = float(latitude_value)
        longitude = float(longitude_value)
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise ValueError("Parcel centroid coordinates are invalid")

    unmapped = {key: value for key, value in record.items() if key not in mapped_source_fields}
    return NormalizedParcel(
        source_record_id=source_id,
        values=values,
        unmapped=unmapped,
        fingerprint=record_fingerprint(record),
    )


def prepare_mapped_record(
    record: Mapping[str, Any],
    mappings: Iterable[Any],
) -> tuple[dict[str, Any], dict[str, str]]:
    """Apply declarative source transforms without adding vendor logic."""
    prepared = dict(record)
    field_mapping: dict[str, str] = {}
    for index, mapping in enumerate(mappings):
        if not mapping.is_active:
            continue
        source_field = mapping.source_field
        value = record.get(source_field)
        transform = mapping.transform
        options = dict(mapping.transform_options or {})

        if transform == "join_fields":
            fields = options.get("fields")
            if not isinstance(fields, list) or not fields:
                raise ValueError("join_fields requires a non-empty fields list")
            separator = str(options.get("separator", " "))
            value = separator.join(
                str(record.get(field)).strip()
                for field in fields
                if record.get(field) is not None and str(record.get(field)).strip()
            )
        elif transform == "object_path":
            path = options.get("path")
            if not isinstance(path, list) or not path:
                raise ValueError("object_path requires a non-empty path list")
            input_field = options.get("source_field", source_field)
            if not isinstance(input_field, str) or not input_field:
                raise ValueError("object_path source_field must be a field name")
            value = record.get(input_field)
            for part in path:
                if isinstance(value, Mapping):
                    value = value.get(str(part))
                    continue
                if isinstance(value, list):
                    try:
                        value = value[int(part)]
                    except (TypeError, ValueError, IndexError):
                        value = None
                    continue
                else:
                    value = None
                    break
        elif transform == "arcgis_polygon_centroid":
            axis = options.get("axis")
            if axis not in {"x", "y"}:
                raise ValueError("arcgis_polygon_centroid axis must be 'x' or 'y'")
            input_field = options.get("source_field", source_field)
            if not isinstance(input_field, str) or not input_field:
                raise ValueError("arcgis_polygon_centroid source_field must be a field name")
            centroid = _arcgis_polygon_centroid(record.get(input_field))
            value = centroid.get(axis) if centroid else None
        elif transform == "first_nonempty":
            fields = options.get("fields")
            if not isinstance(fields, list) or not fields:
                raise ValueError("first_nonempty requires a non-empty fields list")
            value = next(
                (
                    record.get(field)
                    for field in fields
                    if record.get(field) is not None and str(record.get(field)).strip()
                ),
                None,
            )
        elif transform == "value_map":
            input_field = str(options.get("field", source_field))
            values = options.get("values")
            if not isinstance(values, Mapping):
                raise ValueError("value_map requires a values object")
            raw_value = record.get(input_field)
            normalized_value = str(raw_value).strip().casefold() if raw_value is not None else None
            normalized_values = {
                str(key).strip().casefold(): mapped for key, mapped in values.items()
            }
            value = normalized_values.get(normalized_value)
        elif transform == "presence_map":
            input_field = options.get("field")
            if not isinstance(input_field, str) or not input_field:
                raise ValueError("presence_map requires a field")
            raw_value = record.get(input_field)
            present = raw_value is not None and str(raw_value).strip() != ""
            value = options.get("present" if present else "absent")
        elif transform == "conditional_map":
            cases = options.get("cases")
            if not isinstance(cases, list) or not cases:
                raise ValueError("conditional_map requires a non-empty cases list")
            default_field = options.get("default_field")
            default_fields = options.get("default_fields")
            if isinstance(default_field, str) and default_field:
                value = record.get(default_field)
            elif isinstance(default_fields, list) and default_fields:
                separator = str(options.get("separator", "|"))
                value = separator.join(
                    str(record.get(field)).strip()
                    for field in default_fields
                    if record.get(field) is not None and str(record.get(field)).strip()
                )
            else:
                value = options.get("default")
            for case in cases:
                if not isinstance(case, Mapping):
                    raise ValueError("conditional_map cases must be objects")
                input_field = case.get("field")
                operator = case.get("operator")
                if not isinstance(input_field, str) or not input_field:
                    raise ValueError("conditional_map cases require a field")
                raw_value = record.get(input_field)
                present = raw_value is not None and str(raw_value).strip() != ""
                if operator == "present":
                    matches = present
                elif operator == "in":
                    choices = case.get("values")
                    if not isinstance(choices, list):
                        raise ValueError("conditional_map 'in' cases require values")
                    normalized = str(raw_value).strip().casefold() if present else None
                    matches = normalized in {
                        str(choice).strip().casefold() for choice in choices
                    }
                else:
                    raise ValueError(f"Unsupported conditional_map operator: {operator}")
                if matches:
                    value_field = case.get("value_field")
                    value_fields = case.get("value_fields")
                    if isinstance(value_field, str) and value_field:
                        value = record.get(value_field)
                    elif isinstance(value_fields, list) and value_fields:
                        separator = str(case.get("separator", options.get("separator", "|")))
                        value = separator.join(
                            str(record.get(field)).strip()
                            for field in value_fields
                            if record.get(field) is not None
                            and str(record.get(field)).strip()
                        )
                    else:
                        value = case.get("value")
                    break
        elif transform == "unix_milliseconds":
            if value is not None and str(value).strip():
                if _is_blankish_numeric(value):
                    value = None
                else:
                    parsed = datetime.fromtimestamp(
                        float(value) / 1000,
                        tz=timezone.utc,
                    )
                    max_future_hours = options.get("max_future_hours")
                    if max_future_hours is not None:
                        if isinstance(max_future_hours, bool) or float(max_future_hours) < 0:
                            raise ValueError("unix_milliseconds max_future_hours must be non-negative")
                        if parsed > utcnow() + timedelta(hours=float(max_future_hours)):
                            parsed = None
                    value = parsed
        elif transform in {"date", "datetime"}:
            if value is not None and str(value).strip():
                parsed = _parse_datetime(value)
                max_future_hours = options.get("max_future_hours")
                if max_future_hours is not None:
                    if isinstance(max_future_hours, bool) or float(max_future_hours) < 0:
                        raise ValueError("date max_future_hours must be non-negative")
                    if parsed > utcnow() + timedelta(hours=float(max_future_hours)):
                        parsed = None
                value = parsed
            else:
                value = None
        elif transform == "yyyymm":
            raw = str(value).strip() if value is not None else ""
            if raw:
                if not raw.isdigit() or len(raw) != 6:
                    raise ValueError("yyyymm requires a six-digit year/month value")
                value = datetime.strptime(f"{raw}01", "%Y%m%d").replace(tzinfo=timezone.utc)
            else:
                value = None
        elif transform == "multiply":
            factor = options.get("factor")
            if isinstance(factor, bool) or not isinstance(factor, (int, float)):
                raise ValueError("multiply requires a numeric factor")
            if value is not None and str(value).strip():
                if _is_blankish_numeric(value):
                    value = None
                else:
                    value = _parse_decimal(value) * Decimal(str(factor))
        elif transform == "subtract_fields":
            fields = options.get("fields")
            if not isinstance(fields, list) or len(fields) != 2:
                raise ValueError("subtract_fields requires exactly two fields")
            minuend = record.get(fields[0])
            subtrahend = record.get(fields[1])
            if (
                minuend is not None and str(minuend).strip()
                and subtrahend is not None and str(subtrahend).strip()
            ):
                value = _parse_decimal(minuend) - _parse_decimal(subtrahend)
        elif transform == "sum_fields":
            fields = options.get("fields")
            if not isinstance(fields, list) or not fields:
                raise ValueError("sum_fields requires a non-empty fields list")
            operands = [
                record.get(field)
                for field in fields
                if record.get(field) is not None and str(record.get(field)).strip()
            ]
            if operands:
                value = sum((_parse_decimal(operand) for operand in operands), Decimal(0))
        elif transform == "zero_pad":
            width = options.get("width")
            if isinstance(width, bool) or not isinstance(width, int) or width < 1:
                raise ValueError("zero_pad requires a positive integer width")
            if value is not None and str(value).strip():
                numeric = _parse_decimal(value)
                if numeric != numeric.to_integral_value():
                    raise ValueError("zero_pad requires an integer-like value")
                digits = str(int(numeric))
                if len(digits) > width:
                    raise ValueError("zero_pad value exceeds configured width")
                value = digits.zfill(width)
        elif transform:
            raise ValueError(f"Unsupported source transform: {transform}")

        if (value is None or value == "") and mapping.default_value:
            value = mapping.default_value.get("value")

        mapped_key = source_field
        if transform or mapped_key in field_mapping:
            mapped_key = f"__mapped_{index}_{mapping.canonical_field}"
        prepared[mapped_key] = value
        field_mapping[mapped_key] = mapping.canonical_field

    return prepared, field_mapping


def missing_required_source_fields(
    record: Mapping[str, Any],
    mappings: Iterable[Any],
    *,
    extra_required_fields: Iterable[str] = (),
) -> list[str]:
    """Return missing raw fields required to evaluate active mappings."""
    missing: list[str] = []
    for field in extra_required_fields:
        if record.get(field) is None or record.get(field) == "":
            missing.append(field)

    for mapping in mappings:
        if not getattr(mapping, "is_active", True) or not getattr(mapping, "is_required", False):
            continue
        transform = getattr(mapping, "transform", None)
        options = dict(getattr(mapping, "transform_options", None) or {})
        if transform == "join_fields":
            fields = options.get("fields")
            if isinstance(fields, list) and fields:
                missing.extend(
                    str(field)
                    for field in fields
                    if record.get(str(field)) is None
                    or str(record.get(str(field))).strip() == ""
                )
                continue
        if transform == "first_nonempty":
            fields = options.get("fields")
            if isinstance(fields, list) and fields:
                if not any(
                    record.get(str(field)) is not None
                    and str(record.get(str(field))).strip() != ""
                    for field in fields
                ):
                    missing.append("|".join(str(field) for field in fields))
                continue

        field = getattr(mapping, "source_field")
        if record.get(field) is None or str(record.get(field)).strip() == "":
            missing.append(field)

    return sorted(set(missing))


def _arcgis_polygon_centroid(geometry: Any) -> dict[str, float] | None:
    if not isinstance(geometry, Mapping):
        return None
    rings = geometry.get("rings")
    if not isinstance(rings, list) or not rings:
        return None
    ring = rings[0]
    if not isinstance(ring, list) or len(ring) < 3:
        return None
    points: list[tuple[float, float]] = []
    for point in ring:
        if not isinstance(point, list) or len(point) < 2:
            continue
        try:
            points.append((float(point[0]), float(point[1])))
        except (TypeError, ValueError):
            continue
    if len(points) < 3:
        return None
    if points[0] != points[-1]:
        points.append(points[0])

    twice_area = 0.0
    centroid_x = 0.0
    centroid_y = 0.0
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        cross = x0 * y1 - x1 * y0
        twice_area += cross
        centroid_x += (x0 + x1) * cross
        centroid_y += (y0 + y1) * cross
    if abs(twice_area) < 1e-12:
        xs = [point[0] for point in points[:-1]]
        ys = [point[1] for point in points[:-1]]
        return {"x": sum(xs) / len(xs), "y": sum(ys) / len(ys)}
    return {
        "x": centroid_x / (3 * twice_area),
        "y": centroid_y / (3 * twice_area),
    }


def _coerce(field: str, value: Any) -> Any:
    if field in DATE_FIELDS:
        return _parse_datetime(value)
    if field in DECIMAL_FIELDS:
        return _parse_decimal(value)
    if field in INTEGER_FIELDS:
        return int(_parse_decimal(value))
    if field in PERMIT_TEXT_FIELDS:
        return " ".join(str(value).strip().split())
    if isinstance(value, str):
        return " ".join(value.strip().split())
    return value


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, datetime.min.time())
    else:
        raw = str(value).strip()
        if raw.isdigit() and len(raw) == 8:
            parsed = datetime.strptime(raw, "%Y%m%d")
        elif raw.isdigit() and int(raw) > 10_000_000_000:
            parsed = datetime.fromtimestamp(float(raw) / 1000, tz=timezone.utc)
        elif raw.isdigit() and len(raw) == 10:
            parsed = datetime.fromtimestamp(float(raw), tz=timezone.utc)
        else:
            parsed = date_parser.parse(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_source_datetime(value: Any) -> datetime:
    """Parse a publisher watermark using the canonical datetime rules."""
    return _parse_datetime(value)


def _parse_decimal(value: Any) -> Decimal:
    if isinstance(value, str):
        value = value.replace("$", "").replace(",", "").strip()
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Cannot parse numeric value {value!r}") from exc


def _is_blankish_numeric(value: Any) -> bool:
    return str(value).strip().casefold() in BLANKISH_NUMERIC_MARKERS
