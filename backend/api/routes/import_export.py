from __future__ import annotations

import io
import urllib.parse
import unicodedata
from collections.abc import Iterator

from fastapi import APIRouter, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import desc, or_, select

from api.excel_export import DEFAULT_WIDTH_BY_HEADER, style_excel_worksheet
from api.fine_table_cache import clear_fine_table_cache
from api.routes.images import get_image_matcher, image_url_for
from domain.excluded_skus import is_excluded_sku, not_excluded_sku_condition
from domain.gj_schema import GJ_MERGED_PRODUCT_INFO_TABLE
from domain.sources import CANONICAL_COLUMNS, COLUMN_ALIASES, TABLE_NAMES
from domain.schema import PRODUCT_TABLES
from domain.vip_schema import JST_PRODUCT_PROFILE_TABLE
from storage.product_repository import apply_jst_product_costs
from transform.rows import build_admin_record, normalize_admin_field

router = APIRouter()

EXPORT_LABELS = {
    "image_path": "图片",
    "sku": "货号",
    "original_sku": "原始货号",
    "group_name": "组别",
    "product_level": "商品等级",
    "cost": "成本",
    "factory_sku": "工厂货号",
    "color": "颜色",
    "season_category": "季节分类",
    "year": "年份",
    "upper_material": "鞋面材质",
    "lining_material": "内里材质",
    "outsole_material": "大底材质",
    "insole_material": "鞋垫材质",
    "execution_standard": "执行标准",
    "heel_height": "跟高",
    "shoe_width": "鞋宽",
    "shoe_length": "鞋长",
    "shaft_circumference": "筒围",
    "shaft_height": "筒高",
    "internal_height_increase": "内增高",
    "internal_height_note": "内增高备注",
    "upper_height": "鞋帮",
    "toe_shape": "鞋头款式",
    "closure_type": "闭合方式",
    "shoe_box_spec": "鞋盒规格",
    "first_order_time": "首单时间",
    "size_range": "尺码段",
    "product_model": "产品型号",
    "supplier_name": "供应商名",
    "color_code": "颜色代码",
    "launch_date": "上市时间",
}

EXPORT_COLUMNS = [c for c in CANONICAL_COLUMNS if c != "image_path"]
CN_TO_FIELD = {cn: en for cn, en in COLUMN_ALIASES.items() if en in EXPORT_COLUMNS}
SIZE_EXPORT_MODE = "with_sizes"
SIZE_EXPORT_HEADERS = [
    "商品编码",
    "款式编码",
    "商品名",
    "颜色名称",
    "尺码条码",
    "鞋面材质",
    "品名",
    "执行标准",
    "产品型号",
    "内里材质",
    "大底材质",
    "鞋垫材质",
    "原始货号",
    "供应商商品款号",
    "品牌",
    "颜色及规格",
    "分类",
    "成本价",
    "LOGO",
]
LOOKUP_CHUNK_SIZE = 2000

BRAND_LABELS = {
    "cbanner_mens": "千百度男鞋",
    "cbanner_womens": "千百度女鞋",
    "yandou": "烟斗",
    "eblan": "伊伴",
    "all": "总览",
}


def _iter_all_export_rows(repository) -> Iterator[tuple[str, list[object]]]:
    with repository.engine.connect() as connection:
        for brand in TABLE_NAMES:
            table = PRODUCT_TABLES[brand]
            statement = (
                select(*(table.c[column] for column in EXPORT_COLUMNS))
                .where(not_excluded_sku_condition(table.c.sku, table.c.original_sku))
                .order_by(desc(table.c.id))
            )
            rows = connection.execution_options(stream_results=True).execute(statement)
            batch: list[dict[str, object]] = []
            for row in rows.mappings():
                batch.append(dict(row))
                if len(batch) >= LOOKUP_CHUNK_SIZE:
                    apply_jst_product_costs(repository.engine, batch)
                    for item in batch:
                        yield brand, [item.get(column) for column in EXPORT_COLUMNS]
                    batch = []
            if batch:
                apply_jst_product_costs(repository.engine, batch)
                for item in batch:
                    yield brand, [item.get(column) for column in EXPORT_COLUMNS]


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _display_width(value: object) -> int:
    width = 0
    for char in _cell_text(value):
        width += 2 if unicodedata.east_asian_width(char) in {"F", "W", "A"} else 1
    return width


