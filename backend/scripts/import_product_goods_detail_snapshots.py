"""Import compact product-goods snapshots from historical 商品明细表 workbooks."""

from __future__ import annotations

import argparse
import re
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterator
from zipfile import ZipFile
from xml.etree.ElementTree import iterparse

from openpyxl.utils.datetime import from_excel
from sqlalchemy import create_engine, delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from api.product_goods_cache import clear_product_goods_cache
from config import load_settings
from domain.product_goods_detail_snapshot_schema import (
    PRODUCT_GOODS_DETAIL_SNAPSHOT_BATCHES_TABLE,
    ensure_product_goods_detail_snapshot_tables,
)
from domain.product_goods_schema import PRODUCT_GOODS_OVERRIDES_TABLE
from scripts.backfill_product_goods_manual_fields_history import historical_workbooks
from scripts.import_product_goods_manual_fields import (
    BRAND_FOLDERS,
    MANUAL_FIELDS,
    SHARED_ROOT,
    XML_NAMESPACE,
    _cell_value,
    _column_index,
    _product_maps,
    _shared_strings,
    _sheet_xml_path,
    _text,
    _xlsx_sheet_names,
)


PRODUCT_SHEET_NAME = "商品明细表"
SIZE_PATTERN = re.compile(r"^(3[4-9]|4[0-7])$")
ANNUAL_PATTERN = re.compile(r"^(20\d{2})年(?:销售|销量)")
MONTHLY_PATTERN = re.compile(r"^(\d{2})-(1[0-2]|[1-9])$")

STATIC_FIELDS = {
    "year": ("年份",),
    "season": ("季节分类", "季节"),
    "platform": ("所属平台", "主推平台", "主销平台"),
    "category_l4": ("四级分类",),
    "first_order_date": ("首单日期",),
    "factory_sku": ("工厂货号",),
    "factory_code": ("工厂代码",),
    "factory_name": ("工厂", "工厂名称"),
    "color": ("颜色",),
    "cost": ("原成本", "成本"),
    "product_role": ("商品角色",),
    "product_type": ("类型",),
    "douyin_hot": ("抖音爆款",),
    "clearance": ("清仓",),
    "remark": ("备注",),
}
METRIC_FIELDS = {
    "total_order_count": ("总订单量",),
    "total_sales": ("总销量",),
    "stock_plus_purchase": ("在仓库存+进货仓",),
    "in_transit_total": ("在途库存",),
    "return_qty": ("回单",),
    "post_replenishment_stock": ("补单后库存",),
    "post_replenishment_turnover_days": ("补单后周转天数",),
    "day_over_day": ("昨比前日",),
    "yesterday_sales": ("昨日销量",),
    "normal_shelf_sales": ("正价货架销量", "昨日非抖音销量"),
    "clearance_sales": ("清仓销量",),
    "week_sales": ("近7天周销量",),
    "normal_shelf_week_sales": ("正价货架7天销量", "非抖音7天销量"),
    "clearance_week_sales": ("清仓7天销量",),
    "last_week_sales": ("上周销量",),
    "same_week_sales": ("同期周销",),
    "same_week_non_douyin_sales": ("同期非抖音周销",),
    "stock_total": ("在仓合计",),
    "inventory_total": ("整体库存合计",),
    "shortage_total": ("缺货合计",),
    "stock_health": ("库存健康度提醒", "库存预警"),
    "broken_size_sku": ("断码SKU",),
    "sales_size_total": ("销售明细合计",),
    "replenishment_total": ("补单合计",),
    "post_replenishment_total": ("补单后合计",),
    "three_day_change": ("三天环比",),
}
GROUP_TOTALS = {
    "stock_by_size": "在仓合计",
    "in_transit_by_size": "在途合计",
    "inventory_by_size": "整体库存合计",
    "shortage_by_size": "缺货合计",
    "sales_by_size": "销售明细合计",
    "replenishment_by_size": "补单合计",
    "post_replenishment_by_size": "补单后合计",
}
PLATFORM_ALIASES = {
    "唯品": "唯品",
    "天猫": "天猫",
    "得物": "得物",
    "拼多多": "拼多多",
    "京东": "京东",
    "商品卡": "商品卡",
    "直播赛道": "直播赛道",
    "抖音": "直播赛道",
    "抖音商城": "直播赛道",
    "达播清仓": "达播清仓",
    "拼多多清仓": "拼多多清仓",
    "其他": "其他",
}
SNAPSHOT_FORMAT = "product_goods_detail_snapshot_v2"


