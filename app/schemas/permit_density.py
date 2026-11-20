"""Bounded, complete stored-permit density contract."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CellDegrees = Literal[0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 4, 8]


class PermitDensityCell(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    latitude: float = Field(ge=-85, le=85, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    count: int = Field(ge=1)
    source_coordinate_count: int = Field(ge=0)
    estimated_count: int = Field(ge=0)
    south: float = Field(ge=-85, le=85, allow_inf_nan=False)
    west: float = Field(ge=-180, le=180, allow_inf_nan=False)
    north: float = Field(ge=-85, le=85, allow_inf_nan=False)
    east: float = Field(ge=-180, le=180, allow_inf_nan=False)

    @model_validator(mode="after")
    def reconcile(self):
        if self.count != self.source_coordinate_count + self.estimated_count:
            raise ValueError("Cell provenance counts must sum to count")
        if not (self.south < self.north and self.south <= self.latitude <= self.north
                and self.west < self.east and self.west <= self.longitude <= self.east):
            raise ValueError("Cell center must lie within nonempty bounds")
        return self


class PermitDensityResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    measured_at: datetime
    state: str | None
    total_permits: int = Field(ge=0)
    mapped_permits: int = Field(ge=0)
    unmapped_permits: int = Field(ge=0)
    source_coordinate_count: int = Field(ge=0)
    estimated_count: int = Field(ge=0)
    cell_degrees: CellDegrees
    cells: list[PermitDensityCell] = Field(max_length=2048)
    complete: Literal[True] = True

    @model_validator(mode="after")
    def reconcile(self):
        if self.total_permits != self.mapped_permits + self.unmapped_permits:
            raise ValueError("Mapped and unmapped counts must sum to total")
        if self.mapped_permits != self.source_coordinate_count + self.estimated_count:
            raise ValueError("Provenance counts must sum to mapped permits")
        for cell_field, total in (("count", self.mapped_permits),
                                  ("source_coordinate_count", self.source_coordinate_count),
                                  ("estimated_count", self.estimated_count)):
            if sum(getattr(cell, cell_field) for cell in self.cells) != total:
                raise ValueError("Cell counts must reconcile with response totals")
        if len({cell.id for cell in self.cells}) != len(self.cells):
            raise ValueError("Cell identities must be unique")
        if any(cell.north - cell.south > self.cell_degrees + 1e-9 or
               cell.east - cell.west > self.cell_degrees + 1e-9 for cell in self.cells):
            raise ValueError("Cell bounds exceed grid resolution")
        return self
