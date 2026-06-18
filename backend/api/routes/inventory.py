from __future__ import annotations

import io
import urllib.parse
from collections import defaultdict
from decimal import Decimal
from datetime import datetime, timedelta

import xlrd
from fastapi import APIRouter, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook
from sqlalchemy import desc, or_, select as sa_select

from domain.color_barcode_schema import COLOR_BARCODE_TABLE
from domain.gj_schema import GJ_MERGED_PRODUCT_INFO_TABLE
from domain.inventory_sources import (
    DOCUMENT_TYPES,
    normalize_document_type,
    INVENTORY_CANONICAL_COLUMNS,
    INVENTORY_COLUMN_ALIASES,
    INVENTORY_DETAIL_ALIASES,
    INVENTORY_DETAIL_COLUMNS,
    INVENTORY_EXPORT_LABELS,
)
from domain.schema import PRODUCT_TABLES
from domain.vip_schema import JST_PRICE_TABLE

router = APIRouter()

CN_TO_FIELD = {cn: en for cn, en in INVENTORY_COLUMN_ALIASES.items() if en in INVENTORY_CANONICAL_COLUMNS}
DETAIL_CN_TO_FIELD = {cn: en for cn, en in INVENTORY_DETAIL_ALIASES.items() if en in INVENTORY_DETAIL_COLUMNS}

EXCEL_EPOCH = datetime(1899, 12, 30)
PURCHASE_IMPORT_TYPES = {"进货单", "进货退货单", "报溢单", "报损单", "批发销售单", "批发销售退货单", "同价调拨单"}
PURCHASE_SIZE_LABELS = ("35", "36", "37", "38", "39", "40", "41", "42", "43", "44")
PURCHASE_SIZE_CODE_MAPS = {
    "cbanner_mens": {
        "01": "38",
        "02": "39",
        "03": "40",
        "04": "41",
        "05": "42",
        "06": "43",
        "07": "44",
    },
    "cbanner_womens": {
        "01": "35",
        "02": "36",
        "03": "37",
        "04": "38",
        "05": "39",
        "06": "40",
        "07": "41",
        "08": "42",
    },
}
PURCHASE_MILLIMETER_SIZE_MAP = {
    "220": "34",
    "225": "35",
    "230": "36",
    "235": "37",
    "240": "38",
    "245": "39",
    "250": "40",
    "255": "41",
    "260": "42",
    "265": "43",
    "270": "44",
    "275": "45",
    "280": "46",
    "285": "47",
}


def _normalize_date(value: str | None) -> str | None:
    """Convert Excel serial date number to YYYY-MM-DD string. Passes through non-numeric values unchanged."""
    if not value:
        return value
    try:
        serial = float(value)
        # Only treat as Excel serial if it looks like a date number (between 1 and ~100000 days from epoch)
        if 1 <= serial <= 100000:
            return (EXCEL_EPOCH + timedelta(days=int(serial))).strftime("%Y-%m-%d")
    except (ValueError, OverflowError):
        pass
    return value


def _today_text() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _to_decimal(value: object) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    try:
        return Decimal(str(value).strip())
    except Exception:
        return Decimal("0")


def _fmt_decimal(value: Decimal) -> str:
    normalized = value.normalize()
    return str(normalized) if normalized.as_tuple().exponent < 0 else str(int(normalized))


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _purchase_import_brand(document_type: str) -> str:
    return "cbanner_womens" if "女鞋" in document_type else "cbanner_mens"