def _header(value: object) -> str:
    return str(value or "").strip().replace("\n", "").replace(" ", "")


def _number(value: object) -> int | float | None:
    text = str(value or "").strip()
    if not text or text.upper() in {"#N/A", "#VALUE!", "#DIV/0!", "-"}:
        return None
    try:
        parsed = Decimal(text.replace(",", ""))
    except (InvalidOperation, ValueError):
        return None
    if parsed == parsed.to_integral_value():
        return int(parsed)
    return float(parsed)


def _excel_date(value: object) -> str | None:
    numeric = _number(value)
    if isinstance(numeric, (int, float)) and 20_000 <= numeric <= 70_000:
        try:
            parsed = from_excel(numeric)
            if isinstance(parsed, date):
                return parsed.date().isoformat() if hasattr(parsed, "date") else parsed.isoformat()
        except (TypeError, ValueError):
            pass
    text = _text(value)
    return text


def _first_indexes(headers: dict[int, str], aliases: tuple[str, ...]) -> list[int]:
    targets = {_header(alias) for alias in aliases}
    return [index for index, value in headers.items() if _header(value) in targets]


def _first_value(values: dict[int, object], indexes: list[int], *, date_value: bool = False) -> object | None:
    for index in indexes:
        value = values.get(index)
        if _text(value) is not None:
            return _excel_date(value) if date_value else value
    return None


def _sizes_before(headers: dict[int, str], total_label: str) -> list[tuple[str, int]]:
    indexes = _first_indexes(headers, (total_label,))
    if not indexes:
        return []
    index = indexes[0] - 1
    pairs: list[tuple[str, int]] = []
    while index in headers and SIZE_PATTERN.match(_header(headers[index])):
        pairs.append((_header(headers[index]), index))
        index -= 1
    return list(reversed(pairs))


def _header_date(value: object) -> str | None:
    numeric = _number(value)
    if not isinstance(numeric, (int, float)) or not 20_000 <= numeric <= 70_000:
        return None
    try:
        parsed = from_excel(numeric)
    except (TypeError, ValueError):
        return None
    if isinstance(parsed, datetime):
        return parsed.date().isoformat()
    if isinstance(parsed, date):
        return parsed.isoformat()
    return None


def _header_row(path: Path) -> tuple[str, dict[int, str], int, dict[int, str]]:
    with ZipFile(path) as archive:
        if PRODUCT_SHEET_NAME not in _xlsx_sheet_names(archive):
            raise ValueError(f"未找到 {PRODUCT_SHEET_NAME}: {path}")
        shared_strings = _shared_strings(archive)
        sheet_path = _sheet_xml_path(archive, PRODUCT_SHEET_NAME)
        header_rows: dict[int, dict[int, object]] = {}
        with archive.open(sheet_path) as stream:
            for _, element in iterparse(stream, events=("end",)):
                if element.tag != f"{XML_NAMESPACE}row":
                    continue
                row_number = int(element.attrib.get("r") or 0)
                values = {
                    _column_index(cell.attrib.get("r", "")): _cell_value(cell, shared_strings)
                    for cell in element.iter(f"{XML_NAMESPACE}c")
                }
                header_rows[row_number] = values
                element.clear()
                if row_number > 12:
                    break
                if _first_indexes(values, ("货号", "原始货号")) and _first_indexes(values, ("总销量",)):
                    headers = {key: _header(value) for key, value in values.items()}
                    period_starts = sorted(
                        (index, _header(value))
                        for prior_row in header_rows.values()
                        for index, value in prior_row.items()
                        if _header(value) in {"日销量", "周销量", "月销量"}
                    )
                    period_by_index: dict[int, str] = {}
                    for position, (start, period) in enumerate(period_starts):
                        end = period_starts[position + 1][0] if position + 1 < len(period_starts) else max(headers) + 1
                        for index in range(start + 1, end):
                            period_by_index[index] = period
                    return PRODUCT_SHEET_NAME, headers, row_number, period_by_index
    raise ValueError(f"未识别到 {PRODUCT_SHEET_NAME} 表头: {path}")


def _iter_detail_rows(path: Path, *, header_row: int, wanted_indexes: set[int]) -> Iterator[tuple[int, dict[int, object]]]:
    with ZipFile(path) as archive:
        shared_strings = _shared_strings(archive)
        sheet_path = _sheet_xml_path(archive, PRODUCT_SHEET_NAME)
        with archive.open(sheet_path) as stream:
            for _, element in iterparse(stream, events=("end",)):
                if element.tag != f"{XML_NAMESPACE}row":
                    continue
                row_number = int(element.attrib.get("r") or 0)
                if row_number <= header_row:
                    element.clear()
                    continue
                values = {
                    _column_index(cell.attrib.get("r", "")): _cell_value(cell, shared_strings)
                    for cell in element.iter(f"{XML_NAMESPACE}c")
                    if _column_index(cell.attrib.get("r", "")) in wanted_indexes
                }
                element.clear()
                if values:
                    yield row_number, values


