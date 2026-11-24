"""Read-only anchor preview and explicit search precondition; never client authority."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class NearbyParcelAnchorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deal_id: str = Field(min_length=1, max_length=100)
    anchor_brand_match_id: str = Field(min_length=1, max_length=100)
    permit_id: str = Field(min_length=1, max_length=100)
    status: Literal["ready", "unavailable"]
    reason: str | None = Field(default=None, max_length=500)
    latitude: float | None = Field(default=None, strict=True, ge=-90, le=90, allow_inf_nan=False)
    longitude: float | None = Field(default=None, strict=True, ge=-180, le=180, allow_inf_nan=False)
    method: Literal["source_coordinate", "reviewed_parcel_centroid"] | None = None
    parcel_id: str | None = Field(default=None, min_length=1, max_length=100)
    relationship_id: str | None = Field(default=None, min_length=1, max_length=100)
    permit_raw_record_id: str | None = Field(default=None, min_length=1, max_length=100)
    parcel_raw_record_id: str | None = Field(default=None, min_length=1, max_length=100)
    permit_normalization_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    parcel_normalization_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_readiness(self):
        if self.status == "unavailable":
            if not self.reason or self.method is not None or self.latitude is not None or self.longitude is not None:
                raise ValueError("Unavailable anchors require a reason and no usable location")
        elif self.method is None or self.latitude is None or self.longitude is None:
            raise ValueError("Ready anchors require a labelled location")
        elif self.method == "reviewed_parcel_centroid" and not all((
            self.parcel_id, self.relationship_id, self.permit_raw_record_id,
            self.parcel_raw_record_id, self.permit_normalization_hash, self.parcel_normalization_hash,
        )):
            raise ValueError("Reviewed anchors require current parcel and review evidence")
        return self