def _read_purchase_import_rows(content: bytes) -> tuple[list[dict[str, str]], str]:
    if content[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return _read_purchase_import_rows_xls(content)
    try:
        workbook = load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    except Exception as error:
        raise HTTPException(status_code=400, detail="Excel 文件格式无法读取，请使用 .xlsx/.xlsm，或确认 .xls 文件未损坏") from error
    try:
        worksheet = workbook.active
        if worksheet is None:
            return [], ""
        header_index = None
        code_index = None
        qty_index = None
        iterator = worksheet.iter_rows(values_only=True)
        for row_number, row in enumerate(iterator):
            headers = [_cell_text(value).replace("\n", "").replace("\r", "") for value in row]
            code_index = next((index for index, value in enumerate(headers) if value in {"商品编码", "货品编码"}), None)
            qty_index = next((index for index, value in enumerate(headers) if value == "数量"), None)
            if code_index is not None and qty_index is not None:
                header_index = row_number
                break
            if row_number >= 29:
                break
        if header_index is None or code_index is None or qty_index is None:
            raise HTTPException(status_code=400, detail="Excel 中需要包含 商品编码/货品编码 和 数量 列")

        parsed_rows: list[dict[str, str]] = []
        empty_streak = 0
        for row in iterator:
            product_code = _cell_text(row[code_index] if code_index < len(row) else None)
            quantity = _cell_text(row[qty_index] if qty_index < len(row) else None)
            if product_code and quantity:
                parsed_rows.append({"product_code": product_code, "quantity": quantity})
                empty_streak = 0
            elif not any(_cell_text(value) for value in row):
                empty_streak += 1
                if empty_streak >= 50:
                    break
            else:
                empty_streak = 0
        return parsed_rows, worksheet.title
    finally:
        workbook.close()


def _read_purchase_import_rows_xls(content: bytes) -> tuple[list[dict[str, str]], str]:
    try:
        workbook = xlrd.open_workbook(file_contents=content)
    except Exception as error:
        raise HTTPException(status_code=400, detail="Excel .xls 文件无法读取，请另存为 .xlsx 后重试") from error
    if workbook.nsheets == 0:
        return [], ""
    worksheet = workbook.sheet_by_index(0)
    code_index = None
    qty_index = None
    data_start_row = 0
    for row_index in range(min(worksheet.nrows, 30)):
        headers = [_cell_text(value).replace("\n", "").replace("\r", "") for value in worksheet.row_values(row_index)]
        code_index = next((index for index, value in enumerate(headers) if value in {"商品编码", "货品编码"}), None)
        qty_index = next((index for index, value in enumerate(headers) if value == "数量"), None)
        if code_index is not None and qty_index is not None:
            data_start_row = row_index + 1
            break
    if code_index is None or qty_index is None:
        raise HTTPException(status_code=400, detail="Excel 中需要包含 商品编码/货品编码 和 数量 列")

    parsed_rows: list[dict[str, str]] = []
    empty_streak = 0
    for row_index in range(data_start_row, worksheet.nrows):
        values = worksheet.row_values(row_index)
        product_code = _cell_text(values[code_index] if code_index < len(values) else None)
        quantity = _cell_text(values[qty_index] if qty_index < len(values) else None)
        if product_code and quantity:
            parsed_rows.append({"product_code": product_code, "quantity": quantity})
            empty_streak = 0
        elif not any(_cell_text(value) for value in values):
            empty_streak += 1
            if empty_streak >= 50:
                break
        else:
            empty_streak = 0
    return parsed_rows, worksheet.name


def _load_color_barcodes(connection, brand: str) -> list[tuple[str, str]]:
    rows = connection.execute(
        sa_select(COLOR_BARCODE_TABLE.c.color_barcode, COLOR_BARCODE_TABLE.c.color_name)
        .where(COLOR_BARCODE_TABLE.c.brand == brand)
    ).all()
    return sorted(
        [(str(row[0]), str(row[1])) for row in rows if row[0] and row[1]],
        key=lambda item: len(item[0]),
        reverse=True,
    )


def _split_purchase_size_code(product_code: str, brand: str) -> tuple[str, str]:
    if len(product_code) >= 3:
        size_code = product_code[-3:]
        size = PURCHASE_MILLIMETER_SIZE_MAP.get(size_code)
        if size:
            return product_code[:-3], size
    if len(product_code) >= 2:
        size_code = product_code[-2:]
        if size_code in PURCHASE_SIZE_LABELS:
            return product_code[:-2], size_code
        size = PURCHASE_SIZE_CODE_MAPS.get(brand, {}).get(size_code)
        if size:
            return product_code[:-2], size
    return product_code, ""


def _split_purchase_product_code(product_code: str, color_barcodes: list[tuple[str, str]], brand: str) -> tuple[str, str, str, str, str]:
    if len(product_code) < 3:
        return product_code, product_code, "", "", ""
    if len(product_code) >= 5:
        raw_size_code = product_code[-3:]
        size = PURCHASE_MILLIMETER_SIZE_MAP.get(raw_size_code)
        if size:
            original_sku = product_code[:-5]
            color_barcode = product_code[-5:-3]
            color_name = next((name for barcode, name in color_barcodes if barcode == color_barcode), "")
            return original_sku, original_sku, color_barcode, color_name, size
    style_color_code, size = _split_purchase_size_code(product_code, brand)
    color_barcode, color_name = _split_color_from_style_code(style_color_code, color_barcodes)
    return style_color_code, style_color_code, color_barcode, color_name, size


def _split_color_from_style_code(style_color_code: str, color_barcodes: list[tuple[str, str]]) -> tuple[str, str]:
    for color_barcode, color_name in color_barcodes:
        if style_color_code.endswith(color_barcode):
            return color_barcode, color_name
    return "", ""


def _load_purchase_product_lookup(connection, brand: str, product_codes: set[str]) -> dict[str, dict[str, object]]:
    lookup: dict[str, dict[str, object]] = {code: {} for code in product_codes if code}
    if not lookup:
        return {}

    codes = set(lookup)
    gj_statement = (
        sa_select(
            GJ_MERGED_PRODUCT_INFO_TABLE.c.goods_code,
            GJ_MERGED_PRODUCT_INFO_TABLE.c.original_goods_code,
            GJ_MERGED_PRODUCT_INFO_TABLE.c.goods_full_name,
            GJ_MERGED_PRODUCT_INFO_TABLE.c.product_name,
        )
        .where(or_(
            GJ_MERGED_PRODUCT_INFO_TABLE.c.goods_code.in_(codes),
            GJ_MERGED_PRODUCT_INFO_TABLE.c.original_goods_code.in_(codes),
        ))
        .order_by(GJ_MERGED_PRODUCT_INFO_TABLE.c.source_date_value.desc().nulls_last(), desc(GJ_MERGED_PRODUCT_INFO_TABLE.c.updated_at), desc(GJ_MERGED_PRODUCT_INFO_TABLE.c.id))
    )
    for row in connection.execute(gj_statement).mappings():
        product_name = (
            str(row.get("goods_full_name") or "").strip()
            or str(row.get("product_name") or "").strip()
            or None
        )
        for code_key in ("goods_code", "original_goods_code"):
            code = str(row.get(code_key) or "").strip()
            if code and code in lookup and product_name and not lookup[code].get("product_name"):
                lookup[code]["product_name"] = product_name

    price_statement = (
        sa_select(
            JST_PRICE_TABLE.c.goods_code,
            JST_PRICE_TABLE.c.goods_full_name,
            JST_PRICE_TABLE.c.latest_purchase_price,
            JST_PRICE_TABLE.c.preset_price,
            JST_PRICE_TABLE.c.cost_unit_price,
        )
        .where(JST_PRICE_TABLE.c.goods_code.in_(codes))
        .order_by(JST_PRICE_TABLE.c.source_date_value.desc().nulls_last(), desc(JST_PRICE_TABLE.c.updated_at), desc(JST_PRICE_TABLE.c.id))
    )
    for row in connection.execute(price_statement).mappings():
        code = str(row.get("goods_code") or "").strip()
        if not code or code not in lookup:
            continue
        price = (
            row.get("latest_purchase_price")
            or row.get("preset_price")
            or row.get("cost_unit_price")
        )
        product_name = str(row.get("goods_full_name") or "").strip()
        if product_name and not lookup[code].get("product_name"):
            lookup[code]["product_name"] = product_name
        if price not in (None, "") and not lookup[code].get("unit_price"):
            lookup[code]["unit_price"] = price

    product_table = PRODUCT_TABLES.get(brand)
    if product_table is not None:
        for row in connection.execute(
            sa_select(
                product_table.c.sku,
                product_table.c.original_sku,
                product_table.c.cost,
                product_table.c.color,
            )
            .where(or_(
                product_table.c.sku.in_(codes),
                product_table.c.original_sku.in_(codes),
            ))
            .order_by(desc(product_table.c.updated_at), desc(product_table.c.id))
        ).mappings():
            for code_key in ("sku", "original_sku"):
                code = str(row.get(code_key) or "").strip()
                if not code or code not in lookup:
                    continue
                if not lookup[code].get("unit_price") and row.get("cost") not in (None, ""):
                    lookup[code]["unit_price"] = row.get("cost")
                if not lookup[code].get("color_name"):
                    lookup[code]["color_name"] = str(row.get("color") or "").strip() or None
    return lookup


def _purchase_size_label(size_code: str, brand: str) -> str:
    if size_code in PURCHASE_SIZE_LABELS:
        return size_code
    return PURCHASE_SIZE_CODE_MAPS.get(brand, {}).get(size_code, size_code)


def _lookup_has_product_data(item: dict[str, object]) -> bool:
    return bool(item.get("_matched_product"))


def _build_purchase_detail_lookup_for_brand(connection, product_code: str, quantity: Decimal, brand: str) -> dict[str, object]:
    color_barcodes = _load_color_barcodes(connection, brand)
    raw_code = product_code.strip()
    if not raw_code:
        raise HTTPException(status_code=400, detail="货号不能为空")

    stripped_code, size = _split_purchase_size_code(raw_code, brand)
    lookup_codes = {raw_code}
    if stripped_code:
        lookup_codes.add(stripped_code)
    product_lookup = _load_purchase_product_lookup(connection, brand, lookup_codes)

    product_info = product_lookup.get(raw_code) or {}
    detail_code = raw_code
    if not product_info and stripped_code and stripped_code != raw_code:
        product_info = product_lookup.get(stripped_code) or {}
        if product_info:
            detail_code = stripped_code

    if not product_info and stripped_code != raw_code:
        detail_code = stripped_code

    color_barcode, color_name = _split_color_from_style_code(detail_code, color_barcodes)
    color_name = color_name or str(product_info.get("color_name") or "").strip()
    unit_price = _to_decimal(product_info.get("unit_price"))
    amount = quantity * unit_price if quantity and unit_price else Decimal("0")
    product_name = str(product_info.get("product_name") or "").strip()
    if not product_name:
        product_name = f"{detail_code}{color_name}" if color_name else detail_code

    size_quantities = {size: _fmt_decimal(quantity)} if size and quantity else {}
    return {
        "product_code": detail_code,
        "product_name": product_name,
        "color_spec": color_name,
        "color_barcode": color_barcode,
        "color_name": color_name,
        "quantity": _fmt_decimal(quantity) if quantity else None,
        "unit_price": _fmt_decimal(unit_price) if unit_price else None,
        "amount": _fmt_decimal(amount) if amount else None,
        "size_quantities": size_quantities,
        "_matched_product": bool(product_info),
    }


def _build_purchase_detail_lookup(connection, product_code: str, quantity: Decimal, brand: str | None = None) -> dict[str, object]:
    brands = [brand] if brand else ["cbanner_mens", "cbanner_womens"]
    fallback: dict[str, object] | None = None
    for candidate in brands:
        if not candidate:
            continue
        item = _build_purchase_detail_lookup_for_brand(connection, product_code, quantity, candidate)
        if _lookup_has_product_data(item):
            item.pop("_matched_product", None)
            return item
        if fallback is None:
            fallback = item
    item = fallback or _build_purchase_detail_lookup_for_brand(connection, product_code, quantity, "cbanner_mens")
    item.pop("_matched_product", None)
    return item


def _build_purchase_details_from_excel(
    repository,
    content: bytes,
    *,
    brand: str,
    fallback_unit_price: Decimal,
) -> tuple[list[dict[str, object]], str]:
    rows, sheet_name = _read_purchase_import_rows(content)
    if not rows:
        raise HTTPException(status_code=400, detail="Excel 中没有可导入的明细")

    with repository.engine.connect() as connection:
        color_barcodes = _load_color_barcodes(connection, brand)

    parsed_rows = []
    product_codes = set()
    for row in rows:
        raw_code = row["product_code"]
        quantity = _to_decimal(row["quantity"])
        if quantity == 0:
            continue
        sku, original_sku, color_barcode, color_name, size = _split_purchase_product_code(raw_code, color_barcodes, brand)
        parsed_rows.append({
            "raw_code": raw_code,
            "quantity": quantity,
            "sku": sku,
            "original_sku": original_sku,
            "color_barcode": color_barcode,
            "color_name": color_name,
            "size": size,
        })
        if original_sku:
            product_codes.add(original_sku)

    with repository.engine.connect() as connection:
        product_lookup = _load_purchase_product_lookup(connection, brand, product_codes)

    grouped: dict[tuple[str, str], dict[str, object]] = {}
    for row in parsed_rows:
        raw_code = row["raw_code"]
        quantity = row["quantity"]
        original_sku = row["original_sku"]
        color_barcode = row["color_barcode"]
        color_name = row["color_name"] or product_lookup.get(original_sku, {}).get("color_name") or ""
        product_info = product_lookup.get(original_sku, {})
        unit_price = _to_decimal(product_info.get("unit_price")) or fallback_unit_price
        product_name = str(product_info.get("product_name") or "").strip()
        if not product_name:
            product_name = f"{original_sku}{color_name}" if color_name else original_sku
        size = row["size"]
        key = (original_sku, color_barcode)
        item = grouped.setdefault(
            key,
            {
                "product_code": original_sku,
                "product_name": product_name,
                "color_spec": color_name,
                "color_barcode": color_barcode,
                "color_name": color_name,
                "size_quantities": defaultdict(Decimal),
                "quantity": Decimal("0"),
                "unit_price": unit_price,
                "raw_codes": [],
            },
        )
        item["quantity"] = item["quantity"] + quantity
        item["raw_codes"].append(raw_code)
        if size:
            item["size_quantities"][size] += quantity

    if not grouped:
        raise HTTPException(status_code=400, detail="Excel 中没有有效数量")

    details = []
    for item in grouped.values():
        quantity = item["quantity"]
        item_unit_price = _to_decimal(item.get("unit_price"))
        amount = quantity * item_unit_price if item_unit_price else Decimal("0")
        size_quantities = {
            size: _fmt_decimal(item["size_quantities"].get(size, Decimal("0")))
            for size in PURCHASE_SIZE_LABELS
            if item["size_quantities"].get(size, Decimal("0")) != 0
        }
        details.append({
            "product_code": item["product_code"],
            "product_name": item["product_name"],
            "color_spec": item["color_spec"],
            "color_barcode": item["color_barcode"],
            "color_name": item["color_name"],
            "quantity": _fmt_decimal(quantity),
            "unit_price": _fmt_decimal(item_unit_price) if item_unit_price else None,
            "amount": _fmt_decimal(amount) if amount else None,
            "size_quantities": size_quantities,
        })
    return details, sheet_name


@router.get("/inventory")
def list_inventory(
    request: Request,
    date_start: str | None = None,
    date_end: str | None = None,
    supplier: str | None = None,
    warehouse: str | None = None,
    document_type: str | None = None,
    summary: str | None = None,
    original_sku: str | None = None,
    product_code: str | None = None,
    handler: str | None = None,
    completion_status: str | None = None,
    page: int = 1,
    page_size: int = 20,
):
    repository = request.app.state.inventory_repository
    document_type = normalize_document_type(document_type) if document_type else None
    return repository.list_records(
        date_start=date_start,
        date_end=date_end,
        supplier=supplier,
        warehouse=warehouse,
        document_type=document_type,
        summary=summary,
        original_sku=original_sku,
        product_code=product_code,
        handler=handler,
        completion_status=completion_status,
        page=page,
        page_size=page_size,
    )


@router.get("/inventory/export")
def export_inventory(
    request: Request,
    date_start: str | None = None,
    date_end: str | None = None,
    supplier: str | None = None,
    warehouse: str | None = None,
    document_type: str | None = None,
    summary: str | None = None,
    original_sku: str | None = None,
    product_code: str | None = None,
    handler: str | None = None,
    completion_status: str | None = None,
):
    repository = request.app.state.inventory_repository
    document_type = normalize_document_type(document_type) if document_type else None
    result = repository.list_records(
        date_start=date_start,
        date_end=date_end,
        supplier=supplier,
        warehouse=warehouse,
        document_type=document_type,
        summary=summary,
        original_sku=original_sku,
        product_code=product_code,
        handler=handler,
        completion_status=completion_status,
        page=1,
        page_size=100_000,
    )
    items = result["items"]
    details = repository.list_details_for_documents([int(item["id"]) for item in items])
    records_by_id = {item["id"]: item for item in items}

    wb = Workbook()
    ws = wb.active
    ws.title = "进销存记录"

    headers = [INVENTORY_EXPORT_LABELS.get(c, c) for c in INVENTORY_CANONICAL_COLUMNS]
    ws.append(headers)

    for item in items:
        row = [item.get(c) for c in INVENTORY_CANONICAL_COLUMNS]
        ws.append(row)

    detail_ws = wb.create_sheet("单据明细")
    detail_headers = [
        "单据编号",
        "日期",
        "单据类型",
        "供应商/客户/出货仓库",
        "仓库",
        "经手人",
        "摘要",
        "货号",
        "商品全名",
        "颜色条码",
        "颜色名称",
        *PURCHASE_SIZE_LABELS,
        "数量",
        "单价",
        "金额",
    ]
    detail_ws.append(detail_headers)
    for detail in details:
        record = records_by_id.get(detail.get("document_id"), {})
        size_quantities = detail.get("size_quantities") or {}
        if not isinstance(size_quantities, dict):
            size_quantities = {}
        detail_ws.append([
            record.get("document_number") or record.get("id") or "",
            record.get("date") or "",
            record.get("document_type") or "",
            record.get("supplier") or "",
            record.get("warehouse") or "",
            record.get("handler") or "",
            record.get("summary") or "",
            detail.get("product_code") or "",
            detail.get("product_name") or "",
            detail.get("color_barcode") or "",
            detail.get("color_name") or detail.get("color_spec") or "",
            *[size_quantities.get(size, "") for size in PURCHASE_SIZE_LABELS],
            detail.get("quantity") or "",
            detail.get("unit_price") or "",
            detail.get("amount") or "",
        ])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = urllib.parse.quote("进销存数据.xlsx")
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
            "Content-Length": str(buf.getbuffer().nbytes),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )


@router.get("/inventory/ending-balance")
def get_ending_inventory(
    request: Request,
    stock_date: str,
    date_start: str | None = None,
    date_end: str | None = None,
    product_code: str | None = None,
    page: int = 1,
    page_size: int = 20,
):
    repository = request.app.state.inventory_repository
    settings = request.app.state.settings
    return repository.get_ending_inventory(
        jst_stock_root=settings.jst_stock_root,
        stock_date=stock_date,
        date_start=date_start,
        date_end=date_end,
        product_code=product_code,
        page=page,
        page_size=page_size,
    )


@router.post("/inventory/import-jst-stock")
def import_jst_stock(request: Request, stock_date: str | None = None):
    if stock_date is None:
        from datetime import datetime
        now = datetime.now()
        stock_date = f"{now.month:02d}.{now.day:02d}"
    repository = request.app.state.inventory_repository
    settings = request.app.state.settings
    return repository.import_jst_stock(
        jst_stock_root=settings.jst_stock_root,
        stock_date=stock_date,
    )


@router.post("/inventory/import-purchase")
async def import_purchase_inventory(request: Request, file: UploadFile = None):
    if file is None:
        raise HTTPException(status_code=400, detail="No file uploaded")

    form = await request.form()
    document_type = normalize_document_type(form.get("document_type"))
    if document_type not in PURCHASE_IMPORT_TYPES:
        raise HTTPException(status_code=400, detail="只支持进货单、进货退货单、报溢单、报损单、批发销售单、批发销售退货单、同价调拨单导入")
    supplier = str(form.get("supplier") or "").strip()
    warehouse = str(form.get("warehouse") or "").strip()
    handler = str(form.get("handler") or "").strip()
    summary = str(form.get("summary") or "").strip()
    date_value = _normalize_date(str(form.get("date") or "")) or _today_text()
    brand = str(form.get("brand") or "").strip() or _purchase_import_brand(document_type)
    fallback_unit_price = _to_decimal(form.get("unit_price"))

    if document_type not in {"报溢单", "报损单"} and not supplier:
        if document_type == "同价调拨单":
            raise HTTPException(status_code=400, detail="出货仓库不能为空")
        raise HTTPException(status_code=400, detail="收货客户不能为空" if document_type.startswith("批发销售") else "供货单位不能为空")
    if not warehouse:
        if document_type == "同价调拨单":
            raise HTTPException(status_code=400, detail="入货仓库不能为空")
        raise HTTPException(status_code=400, detail="发货仓库不能为空" if document_type.startswith("批发销售") else "收货仓库不能为空")
    if not handler:
        raise HTTPException(status_code=400, detail="经手人不能为空")
    if not summary:
        raise HTTPException(status_code=400, detail="摘要不能为空")

    content = await file.read()
    repository = request.app.state.inventory_repository
    details, sheet_name = _build_purchase_details_from_excel(
        repository,
        content,
        brand=brand,
        fallback_unit_price=fallback_unit_price,
    )
    total_count = sum((_to_decimal(detail.get("quantity")) for detail in details), Decimal("0"))
    total_amount = sum((_to_decimal(detail.get("amount")) for detail in details), Decimal("0"))

    doc_payload = {
        "date": date_value,
        "supplier": supplier,
        "warehouse": warehouse,
        "document_type": document_type,
        "handler": handler,
        "summary": summary,
        "total_count": _fmt_decimal(total_count),
        "amount": _fmt_decimal(total_amount) if total_amount else None,
        "source_workbook": file.filename or "",
        "source_sheet": sheet_name,
        "source_row_number": "import_purchase",
        "raw_payload": {"import_type": "purchase_detail", "brand": brand},
    }

    existing_doc = repository.get_record_by_summary(summary) if summary else None
    if existing_doc:
        raise HTTPException(status_code=400, detail=f"摘要 '{summary}' 已存在，请打开该单据明细后使用“重新导入明细”覆盖")

    doc = repository.create_record(doc_payload)
    detail_payloads = []
    for detail in details:
        detail["document_id"] = doc["id"]
        detail_payloads.append(detail)
    repository.create_details(detail_payloads, doc["id"])

    return {
        "created": 1,
        "details": len(details),
        "message": f"导入完成：新增 1 条单据，{len(details)} 条明细",
        "item": doc,
    }