def _platform_values(headers: dict[int, str], period_by_index: dict[int, str]) -> dict[str, list[tuple[str, int]]]:
    result: dict[str, list[tuple[str, int]]] = defaultdict(list)
    period_keys = {"日销量": "daily", "周销量": "weekly", "月销量": "monthly"}
    for index, period in period_by_index.items():
        platform = PLATFORM_ALIASES.get(_header(headers.get(index)))
        if platform and period in period_keys:
            result[period_keys[period]].append((platform, index))
    return result


def _snapshot_payload(headers: dict[int, str], values: dict[int, object], period_by_index: dict[int, str]) -> dict[str, object]:
    static: dict[str, object] = {}
    for field, aliases in STATIC_FIELDS.items():
        value = _first_value(values, _first_indexes(headers, aliases), date_value=field == "first_order_date")
        if value is not None:
            static[field] = _text(value)
    metrics: dict[str, int | float | str] = {}
    for field, aliases in METRIC_FIELDS.items():
        value = _first_value(values, _first_indexes(headers, aliases))
        normalized = _number(value)
        if normalized is not None:
            metrics[field] = normalized
        elif field in {"stock_health", "broken_size_sku"} and _text(value) is not None:
            metrics[field] = _text(value) or ""

    result: dict[str, object] = {**static, "metrics": metrics}
    for field, label in GROUP_TOTALS.items():
        result[field] = {
            size: number
            for size, index in _sizes_before(headers, label)
            if (number := _number(values.get(index))) is not None
        }

    annual_sales: dict[str, int | float] = {}
    monthly_sales: dict[str, int | float] = {}
    daily_sales_by_date: dict[str, int | float] = {}
    for index, header in headers.items():
        value = _number(values.get(index))
        if value is None:
            continue
        annual_match = ANNUAL_PATTERN.match(header)
        if annual_match:
            annual_sales[annual_match.group(1)] = value
            continue
        monthly_match = MONTHLY_PATTERN.match(header)
        if monthly_match:
            monthly_sales[f"20{monthly_match.group(1)}-{int(monthly_match.group(2))}"] = value
            continue
        date_text = _header_date(header)
        if date_text:
            daily_sales_by_date[date_text] = value
    result["annual_sales"] = annual_sales
    result["monthly_sales"] = monthly_sales
    result["daily_sales_by_date"] = daily_sales_by_date
    for period, pairs in _platform_values(headers, period_by_index).items():
        result[f"{period}_platform_sales"] = {
            platform: number
            for platform, index in pairs
            if (number := _number(values.get(index))) is not None
        }
    return result


def _wanted_indexes(headers: dict[int, str], period_by_index: dict[int, str]) -> set[int]:
    indexes: set[int] = set()
    for aliases in (*STATIC_FIELDS.values(), *METRIC_FIELDS.values(), ("货号", "原始货号", "商品货号", "sku"), ("款号",)):
        indexes.update(_first_indexes(headers, aliases))
    for label in GROUP_TOTALS.values():
        indexes.update(index for _, index in _sizes_before(headers, label))
    for index, header in headers.items():
        if ANNUAL_PATTERN.match(header) or MONTHLY_PATTERN.match(header) or _header_date(header):
            indexes.add(index)
    for pairs in _platform_values(headers, period_by_index).values():
        indexes.update(index for _, index in pairs)
    return indexes


def _source_codes(headers: dict[int, str], values: dict[int, object]) -> tuple[list[str], list[str]]:
    goods_indexes = _first_indexes(headers, ("货号", "原始货号", "商品货号", "sku"))
    style_indexes = _first_indexes(headers, ("款号", "原始款号"))
    goods_codes = [text for index in goods_indexes if (text := _text(values.get(index)))]
    style_codes = [text for index in style_indexes if (text := _text(values.get(index)))]
    return sorted(set(goods_codes), key=len, reverse=True), sorted(set(style_codes), key=len, reverse=True)


