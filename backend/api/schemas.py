from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator


BrandKey = Literal["qbd_mens", "qbd_womens", "yandou", "yiban"]
MatchedBy = Literal["original_sku", "sku", "none"]


class ProductPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image_path: str | None = None
    sku: str | None = None
    original_sku: str | None = None
    group_name: str | None = None
    cost: str | None = None
    factory_sku: str | None = None
    color: str | None = None
    season_category: str | None = None
    year: str | None = None
    upper_material: str | None = None
    lining_material: str | None = None
    outsole_material: str | None = None
    insole_material: str | None = None
    execution_standard: str | None = None
    heel_height: str | None = None
    shoe_width: str | None = None
    shoe_length: str | None = None
    shaft_circumference: str | None = None
    shaft_height: str | None = None
    internal_height_increase: str | None = None
    internal_height_note: str | None = None
    upper_height: str | None = None
    toe_shape: str | None = None
    closure_type: str | None = None
    shoe_box_spec: str | None = None
    first_order_time: str | None = None
    size_range: str | None = None
    product_model: str | None = None
    supplier_name: str | None = None
    color_code: str | None = None
    launch_date: str | None = None

    @model_validator(mode="after")
    def validate_not_completely_empty(self) -> ProductPayload:
        if any(
            value is not None and (not isinstance(value, str) or value.strip())
            for value in self.model_dump().values()
        ):
            return self
        raise ValueError("At least one payload field must be provided")


class ProductWriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brand: BrandKey
    payload: ProductPayload


class ImageLookupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brand: BrandKey
    original_sku: str | None = None
    sku: str | None = None

    @model_validator(mode="after")
    def validate_lookup_keys(self) -> ImageLookupRequest:
        if any(
            value is not None and (not isinstance(value, str) or value.strip())
            for value in (self.original_sku, self.sku)
        ):
            return self
        raise ValueError("Either original_sku or sku must be provided")


class BatchDeleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brand: BrandKey
    ids: list[int]
