from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import re

from domain.sources import CANONICAL_COLUMNS, COLUMN_ALIASES


EMPTY_VALUES = {None, "", "-", "/"}
NA_MARKERS = {"#N/A"}



def is_empty_like(value: object) -> bool:
    if value in EMPTY_VALUES:
        return True
    if isinstance(value, str):
        text = value.strip()
        return text in EMPTY_VALUES or text.upper() in NA_MARKERS
    return False



def normalize_header(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip().replace("\n", "").replace("\r", "")



def normalize_cell(value: object) -> object:
    if is_empty_like(value):
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return format(value, "f").rstrip("0").rstrip(".")
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    text = str(value).strip()
    return text or None



def coerce_cost(value: object) -> Decimal | None:
    if is_empty_like(value):
        return None
    if isinstance(value, Decimal):
        return value
    try:
        text = str(value).replace(",", "").strip()
        if not text:
            return None
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None



def normalize_first_order_time(value: object) -> str | None:
    normalized = normalize_cell(value)
    if normalized is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(normalized).strip()
    match = re.search(r"(20\d{2})[-/年](\d{1,2})[-/月](\d{1,2})", text)
    if match:
        year, month, day = match.groups()
        return f"{year}-{int(month):02d}-{int(day):02d}"
    if re.fullmatch(r"\d{1,2}:\d{2}(:\d{2})?", text):
        return None
    return text[:10]



def derive_year_from_sheet(sheet_name: str) -> str | None:
    digits = "".join(ch for ch in sheet_name if ch.isdigit())
    if len(digits) >= 4 and digits.startswith("20"):
        return digits[:4]
    if len(digits) >= 2:
        return f"20{digits[:2]}"
    return None



def derive_season_category(sheet_name: str) -> str | None:
    if "春" in sheet_name:
        return "spring"
    if "夏" in sheet_name:
        return "summer"
    if "秋" in sheet_name:
        return "autumn"
    if "冬" in sheet_name:
        return "winter"
    return None


ADMIN_EDITABLE_COLUMNS = (
    "image_path",
    "sku",
    "original_sku",
    "group_name",
    "cost",
    "factory_sku",
    "color",
    "season_category",
    "year",
    "upper_material",
    "lining_material",
    "outsole_material",
    "insole_material",
    "execution_standard",
    "heel_height",
    "shoe_width",
    "shoe_length",
    "shaft_circumference",
    "shaft_height",
    "internal_height_increase",
    "internal_height_note",
    "upper_height",
    "toe_shape",
    "closure_type",
    "shoe_box_spec",
    "first_order_time",
)

def normalize_admin_first_order_time(value: object) -> str | None:
    normalized = normalize_first_order_time(value)
    if normalized is None:
        return None
    if re.fullmatch(r"20\d{2}-\d{2}-\d{2}", normalized):
        return normalized
    return None


ADMIN_FIELD_NORMALIZERS = {
    "cost": coerce_cost,
    "first_order_time": normalize_admin_first_order_time,
}



def normalize_admin_field(field_name: str, value: object) -> object:
    field_normalizer = ADMIN_FIELD_NORMALIZERS.get(field_name, normalize_cell)
    return field_normalizer(value)



def normalize_admin_payload(payload: dict[str, object]) -> dict[str, object]:
    normalized: dict[str, object] = {}

    for key in ADMIN_EDITABLE_COLUMNS:
        if key not in payload:
            continue
        normalized[key] = normalize_admin_field(key, payload[key])

    # Pass through extra_fields if present
    if "extra_fields" in payload:
        normalized["extra_fields"] = payload["extra_fields"]

    return normalized



def build_admin_record(
    brand: str,
    payload: dict[str, object],
    existing_metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    normalized_payload = normalize_admin_payload(payload)
    extra = normalized_payload.pop("extra_fields", None)
    record = {column: None for column in CANONICAL_COLUMNS}
    record.update(normalized_payload)
    record["extra_fields"] = extra

    metadata = {
        "source_workbook": "manual_admin",
        "source_sheet": brand,
        "source_row_number": "manual",
    }
    if existing_metadata is not None:
        metadata.update(existing_metadata)

    return {
        **record,
        **metadata,
        "raw_payload": dict(normalized_payload),
    }



def build_canonical_row(
    raw_row: dict[str, object],
    *,
    workbook_key: str,
    sheet_name: str,
    row_number: int,
    image_path: str | None,
) -> dict[str, object] | None:
    canonical = {column: None for column in CANONICAL_COLUMNS}

    for source_key, value in raw_row.items():
        normalized_key = normalize_header(source_key)
        target_key = COLUMN_ALIASES.get(normalized_key)
        if not target_key:
            continue
        canonical[target_key] = normalize_cell(value)

    if not canonical["sku"]:
        canonical["sku"] = canonical["original_sku"]

    if not canonical["original_sku"] and canonical["sku"]:
        canonical["original_sku"] = canonical["sku"]

    if not canonical["sku"] and not canonical["original_sku"]:
        return None

    if not canonical["season_category"]:
        canonical["season_category"] = derive_season_category(sheet_name)

    if not canonical["year"]:
        canonical["year"] = derive_year_from_sheet(sheet_name)

    canonical["cost"] = coerce_cost(canonical["cost"])
    canonical["first_order_time"] = normalize_first_order_time(canonical["first_order_time"])
    canonical["image_path"] = image_path

    # Collect unrecognized columns into extra_fields
    known_keys = set(COLUMN_ALIASES.values())
    extra = {}
    raw_normalized = {normalize_header(key): normalize_cell(value) for key, value in raw_row.items()}
    for key, value in raw_normalized.items():
        if key and key not in COLUMN_ALIASES and key not in known_keys:
            if value is not None and str(value).strip():
                extra[key] = value
    canonical["extra_fields"] = extra if extra else None

    return {
        **canonical,
        "source_workbook": workbook_key,
        "source_sheet": sheet_name,
        "source_row_number": str(row_number),
        "raw_payload": {normalize_header(key): normalize_cell(value) for key, value in raw_row.items()},
    }



def drop_empty_rows(rows: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    filtered: list[dict[str, object]] = []
    for row in rows:
        if any(normalize_cell(value) is not None for value in row.values()):
            filtered.append(row)
    return filtered