def _write_missing_overrides(engine, *, brand: str, values_by_product: dict[int, dict[str, object]], product_ids: set[int]) -> None:
    records = []
    for product_id in product_ids:
        values = values_by_product[product_id]
        records.append({"brand": brand, "product_id": product_id, **{field: values.get(field) for field in MANUAL_FIELDS}})
    if not records:
        return
    with engine.begin() as connection:
        for index in range(0, len(records), 1_000):
            statement = pg_insert(PRODUCT_GOODS_OVERRIDES_TABLE).values(records[index:index + 1_000])
            connection.execute(
                statement.on_conflict_do_update(
                    index_elements=["brand", "product_id"],
                    set_={field: getattr(statement.excluded, field) for field in MANUAL_FIELDS},
                )
            )


def import_workbook(
    *,
    engine,
    brand: str,
    path: Path,
    snapshot_date: date,
    by_sku: dict[str, int],
    by_unique_style: dict[str, int],
    values_by_product: dict[int, dict[str, object]],
    dry_run: bool,
) -> tuple[int, set[int]]:
    sheet_name, headers, header_row, period_by_index = _header_row(path)
    wanted_indexes = _wanted_indexes(headers, period_by_index)
    table = ensure_product_goods_detail_snapshot_tables(engine, snapshot_date.year)
    records: dict[str, dict[str, object]] = {}
    dirty_product_ids: set[int] = set()
    for row_number, values in _iter_detail_rows(path, header_row=header_row, wanted_indexes=wanted_indexes):
        goods_codes, style_codes = _source_codes(headers, values)
        product_id = next((by_sku[code] for code in goods_codes if code in by_sku), None)
        if product_id is None:
            product_id = next((by_unique_style[code] for code in style_codes if code in by_unique_style), None)
        goods_code = next((code for code in goods_codes if code in by_sku), None) or next(
            (code for code in goods_codes if not code.isdigit()),
            None,
        )
        if goods_code is None and product_id is not None:
            goods_code = next((code for code, identifier in by_sku.items() if identifier == product_id), None)
        if goods_code is None:
            continue
        payload = _snapshot_payload(headers, values, period_by_index)
        records[goods_code] = {
            "brand": brand,
            "snapshot_date": snapshot_date,
            "goods_code": goods_code,
            "style_code": style_codes[0] if style_codes else None,
            "source_workbook": path.name,
            "source_sheet": sheet_name,
            "source_row_number": row_number,
            "data": payload,
        }
        if product_id is not None:
            manual_values = values_by_product.setdefault(product_id, {field: None for field in MANUAL_FIELDS})
            for field in MANUAL_FIELDS:
                source_value = payload.get(field)
                if _text(manual_values.get(field)) is None and _text(source_value) is not None:
                    manual_values[field] = source_value
                    dirty_product_ids.add(product_id)
    if dry_run:
        return len(records), dirty_product_ids

    with engine.begin() as connection:
        connection.execute(
            delete(table).where(
                (table.c.brand == brand)
                & (table.c.snapshot_date == snapshot_date)
            )
        )
        payloads = list(records.values())
        for index in range(0, len(payloads), 1_000):
            connection.execute(table.insert(), payloads[index:index + 1_000])
    return len(records), dirty_product_ids


