from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from domain.inventory_sources import normalize_document_type


class InventorySelectionFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date_start: str | None = None
    date_end: str | None = None
    supplier: str | None = None
    suppliers: list[str] = Field(default_factory=list)
    brands: list[str] = Field(default_factory=list)
    warehouse: str | None = None
    warehouses: list[str] = Field(default_factory=list)
    document_type: str | None = None
    document_types: list[str] = Field(default_factory=list)
    exclude_document_type: str | None = None
    document_number: str | None = None
    summary: str | None = None
    original_sku: str | None = None
    product_code: str | None = None
    handler: str | None = None
    completion_status: Literal["completed", "incomplete"] | None = None

    def repository_filters(self):
        filters = self.model_dump()
        for key in ("document_type", "exclude_document_type"):
            if filters[key]:
                filters[key] = normalize_document_type(filters[key])
        filters["document_types"] = list(dict.fromkeys(
            normalize_document_type(value) for value in self.document_types if value.strip()
        ))
        return filters