@router.get("/inventory/general-customer-shops")
def list_general_customer_shops(request: Request):
    repository = request.app.state.inventory_repository
    return {"items": repository.list_general_customer_shops()}


@router.get("/inventory/general-customer-brands")
def list_general_customer_brands(request: Request):
    repository = request.app.state.inventory_repository
    return {"items": repository.list_general_customer_brands()}


@router.post("/inventory/general-customer-brands")
def create_general_customer_brand(request: Request, payload: dict):
    repository = request.app.state.inventory_repository
    name = str(payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="品牌名称不能为空")
    if repository.get_general_customer_brand_by_name(name):
        raise HTTPException(status_code=400, detail=f"品牌 '{name}' 已存在")
    return {
        "item": repository.create_general_customer_brand({
            "name": name,
        }),
        "message": "创建成功",
    }


@router.put("/inventory/general-customer-brands/{brand_id}")
def update_general_customer_brand(request: Request, brand_id: int, payload: dict):
    repository = request.app.state.inventory_repository
    name = str(payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="品牌名称不能为空")
    existing = repository.get_general_customer_brand_by_name(name)
    if existing and existing.get("id") != brand_id:
        raise HTTPException(status_code=400, detail=f"品牌 '{name}' 已存在")
    record = repository.update_general_customer_brand(brand_id, {
        "name": name,
    })
    if record is None:
        raise HTTPException(status_code=404, detail="Brand not found")
    return {"item": record, "message": "更新成功"}