def _excel_cell_value(value: object) -> object:
    if isinstance(value, str):
        return ILLEGAL_CHARACTERS_RE.sub("", value)
    return value


def _export_all_products(repository) -> StreamingResponse:
    headers = ["品牌"] + [EXPORT_LABELS.get(c, c) for c in EXPORT_COLUMNS]
    wb = Workbook(write_only=True)
    ws = wb.create_sheet(title="总览")
    header_font = Font(name="宋体", size=10, bold=True)
    header_fill = PatternFill("solid", fgColor="F2F2F2")
    header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=False)
    max_width = 42
    min_width = 10
    column_widths = [max(DEFAULT_WIDTH_BY_HEADER.get(header, min_width), _display_width(header) + 2) for header in headers]

    header_cells = []
    for header in headers:
        cell = WriteOnlyCell(ws, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment
        header_cells.append(cell)
    ws.append(header_cells)

    row_count = 1
    for brand, values in _iter_all_export_rows(repository):
        row = [BRAND_LABELS.get(brand, brand)] + [_excel_cell_value(value) for value in values]
        for index, value in enumerate(row):
            column_widths[index] = max(column_widths[index], min(_display_width(value) + 2, max_width))
        ws.append(row)
        row_count += 1

    for index, width in enumerate(column_widths, start=1):
        ws.column_dimensions[get_column_letter(index)].width = max(min_width, min(width, max_width))
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{row_count}"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = urllib.parse.quote("总览.xlsx")
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


def _dict_or_empty(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _first_text(*values: object) -> str:
    for value in values:
        text = _cell_text(value)
        if text:
            return text
    return ""


def _chunk_values(values: set[str]) -> list[list[str]]:
    ordered_values = sorted(values)
    return [
        ordered_values[index:index + LOOKUP_CHUNK_SIZE]
        for index in range(0, len(ordered_values), LOOKUP_CHUNK_SIZE)
    ]


def _index_product_archive_rows(items: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    rows_by_code: dict[str, dict[str, object]] = {}
    for item in items:
        for key in ("sku", "original_sku"):
            code = _cell_text(item.get(key))
            if code and code not in rows_by_code:
                rows_by_code[code] = item
    return rows_by_code


def _load_product_archive_rows(connection, brand: str, codes: set[str]) -> dict[str, dict[str, object]]:
    table = PRODUCT_TABLES.get(brand)
    if table is None or not codes:
        return {}

    rows_by_code: dict[str, dict[str, object]] = {}
    for chunk in _chunk_values(codes):
        for row in connection.execute(
            select(table)
            .where(or_(table.c.sku.in_(chunk), table.c.original_sku.in_(chunk)))
            .order_by(desc(table.c.updated_at), desc(table.c.id))
        ).mappings():
            item = dict(row)
            for key in ("sku", "original_sku"):
                code = _cell_text(item.get(key))
                if code and code in codes and code not in rows_by_code:
                    rows_by_code[code] = item
    return rows_by_code


def _load_gj_rows(connection, codes: set[str]) -> dict[str, dict[str, object]]:
    if not codes:
        return {}

    rows_by_code: dict[str, dict[str, object]] = {}
    for chunk in _chunk_values(codes):
        for row in connection.execute(
            select(GJ_MERGED_PRODUCT_INFO_TABLE)
            .where(or_(
                GJ_MERGED_PRODUCT_INFO_TABLE.c.goods_code.in_(chunk),
                GJ_MERGED_PRODUCT_INFO_TABLE.c.original_goods_code.in_(chunk),
            ))
            .order_by(
                GJ_MERGED_PRODUCT_INFO_TABLE.c.source_date_value.desc().nulls_last(),
                desc(GJ_MERGED_PRODUCT_INFO_TABLE.c.updated_at),
                desc(GJ_MERGED_PRODUCT_INFO_TABLE.c.id),
            )
        ).mappings():
            item = dict(row)
            for key in ("goods_code", "original_goods_code"):
                code = _cell_text(item.get(key))
                if code and code in codes and code not in rows_by_code:
                    rows_by_code[code] = item
    return rows_by_code


def _load_product_profile_rows(connection, codes: set[str]) -> list[dict[str, object]]:
    if not codes:
        return []

    profiles: list[dict[str, object]] = []
    seen_ids: set[object] = set()
    for chunk in _chunk_values(codes):
        statement = (
            select(JST_PRODUCT_PROFILE_TABLE)
            .where(or_(
                JST_PRODUCT_PROFILE_TABLE.c.product_code.in_(chunk),
                JST_PRODUCT_PROFILE_TABLE.c.style_code.in_(chunk),
            ))
            .order_by(JST_PRODUCT_PROFILE_TABLE.c.style_code, JST_PRODUCT_PROFILE_TABLE.c.product_code)
        )
        for row in connection.execute(statement).mappings():
            item = dict(row)
            row_id = item.get("id") or item.get("product_code")
            if row_id in seen_ids:
                continue
            seen_ids.add(row_id)
            profiles.append(item)

    profiles.sort(key=lambda item: (
        _cell_text(item.get("style_code")),
        _cell_text(item.get("product_code")),
    ))
    return profiles


def _export_products_with_sizes(repository, brand: str, ids: str | None) -> StreamingResponse:
    if brand == "all":
        raise HTTPException(status_code=400, detail="带尺码导出请选择具体品牌")

    if ids:
        id_list = [int(i.strip()) for i in ids.split(",") if i.strip()]
        source_products = repository.get_products_by_ids(brand, id_list)
    else:
        table = repository.list_products(brand, query=None, page=1, page_size=1_000_000)
        source_products = list(table["items"])
    apply_jst_product_costs(repository.engine, source_products)

    selected_codes = {
        code
        for item in source_products
        for code in (_cell_text(item.get("sku")), _cell_text(item.get("original_sku")))
        if code
    }

    wb = Workbook()
    ws = wb.active
    brand_label = BRAND_LABELS.get(brand, brand)
    ws.title = f"{brand_label}带尺码"
    ws.append(SIZE_EXPORT_HEADERS)

    with repository.engine.connect() as connection:
        profiles = _load_product_profile_rows(connection, selected_codes)

        lookup_codes = {
            code
            for profile in profiles
            for code in (_cell_text(profile.get("style_code")), _cell_text(profile.get("product_code")))
            if code
        }
        lookup_codes.update(selected_codes)
        archive_rows = _index_product_archive_rows(source_products)
        loaded_archive_rows = _load_product_archive_rows(connection, brand, lookup_codes)
        apply_jst_product_costs(repository.engine, list(loaded_archive_rows.values()))
        archive_rows.update({
            code: item
            for code, item in loaded_archive_rows.items()
            if code not in archive_rows
        })
        gj_rows = _load_gj_rows(connection, lookup_codes)

    for profile in profiles:
        raw_payload = _dict_or_empty(profile.get("raw_payload"))
        product_code = _cell_text(profile.get("product_code"))
        style_code = _cell_text(profile.get("style_code"))
        color_name = _cell_text(profile.get("color_name"))
        size_barcode = _cell_text(profile.get("size_barcode"))
        archive = archive_rows.get(style_code) or archive_rows.get(product_code) or {}
        gj = gj_rows.get(style_code) or gj_rows.get(product_code) or {}
        archive_extra = _dict_or_empty(archive.get("extra_fields"))

        product_name = _first_text(gj.get("goods_full_name"), raw_payload.get("商品名"), raw_payload.get("商品名称"), product_code)
        category = _first_text(archive.get("group_name"), raw_payload.get("分类"))
        logo = _first_text(gj.get("brand"), raw_payload.get("LOGO"), raw_payload.get("品牌"))
        ws.append([
            product_code,
            style_code,
            product_name,
            color_name,
            size_barcode,
            _first_text(gj.get("upper_material"), archive.get("upper_material"), raw_payload.get("鞋面材质")),
            _first_text(archive_extra.get("品名"), gj.get("product_name"), raw_payload.get("品名")),
            _first_text(gj.get("execution_standard"), archive.get("execution_standard"), raw_payload.get("执行标准")),
            _first_text(raw_payload.get("产品型号"), archive.get("product_model")),
            _first_text(gj.get("lining_material"), archive.get("lining_material"), raw_payload.get("内里材质")),
            _first_text(gj.get("outsole_material"), archive.get("outsole_material"), raw_payload.get("大底材质")),
            _first_text(gj.get("insole_material"), archive.get("insole_material"), raw_payload.get("鞋垫材质")),
            _first_text(gj.get("original_goods_code"), archive.get("original_sku"), raw_payload.get("原始货号")),
            _first_text(raw_payload.get("供应商商品款号"), archive.get("factory_sku"), gj.get("factory_code")),
            _first_text(raw_payload.get("品牌"), gj.get("brand")),
            f"{color_name};{size_barcode}" if color_name or size_barcode else "",
            category,
            _first_text(archive.get("cost"), raw_payload.get("成本价"), raw_payload.get("成本")),
            logo,
        ])

    style_excel_worksheet(ws)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = urllib.parse.quote(f"{brand_label}带尺码商品档案.xlsx")
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@router.get("/export")
def export_products(
    request: Request,
    brand: str = Query(...),
    ids: str | None = Query(None),
    mode: str | None = Query(None),
):
    repository = request.app.state.repository
    if mode == SIZE_EXPORT_MODE:
        return _export_products_with_sizes(repository, brand, ids)

    if brand == "all":
        return _export_all_products(repository)

    if ids:
        id_list = [int(i.strip()) for i in ids.split(",") if i.strip()]
        items = repository.get_products_by_ids(brand, id_list)
    else:
        table = repository.list_products(brand, query=None, page=1, page_size=1_000_000)
        items = table["items"]

    wb = Workbook()
    ws = wb.active
    ws.title = BRAND_LABELS.get(brand, brand)

    headers = [EXPORT_LABELS.get(c, c) for c in EXPORT_COLUMNS]
    ws.append(headers)

    for item in items:
        row = [_excel_cell_value(item.get(c)) for c in EXPORT_COLUMNS]
        ws.append(row)

    style_excel_worksheet(ws)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    brand_label = BRAND_LABELS.get(brand, brand)
    filename = urllib.parse.quote(f"{brand_label}.xlsx")
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@router.post("/import")
async def import_products(
    request: Request,
    brand: str = Query(...),
    file: UploadFile = None,
):
    if file is None:
        raise HTTPException(status_code=400, detail="No file uploaded")

    content = await file.read()
    try:
        wb = load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid Excel file")

    ws = wb.active
    iterator = ws.iter_rows(values_only=True)
    header_row = next(iterator, None)
    if header_row is None:
        wb.close()
        raise HTTPException(status_code=400, detail="Empty file")

    from transform.rows import normalize_header

    headers = [normalize_header(h) for h in header_row]

    reverse_aliases = {}
    for cn_label, en_field in CN_TO_FIELD.items():
        reverse_aliases[cn_label] = en_field
        reverse_aliases[en_field] = en_field

    repository = request.app.state.repository
    image_matcher = get_image_matcher(request, brand)
    created = 0
    updated = 0
    imported_skus: list[str] = []

    for row in iterator:
        row_dict = {}
        for idx, cell_value in enumerate(row):
            if idx < len(headers) and headers[idx]:
                row_dict[headers[idx]] = cell_value

        payload = {}
        extra_fields = {}
        known_fields = set(CN_TO_FIELD.values()) | set(CN_TO_FIELD.keys())
        for key, value in row_dict.items():
            field = reverse_aliases.get(key)
            if field:
                payload[field] = value
            elif key and key not in known_fields:
                # Unrecognized column -> store in extra_fields
                normalized = normalize_admin_field(key, value)
                if normalized is not None and str(normalized).strip():
                    extra_fields[key] = normalized

        # Normalize sku/original_sku: handle numeric values from Excel
        raw_sku = payload.get("sku")
        if raw_sku is not None:
            if isinstance(raw_sku, float) and raw_sku.is_integer():
                payload["sku"] = str(int(raw_sku))
            else:
                payload["sku"] = str(raw_sku).strip()

        raw_orig = payload.get("original_sku")
        if raw_orig is not None:
            if isinstance(raw_orig, float) and raw_orig.is_integer():
                payload["original_sku"] = str(int(raw_orig))
            else:
                payload["original_sku"] = str(raw_orig).strip()

        if not payload.get("original_sku") and not payload.get("sku"):
            continue

        if payload.get("original_sku") and not payload.get("sku"):
            payload["sku"] = payload["original_sku"]

        if is_excluded_sku(payload.get("sku"), payload.get("original_sku")):
            continue

        if extra_fields:
            payload["extra_fields"] = extra_fields

        sku_val = str(payload.get("sku", "") or "").strip()
        original_sku_val = str(payload.get("original_sku", "") or "").strip()
        existing = repository.find_by_sku(brand, sku_val) if sku_val else None
        if existing is None and original_sku_val:
            existing = repository.find_by_original_sku(brand, original_sku_val)

        if sku_val:
            imported_skus.append(sku_val)

        # Only keep fields that have a value in the imported row
        import_fields = {}
        for key, value in payload.items():
            if key in ("sku", "extra_fields"):
                continue
            normalized = normalize_admin_field(key, value)
            if normalized is not None and str(normalized).strip():
                import_fields[key] = normalized

        # Look up image by original_sku or sku
        if image_matcher and not import_fields.get("image_path"):
            orig_val = str(payload.get("original_sku", "") or "").strip()
            sku_val_img = str(payload.get("sku", "") or "").strip()
            found_path = None
            if orig_val:
                found_path = image_matcher.find(orig_val)
            if not found_path and sku_val_img:
                found_path = image_matcher.find(sku_val_img)
            if found_path:
                import_fields["image_path"] = found_path

        if existing is not None:
            # Merge: only overwrite fields present in the imported Excel
            merged = {k: v for k, v in existing.items() if v is not None}
            merged.update(import_fields)
            # Merge extra_fields: keep existing + add new
            existing_extra = existing.get("extra_fields") or {}
            new_extra = payload.get("extra_fields") or {}
            if existing_extra or new_extra:
                merged["extra_fields"] = {**existing_extra, **new_extra}
            record = build_admin_record(brand, merged, existing_metadata={
                "source_workbook": existing["source_workbook"],
                "source_sheet": existing["source_sheet"],
                "source_row_number": existing["source_row_number"],
            })
            repository.update_product(brand, existing["id"], record)
            updated += 1
        else:
            record = build_admin_record(brand, payload)
            repository.create_product(brand, record)
            created += 1

    wb.close()
    clear_fine_table_cache()
    return {"created": created, "updated": updated, "skus": imported_skus, "message": f"导入完成：新增 {created} 条，更新 {updated} 条"}