def import_brand(
    brand: str,
    *,
    root: Path,
    dry_run: bool,
    max_workbooks: int | None = None,
    retry_failed: bool = False,
    force: bool = False,
    snapshot_dates: set[date] | None = None,
) -> dict[str, object]:
    settings = load_settings(require_database=True)
    assert settings.database_url is not None
    engine = create_engine(settings.database_url, future=True)
    PRODUCT_GOODS_DETAIL_SNAPSHOT_BATCHES_TABLE.create(engine, checkfirst=True)
    workbooks = historical_workbooks(root, brand=brand)
    if snapshot_dates is not None:
        workbooks = [item for item in workbooks if item.business_date in snapshot_dates]
    if max_workbooks is not None:
        workbooks = workbooks[:max_workbooks]
    with engine.connect() as connection:
        by_sku, by_unique_style = _product_maps(connection, brand)
        values_by_product = {
            int(row["product_id"]): {field: row.get(field) for field in MANUAL_FIELDS}
            for row in connection.execute(
                select(PRODUCT_GOODS_OVERRIDES_TABLE).where(PRODUCT_GOODS_OVERRIDES_TABLE.c.brand == brand)
            ).mappings()
        }
        completed = {
            row["snapshot_date"]
            for row in connection.execute(
                select(PRODUCT_GOODS_DETAIL_SNAPSHOT_BATCHES_TABLE.c.snapshot_date).where(
                    (PRODUCT_GOODS_DETAIL_SNAPSHOT_BATCHES_TABLE.c.brand == brand)
                    & (PRODUCT_GOODS_DETAIL_SNAPSHOT_BATCHES_TABLE.c.status == "success")
                )
            ).mappings()
            if isinstance(row["snapshot_date"], date)
        }
    imported = 0
    skipped = 0
    total_rows = 0
    changed_product_ids: set[int] = set()
    for item in workbooks:
        if item.business_date in completed and not retry_failed and not force:
            skipped += 1
            continue
        batch_values = {
            "brand": brand,
            "snapshot_date": item.business_date,
            "source_path": str(item.path),
            "source_workbook": item.path.name,
            "status": "running",
            "row_count": None,
            "message": None,
        }
        if not dry_run:
            with engine.begin() as connection:
                statement = pg_insert(PRODUCT_GOODS_DETAIL_SNAPSHOT_BATCHES_TABLE).values(batch_values)
                connection.execute(
                    statement.on_conflict_do_update(
                        index_elements=["brand", "snapshot_date"],
                        set_={key: value for key, value in batch_values.items() if key not in {"brand", "snapshot_date"}},
                    )
                )
        try:
            row_count, dirty = import_workbook(
                engine=engine,
                brand=brand,
                path=item.path,
                snapshot_date=item.business_date,
                by_sku=by_sku,
                by_unique_style=by_unique_style,
                values_by_product=values_by_product,
                dry_run=dry_run,
            )
        except Exception as exc:
            if not dry_run:
                with engine.begin() as connection:
                    connection.execute(
                        PRODUCT_GOODS_DETAIL_SNAPSHOT_BATCHES_TABLE.update()
                        .where(
                            (PRODUCT_GOODS_DETAIL_SNAPSHOT_BATCHES_TABLE.c.brand == brand)
                            & (PRODUCT_GOODS_DETAIL_SNAPSHOT_BATCHES_TABLE.c.snapshot_date == item.business_date)
                        )
                        .values(status="failed", message=f"{type(exc).__name__}: {exc}")
                    )
            print(f"[FAILED] {brand} {item.business_date} {item.path.name}: {type(exc).__name__}: {exc}", flush=True)
            continue
        if not dry_run:
            with engine.begin() as connection:
                connection.execute(
                    PRODUCT_GOODS_DETAIL_SNAPSHOT_BATCHES_TABLE.update()
                    .where(
                        (PRODUCT_GOODS_DETAIL_SNAPSHOT_BATCHES_TABLE.c.brand == brand)
                        & (PRODUCT_GOODS_DETAIL_SNAPSHOT_BATCHES_TABLE.c.snapshot_date == item.business_date)
                    )
                    .values(status="success", row_count=row_count, message=SNAPSHOT_FORMAT)
                )
        imported += 1
        total_rows += row_count
        changed_product_ids.update(dirty)
        print(f"[OK] {brand} {item.business_date.isoformat()} {item.path.name}: {row_count} rows", flush=True)
    if changed_product_ids and not dry_run:
        _write_missing_overrides(engine, brand=brand, values_by_product=values_by_product, product_ids=changed_product_ids)
        clear_product_goods_cache()
    return {
        "brand": brand,
        "available_workbooks": len(workbooks),
        "imported_workbooks": imported,
        "skipped_workbooks": skipped,
        "rows": total_rows,
        "manual_fields_filled": len(changed_product_ids),
        "dry_run": dry_run,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="导入历史货品表商品明细快照")
    parser.add_argument("--brand", choices=sorted(BRAND_FOLDERS), action="append")
    parser.add_argument("--root", type=Path, help="单品牌历史目录；需同时传入一个 --brand")
    parser.add_argument("--max-workbooks", type=int, default=None)
    parser.add_argument("--snapshot-date", type=date.fromisoformat, action="append", help="只导入指定日期，可重复传入")
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--force", action="store_true", help="重新覆盖已成功导入的日期")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    brands = args.brand or ("cbanner_womens", "cbanner_mens", "eblan")
    if args.root is not None and len(brands) != 1:
        parser.error("--root requires exactly one --brand")
    for brand in brands:
        root = args.root or SHARED_ROOT / BRAND_FOLDERS[brand]
        print(
            import_brand(
                brand,
                root=root,
                dry_run=args.dry_run,
                max_workbooks=args.max_workbooks,
                retry_failed=args.retry_failed,
                force=args.force,
                snapshot_dates=set(args.snapshot_date) if args.snapshot_date else None,
            )
        )


if __name__ == "__main__":
    main()