@router.delete("/inventory/general-customer-brands/{brand_id}")
def delete_general_customer_brand(request: Request, brand_id: int):
    repository = request.app.state.inventory_repository
    result = repository.delete_general_customer_brand(brand_id)
    if result == "not_found":
        raise HTTPException(status_code=404, detail="Brand not found")
    return {"message": "删除成功"}


@router.post("/inventory/general-customer-shops")
def create_general_customer_shop(request: Request, payload: dict):
    repository = request.app.state.inventory_repository
    customer_name = str(payload.get("customer_name") or "").strip()
    shop_name = str(payload.get("shop_name") or "").strip()
    if not customer_name:
        raise HTTPException(status_code=400, detail="品牌名称不能为空")
    if not shop_name:
        raise HTTPException(status_code=400, detail="店铺名称不能为空")
    existing = repository.get_general_customer_shop_by_name(customer_name, shop_name)
    if existing:
        raise HTTPException(status_code=400, detail=f"店铺 '{customer_name} / {shop_name}' 已存在")
    payload["customer_name"] = customer_name
    payload["shop_name"] = shop_name
    return {"item": repository.create_general_customer_shop(payload), "message": "创建成功"}


@router.put("/inventory/general-customer-shops/{shop_id}")
def update_general_customer_shop(request: Request, shop_id: int, payload: dict):
    repository = request.app.state.inventory_repository
    payload["customer_name"] = str(payload.get("customer_name") or "").strip()
    payload["shop_name"] = str(payload.get("shop_name") or "").strip()
    record = repository.update_general_customer_shop(shop_id, payload)
    if record is None:
        raise HTTPException(status_code=404, detail="Shop not found")
    return {"item": record, "message": "更新成功"}


