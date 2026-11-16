"""Read-only stored inventory, separate from catalog availability and ranked leads."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CoverageKind = Literal["all", "permit", "planning", "parcel"]
RecordKind = Literal["permit", "planning", "parcel"]
LocationMethod = Literal["source_coordinate", "census_address_range_estimate"]


class CoverageCounts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    permit_count: int = Field(ge=0)
    planning_count: int = Field(ge=0)
    parcel_count: int = Field(ge=0)
    mapped_count: int = Field(ge=0)
    unmapped_count: int = Field(ge=0)


class CoverageState(CoverageCounts):
    state: str
    label: str
    latitude: float | None = Field(default=None, ge=-85, le=85, allow_inf_nan=False)
    longitude: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)


class CoverageGroup(CoverageState):
    id: str
    jurisdiction: str | None


class MapCoverageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    measured_at: datetime
    totals: CoverageCounts
    states: list[CoverageState] = Field(max_length=52)
    groups: list[CoverageGroup] = Field(max_length=100)
    grouping: Literal["state", "jurisdiction"]
    total_groups: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0, le=100000)
    next_offset: int | None
    previous_offset: int | None
    truncated: bool


class MapInventoryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: RecordKind
    title: str
    address: str | None
    city: str | None
    state: str
    jurisdiction: str
    latitude: float | None = Field(default=None, ge=-85, le=85, allow_inf_nan=False)
    longitude: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)
    location_method: LocationMethod | None


class MapRecordsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[MapInventoryRecord] = Field(max_length=100)
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0, le=100000)
    next_offset: int | None
    previous_offset: int | None