@router.delete("/inventory/general-customer-shops/{shop_id}")
def delete_general_customer_shop(request: Request, shop_id: int):
    repository = request.app.state.inventory_repository
    if not repository.delete_general_customer_shop(shop_id):
        raise HTTPException(status_code=404, detail="Shop not found")
    return {"message": "删除成功"}


@router.get("/inventory/detail-lookup")
def lookup_inventory_detail(
    request: Request,
    product_code: str,
    quantity: str | None = None,
    brand: str | None = None,
):
    repository = request.app.state.inventory_repository
    with repository.engine.connect() as connection:
        item = _build_purchase_detail_lookup(
            connection,
            str(product_code or ""),
            _to_decimal(quantity),
            brand,
        )
    return {"item": item}


@router.get("/inventory/{record_id}")
def get_inventory_record(request: Request, record_id: int):
    repository = request.app.state.inventory_repository
    record = repository.get_record(record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Record not found")
    return record


@router.post("/inventory")
def create_inventory_record(request: Request, payload: dict):
    repository = request.app.state.inventory_repository
    if payload.get("date"):
        payload["date"] = _normalize_date(str(payload["date"]))
    else:
        payload["date"] = _today_text()
    if "document_type" in payload:
        payload["document_type"] = normalize_document_type(payload.get("document_type"))
    summary = (payload.get("summary") or "").strip()
    if summary:
        from domain.inventory_schema import INVENTORY_TABLE
        from sqlalchemy import select as sa_select
        with repository.engine.connect() as conn:
            existing = conn.execute(
                sa_select(INVENTORY_TABLE).where(INVENTORY_TABLE.c.summary == summary)
            ).first()
            if existing:
                raise HTTPException(status_code=400, detail=f"摘要 '{summary}' 已存在")
    return {"item": repository.create_record(payload), "message": "创建成功"}


@router.put("/inventory/{record_id}")
def update_inventory_record(request: Request, record_id: int, payload: dict):
    repository = request.app.state.inventory_repository
    if payload.get("date"):
        payload["date"] = _normalize_date(str(payload["date"]))
    if "document_type" in payload:
        payload["document_type"] = normalize_document_type(payload.get("document_type"))
    record = repository.update_record(record_id, payload)
    if record is None:
        raise HTTPException(status_code=404, detail="Record not found")
    return {"item": record, "message": "更新成功"}


@router.delete("/inventory/{record_id}")
def delete_inventory_record(request: Request, record_id: int):
    repository = request.app.state.inventory_repository
    if not repository.delete_record(record_id):
        raise HTTPException(status_code=404, detail="Record not found")
    return {"message": "删除成功"}


@router.post("/inventory/batch-delete")
def batch_delete_inventory(request: Request, payload: dict):
    ids = payload.get("ids", [])
    repository = request.app.state.inventory_repository
    deleted = repository.delete_records(ids)
    return {"deleted": deleted, "message": f"已删除 {deleted} 条记录"}


@router.get("/inventory/{record_id}/details")
def list_inventory_details(request: Request, record_id: int):
    repository = request.app.state.inventory_repository
    return {"items": repository.list_details(record_id)}


@router.post("/inventory/{record_id}/details/import-replace")
async def replace_inventory_details_from_excel(request: Request, record_id: int, file: UploadFile = None):
    if file is None:
        raise HTTPException(status_code=400, detail="No file uploaded")
    repository = request.app.state.inventory_repository
    record = repository.get_record(record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Record not found")

    form = await request.form()
    document_type = normalize_document_type(record.get("document_type"))
    brand = str(form.get("brand") or "").strip() or _purchase_import_brand(document_type or "")
    fallback_unit_price = _to_decimal(form.get("unit_price"))
    content = await file.read()
    details, sheet_name = _build_purchase_details_from_excel(
        repository,
        content,
        brand=brand,
        fallback_unit_price=fallback_unit_price,
    )
    detail_payloads = []
    for detail in details:
        item = dict(detail)
        item["document_id"] = record_id
        detail_payloads.append(item)
    repository.replace_details(record_id, detail_payloads)
    repository.update_record(record_id, {
        "source_workbook": file.filename or record.get("source_workbook") or "",
        "source_sheet": sheet_name or record.get("source_sheet") or "",
        "source_row_number": "replace_details",
    })
    return {
        "updated": 1,
        "details": len(details),
        "message": f"已重新导入并覆盖 {len(details)} 条明细",
    }


@router.post("/inventory/{record_id}/details")
def create_inventory_detail(request: Request, record_id: int, payload: dict):
    repository = request.app.state.inventory_repository
    payload["document_id"] = record_id
    return {"item": repository.create_detail(payload), "message": "明细添加成功"}


@router.put("/inventory/{record_id}/details/{detail_id}")
def update_inventory_detail(request: Request, record_id: int, detail_id: int, payload: dict):
    repository = request.app.state.inventory_repository
    payload["document_id"] = record_id
    detail = repository.update_detail(detail_id, payload)
    if detail is None:
        raise HTTPException(status_code=404, detail="Detail not found")
    return {"item": detail, "message": "明细更新成功"}


@router.post("/inventory/{record_id}/details/batch-delete")
def batch_delete_inventory_details(request: Request, record_id: int, payload: dict):
    ids = payload.get("ids", [])
    if not isinstance(ids, list):
        raise HTTPException(status_code=400, detail="ids 必须是数组")
    detail_ids = []
    for value in ids:
        try:
            detail_ids.append(int(value))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="明细 ID 格式错误")
    repository = request.app.state.inventory_repository
    deleted = repository.delete_details(record_id, detail_ids)
    return {"deleted": deleted, "message": f"已删除 {deleted} 条明细"}


@router.delete("/inventory/{record_id}/details/{detail_id}")
def delete_inventory_detail(request: Request, record_id: int, detail_id: int):
    repository = request.app.state.inventory_repository
    if not repository.delete_detail(detail_id):
        raise HTTPException(status_code=404, detail="Detail not found")
    return {"message": "明细删除成功"}


@router.post("/inventory/batch-update-costs")
def batch_update_inventory_costs(request: Request, payload: dict):
    repository = request.app.state.inventory_repository
    date_start = _normalize_date(str(payload.get("date_start") or "").strip()) or None
    date_end = _normalize_date(str(payload.get("date_end") or "").strip()) or None
    updates = payload.get("updates")
    if not isinstance(updates, dict) or not updates:
        raise HTTPException(status_code=400, detail="请填写货号和新单价")
    for product_code, unit_price in updates.items():
        if not str(product_code or "").strip():
            raise HTTPException(status_code=400, detail="货号不能为空")
        if _to_decimal(unit_price) <= 0:
            raise HTTPException(status_code=400, detail=f"货号 {product_code} 的新单价必须大于 0")
    result = repository.batch_update_purchase_costs(
        date_start=date_start,
        date_end=date_end,
        price_updates=updates,
    )
    return {
        **result,
        "message": f"已更新 {result['updated_details']} 条明细，涉及 {result['updated_documents']} 张单据",
    }


@router.post("/inventory/import")
async def import_inventory(request: Request, file: UploadFile = None):
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

    headers = [str(h).strip() if h else "" for h in header_row]

    # Build reverse alias maps
    reverse_aliases: dict[str, str] = {}
    for cn_label, en_field in CN_TO_FIELD.items():
        reverse_aliases[cn_label] = en_field
        reverse_aliases[en_field] = en_field

    detail_reverse_aliases: dict[str, str] = {}
    for cn_label, en_field in DETAIL_CN_TO_FIELD.items():
        detail_reverse_aliases[cn_label] = en_field
        detail_reverse_aliases[en_field] = en_field

    known_fields = set(CN_TO_FIELD.values()) | set(CN_TO_FIELD.keys())
    detail_known_fields = set(DETAIL_CN_TO_FIELD.values()) | set(DETAIL_CN_TO_FIELD.keys())
    repository = request.app.state.inventory_repository

    # Phase 1: Parse all rows and group by summary
    # Each row_entry = {doc: dict, detail: dict}
    groups: dict[str, list[dict]] = {}
    group_order: list[str] = []  # preserve insertion order

    for row in iterator:
        row_dict = {}
        for idx, cell_value in enumerate(row):
            if idx < len(headers) and headers[idx]:
                row_dict[headers[idx]] = cell_value

        doc_payload: dict[str, object] = {}
        detail_payload: dict[str, object] = {}
        extra_fields: dict[str, str] = {}

        for key, value in row_dict.items():
            doc_field = reverse_aliases.get(key)
            detail_field = detail_reverse_aliases.get(key)
            str_value = str(value).strip() if value is not None else None

            if doc_field:
                if doc_field in ("total_count", "amount") and str_value:
                    try:
                        str_value = str(float(str_value))
                    except ValueError:
                        pass
                if doc_field == "date":
                    str_value = _normalize_date(str_value)
                doc_payload[doc_field] = str_value
            elif detail_field:
                if detail_field == "quantity" and str_value:
                    try:
                        str_value = str(int(float(str_value))) if float(str_value) == int(float(str_value)) else str(float(str_value))
                    except ValueError:
                        pass
                if detail_field in ("amount", "unit_price") and str_value:
                    try:
                        str_value = str(float(str_value))
                    except ValueError:
                        pass
                detail_payload[detail_field] = str_value
            elif key and key not in known_fields and key not in detail_known_fields:
                if value is not None and str(value).strip():
                    extra_fields[key] = str(value).strip()

        if not doc_payload.get("date"):
            continue

        # Validate document_type
        doc_type = normalize_document_type(doc_payload.get("document_type"))
        doc_payload["document_type"] = doc_type
        if doc_type and doc_type not in DOCUMENT_TYPES:
            extra_fields["原始单据类型"] = doc_type
            doc_payload["document_type"] = ""

        if extra_fields:
            doc_payload["extra_fields"] = extra_fields

        doc_payload.setdefault("source_workbook", file.filename or "")
        doc_payload.setdefault("source_sheet", ws.title or "")

        # raw_payload stores the original row data
        raw_payload = {}
        for k, v in row_dict.items():
            raw_payload[k] = str(v) if v is not None else ""
        for rp_key, rp_value in raw_payload.items():
            if reverse_aliases.get(rp_key) == "date":
                raw_payload[rp_key] = _normalize_date(rp_value) or rp_value
                break
        doc_payload["raw_payload"] = raw_payload

        summary = str(doc_payload.get("summary") or "").strip()
        if summary not in groups:
            groups[summary] = []
            group_order.append(summary)
        groups[summary].append({"doc": doc_payload, "detail": detail_payload})

    wb.close()

    # Phase 2: Create documents with details grouped by summary
    new_suppliers: set[str] = set()
    new_warehouses: set[str] = set()
    created_docs = 0
    created_details = 0
    skipped_docs = 0

    from domain.inventory_schema import INVENTORY_TABLE
    from sqlalchemy import select as sa_select

    for summary in group_order:
        group_rows = groups[summary]
        first = group_rows[0]
        doc_payload = first["doc"]

        supplier_name = str(doc_payload.get("supplier") or "").strip()
        warehouse_name = str(doc_payload.get("warehouse") or "").strip()
        if supplier_name:
            new_suppliers.add(supplier_name)
        if warehouse_name:
            new_warehouses.add(warehouse_name)

        # Skip if summary already exists in database
        if summary:
            with repository.engine.connect() as conn:
                existing = conn.execute(
                    sa_select(INVENTORY_TABLE).where(INVENTORY_TABLE.c.summary == summary)
                ).first()
                if existing:
                    skipped_docs += 1
                    continue

        try:
            doc = repository.create_record(doc_payload)
            created_docs += 1
            doc_id = doc["id"]

            # Create detail rows that have a product_code
            for row in group_rows:
                detail = row["detail"]
                if detail.get("product_code"):
                    detail["document_id"] = doc_id
                    try:
                        repository.create_detail(detail)
                        created_details += 1
                    except Exception:
                        pass
        except Exception:
            skipped_docs += 1

    # Sync new suppliers and warehouses
    supplier_added = 0
    for name in new_suppliers:
        if not repository.get_supplier_by_name(name):
            repository.create_supplier({"name": name})
            supplier_added += 1

    warehouse_added = 0
    for name in new_warehouses:
        if not repository.get_warehouse_by_name(name):
            repository.create_warehouse({"name": name})
            warehouse_added += 1

    msg = f"导入完成：新增 {created_docs} 条单据，{created_details} 条明细"
    if skipped_docs > 0:
        msg += f"，跳过 {skipped_docs} 条已存在的单据"
    if supplier_added > 0:
        msg += f"，新增供应商 {supplier_added} 个"
    if warehouse_added > 0:
        msg += f"，新增仓库 {warehouse_added} 个"
    return {"created": created_docs, "details": created_details, "skipped": skipped_docs, "message": msg}
