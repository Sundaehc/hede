"""Export daily fine-table snapshots to shared brand folders.

Run:
    python -m scripts.export_fine_table_daily
    python -m scripts.export_fine_table_daily --brand cbanner_mens
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from sqlalchemy import select

from api.excel_export import style_excel_worksheet
from api.routes.fine_table import create_fine_table_snapshot
from config import load_settings
from domain.fine_table_snapshot_schema import (
    FINE_TABLE_SNAPSHOT_BATCH_TABLE,
    fine_table_snapshot_row_table_for_date,
    fine_table_snapshot_year_table_exists,
)
from domain.sources import TABLE_NAMES
from storage.product_repository import ProductRepository


BRAND_EXPORT_FOLDERS = {
    "cbanner_mens": "千百度男鞋",
    "cbanner_womens": "千百度女鞋",
    "yandou": "烟斗",
    "eblan": "伊伴",
}

SIZE_STOCK_LABELS = (
    "34/220",
    "35/225",
    "36/230",
    "37/235",
    "38/240",
    "39/245",
    "40/250",
    "41/255",
    "42/260",
    "43/265",
    "44/270",
    "45/275",
    "46/280",
    "47/285",
)

KNOWN_COLUMNS: tuple[tuple[str, str], ...] = (
    ("brand_label", "品牌"),
    ("sku", "货号"),
    ("original_sku", "原始货号"),
    ("status", "上下线状态"),
    ("group_name", "组别"),
    ("product_level", "商品等级"),
    ("factory_code", "工厂代码"),
    ("product_name", "品名"),
    ("main_style", "主款式"),
    ("style_code", "款号"),
    ("goods_id", "商品ID"),
    ("p_spu", "P-SPU"),
    ("category_l3", "三级分类"),
    ("factory_sku", "工厂货号"),
    ("color", "颜色名称"),
    ("color_code", "颜色代码"),
    ("season_category", "季节"),
    ("year", "年份"),
    ("supplier_name", "供应商"),
    ("execution_standard", "执行标"),
    ("upper_material", "鞋面材质"),
    ("lining_material", "内里材质"),
    ("outsole_material", "大底材质"),
    ("insole_material", "鞋垫材质"),
    ("heel_height", "跟高"),
    ("shoe_width", "鞋宽"),
    ("shoe_length", "鞋长"),
    ("shaft_circumference", "筒围"),
    ("shaft_height", "筒高"),
    ("internal_height_increase", "内增高"),
    ("internal_height_note", "内增高说明"),
    ("upper_height", "帮高"),
    ("toe_shape", "头型"),
    ("closure_type", "闭合方式"),
    ("shoe_box_spec", "鞋盒规格"),
    ("first_order_time", "首单日期"),
    ("size_range", "尺码段"),
    ("product_model", "产品型号"),
    ("launch_date", "上市时间"),
    ("image_path", "图片路径"),
    ("image_url", "图片URL"),
    ("goods_status", "商品状态原值"),
    ("status_key", "状态标识"),
    ("sales_tag", "畅销度"),
    ("goods_tag", "小灯塔"),
    ("latest_purchase_price", "成本"),
    ("cost", "档案成本"),
    ("final_price", "到手价"),
    ("vip_price", "唯品价"),
    ("market_price", "市场价"),
    ("price_band", "价格段"),
    ("activity_profit", "活动毛利"),
    ("margin_rate", "活动毛利率"),
    ("discount_rate", "折扣率"),
    ("vip_1d_sales", "唯品1天"),
    ("vip_3d_sales", "唯品3天"),
    ("vip_7d_sales", "唯品7天"),
    ("vip_15d_sales", "唯品15天"),
    ("vip_30d_sales", "唯品30天"),
    ("vip_daily_average_sales", "唯品日均"),
    ("vip_projected_15d_sales", "唯品15天预计"),
    ("other_3d_sales", "其他3天"),
    ("other_7d_sales", "其他7天"),
    ("other_15d_sales", "其他15天"),
    ("other_30d_sales", "其他30天"),
    ("other_daily_average_sales", "其他日均"),
    ("other_projected_15d_sales", "其他15天预计"),
    ("original_other_3d_sales", "其他原始3天"),
    ("original_other_7d_sales", "其他原始7天"),
    ("original_other_15d_sales", "其他原始15天"),
    ("original_other_30d_sales", "其他原始30天"),
    ("shop_30d_sales", "其他平台30天店铺拆分"),
    ("vip_3d_uv", "3天UV"),
    ("vip_7d_uv", "7天UV"),
    ("vip_30d_uv", "30天UV"),
    ("vip_3d_ctr", "3天CTR"),
    ("vip_7d_ctr", "7天CTR"),
    ("vip_30d_ctr", "30天CTR"),
    ("vip_3d_exposure", "3天曝光"),
    ("vip_7d_exposure", "7天曝光"),
    ("vip_30d_exposure", "30天曝光"),
    ("vip_3d_conversion", "3天转化"),
    ("vip_7d_conversion", "7天转化"),
    ("vip_30d_conversion", "30天转化"),
    ("vip_3d_sales_change_rate", "3天销售环比"),
    ("vip_3d_uv_change_rate", "3天UV环比"),
    ("vip_3d_ctr_change_rate", "3天CTR环比"),
    ("vip_3d_conversion_change_rate", "3天转化环比"),
    ("vip_7d_sales_change_rate", "7天销售环比"),
    ("vip_7d_uv_change_rate", "7天UV环比"),
    ("vip_7d_ctr_change_rate", "7天CTR环比"),
    ("vip_7d_conversion_change_rate", "7天转化环比"),
    ("vip_30d_reject_count", "30天拒退"),
    ("vip_30d_reject_rate", "30天拒退率"),
    ("stock_qty", "聚水潭库存"),
    ("original_stock_qty", "原始货号库存"),
    ("projected_5d_stock_no_inbound", "现有5天后预计库存(不加未到)"),
    ("inbound_qty", "采购在途数"),
    ("defect_stock", "次品库存"),
    ("original_defect_stock", "原始货号次品仓汇总"),
    ("original_inbound_qty", "原始货号采购在途数量汇总"),
    ("original_order_in_transit_stock", "原始货号已下订单未到数量汇总"),
    ("original_defect_in_transit_stock", "原始货号打次未到数量汇总"),
    ("off_shelf_stock", "下架仓商品数量"),
    ("order_occupy_stock", "订单占有"),
    ("order_in_transit_stock", "已下订单未到数量"),
    ("defect_in_transit_stock", "打次未到数量"),
    ("purchase_diff", "采购差异"),
    ("projected_15d_stock", "15天后库存"),
    ("vip_projected_15d_stock", "15天后库存减唯品会"),
    ("other_projected_15d_stock", "15天后库存减其他平台"),
    ("risk", "风险"),
)

SKIPPED_EXTRA_KEYS = {
    "brand",
    "created_at",
    "daily_sales",
    "extra_field",
    "extra_fields",
    "id",
    "raw_payload",
    "size_stock",
    "source_row_number",
    "source_sheet",
    "source_workbook",
    "updated_at",
}
TEXT_HEADERS = {
    "品牌",
    "货号",
    "原始货号",
    "商品ID",
    "P-SPU",
    "款号",
    "工厂货号",
    "颜色代码",
    "图片路径",
    "图片URL",
}


@dataclass
class _AppState:
    settings: Any
    repository: ProductRepository


@dataclass
class _App:
    state: _AppState


@dataclass
class _Request:
    app: _App


def _brand_label(brand: str) -> str:
    return BRAND_EXPORT_FOLDERS.get(brand, brand)


def _to_float(value: Any) -> float:
    if value is None or value == "":
        return 0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0


def _to_optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_percent(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        value = value.strip().replace("%", "")
    parsed = _to_optional_float(value)
    if parsed is None:
        return None
    return parsed / 100


def _rounded(value: float | None, digits: int = 2) -> float | None:
    if value is None:
        return None
    return round(value, digits)


def _status_label(row: dict[str, Any]) -> str:
    goods_status = str(row.get("goods_status") or "").strip()
    if goods_status:
        return goods_status
    status_key = row.get("status_key")
    if status_key == "online":
        return "商品上线"
    if status_key == "partial":
        return "部分上线"
    if status_key == "offline":
        return "已下线"
    return "未知"


def _daily_sales_by_date(row: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in row.get("daily_sales") or []:
        if not isinstance(item, dict):
            continue
        day = str(item.get("date") or "").strip()
        if day:
            result[day] = item
    return result


def _daily_column_label(day: str, metric: str) -> str:
    display_day = day[5:] if len(day) >= 10 and day[4] == "-" else day
    return f"{display_day}{metric}"


def _format_shop_sales(value: Any) -> str | None:
    if not isinstance(value, list):
        return None
    parts = []
    for item in value:
        if not isinstance(item, dict):
            continue
        shop_name = str(item.get("shop_name") or "").strip()
        quantity = item.get("quantity")
        if shop_name or quantity not in (None, ""):
            parts.append(f"{shop_name}:{quantity or 0}")
    return "; ".join(parts)


def _format_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))


def _normalize_cell(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (dict, list)):
        return _format_json(value)
    return value


def _exposure(uv: Any, ctr: Any) -> float | None:
    ctr_value = _parse_percent(ctr)
    if not ctr_value:
        return None
    return _to_float(uv) / ctr_value


def _cell_value(row: dict[str, Any], key: str, brand: str) -> Any:
    if key == "brand_label":
        return _brand_label(str(row.get("brand") or brand))
    if key == "status":
        return _status_label(row)
    if key == "category_l3":
        return row.get("category_l3") or row.get("product_model")
    if key == "latest_purchase_price":
        return row.get("latest_purchase_price") or row.get("cost")
    if key == "vip_projected_15d_sales":
        return _rounded(_to_float(row.get("vip_daily_average_sales")) * 15)
    if key == "other_daily_average_sales":
        return _rounded(_to_float(row.get("other_30d_sales")) / 30)
    if key == "other_projected_15d_sales":
        return _rounded((_to_float(row.get("other_30d_sales")) / 30) * 15)
    if key == "vip_3d_exposure":
        return _rounded(_exposure(row.get("vip_3d_uv"), row.get("vip_3d_ctr")))
    if key == "vip_7d_exposure":
        return _rounded(_exposure(row.get("vip_7d_uv"), row.get("vip_7d_ctr")))
    if key == "vip_30d_exposure":
        return _rounded(_exposure(row.get("vip_30d_uv"), row.get("vip_30d_ctr")))
    if key == "projected_5d_stock_no_inbound":
        return _rounded(
            _to_float(row.get("stock_qty"))
            - (_to_float(row.get("vip_daily_average_sales")) * 5 + _to_float(row.get("other_30d_sales")) / 30 * 5)
        )
    if key == "order_in_transit_stock":
        return _rounded(_to_float(row.get("inbound_qty")) - _to_float(row.get("defect_in_transit_stock")))
    if key == "vip_projected_15d_stock":
        return _rounded(
            _to_float(row.get("stock_qty"))
            + _to_float(row.get("inbound_qty"))
            - _to_float(row.get("vip_daily_average_sales")) * 15
        )
    if key == "other_projected_15d_stock":
        vip_projected_stock = (
            _to_float(row.get("stock_qty"))
            + _to_float(row.get("inbound_qty"))
            - _to_float(row.get("vip_daily_average_sales")) * 15
        )
        return _rounded(vip_projected_stock - (_to_float(row.get("other_30d_sales")) / 30 * 15))
    if key == "risk":
        vip_projected = _cell_value(row, "vip_projected_15d_stock", brand)
        other_projected = _cell_value(row, "other_projected_15d_stock", brand)
        if min(_to_float(vip_projected), _to_float(other_projected)) < 0:
            return "15天后缺口"
        if _to_float(row.get("stock_qty")) < _to_float(row.get("vip_7d_sales")) + _to_float(row.get("other_7d_sales")):
            return "低库存"
        return "正常"
    if key == "shop_30d_sales":
        return _format_shop_sales(row.get("shop_30d_sales"))
    if key.startswith("daily_sales::"):
        _, day, metric = key.split("::", 2)
        daily = _daily_sales_by_date(row).get(day, {})
        return daily.get("quantity" if metric == "quantity" else "uv") or 0
    if key.startswith("size_stock::"):
        _, label = key.split("::", 1)
        size_stock = row.get("size_stock") or {}
        if isinstance(size_stock, dict):
            return size_stock.get(label, 0) or 0
        return 0
    return _normalize_cell(row.get(key))


def _daily_columns(rows: list[dict[str, Any]]) -> list[tuple[str, str]]:
    days: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for day in _daily_sales_by_date(row):
            if day in seen:
                continue
            seen.add(day)
            days.append(day)
    days.sort()

    columns: list[tuple[str, str]] = []
    for day in days:
        columns.append((f"daily_sales::{day}::quantity", _daily_column_label(day, "销售")))
        columns.append((f"daily_sales::{day}::uv", _daily_column_label(day, "UV")))
    return columns


def _size_columns(rows: list[dict[str, Any]]) -> list[tuple[str, str]]:
    labels = list(SIZE_STOCK_LABELS)
    seen = set(labels)
    extra_labels: set[str] = set()
    for row in rows:
        size_stock = row.get("size_stock") or {}
        if not isinstance(size_stock, dict):
            continue
        for label in size_stock:
            label_text = str(label)
            if label_text not in seen:
                extra_labels.add(label_text)
    labels.extend(sorted(extra_labels))
    return [(f"size_stock::{label}", label) for label in labels]


def _columns_for_rows(rows: list[dict[str, Any]]) -> list[tuple[str, str]]:
    columns = list(KNOWN_COLUMNS)
    known_keys = {key for key, _label in columns}
    known_keys.update(SKIPPED_EXTRA_KEYS)
    columns.extend(_daily_columns(rows))
    columns.extend(_size_columns(rows))

    extra_keys: list[str] = []
    for row in rows:
        for key in row:
            if key in known_keys or key in extra_keys:
                continue
            extra_keys.append(key)
    columns.extend((key, key) for key in extra_keys)
    return columns


def _find_snapshot_batch(repository: ProductRepository, brand: str, snapshot_date: date) -> dict[str, Any] | None:
    FINE_TABLE_SNAPSHOT_BATCH_TABLE.create(repository.engine, checkfirst=True)
    with repository.engine.connect() as connection:
        batch = connection.execute(
            select(FINE_TABLE_SNAPSHOT_BATCH_TABLE)
            .where(FINE_TABLE_SNAPSHOT_BATCH_TABLE.c.brand == brand)
            .where(FINE_TABLE_SNAPSHOT_BATCH_TABLE.c.snapshot_date == snapshot_date)
        ).mappings().first()
    return dict(batch) if batch is not None else None


def _ensure_snapshot(
    request: _Request,
    *,
    brand: str,
    snapshot_date: date,
    create_missing_snapshot: bool,
    refresh_snapshot: bool,
) -> dict[str, Any]:
    repository = request.app.state.repository
    batch = _find_snapshot_batch(repository, brand, snapshot_date)
    has_row_table = fine_table_snapshot_year_table_exists(repository.engine, snapshot_date)
    if refresh_snapshot or batch is None or not has_row_table:
        if not create_missing_snapshot:
            raise RuntimeError(f"[{brand}] snapshot not found for {snapshot_date.isoformat()}")
        result = create_fine_table_snapshot(
            request,  # type: ignore[arg-type]
            brand=brand,  # type: ignore[arg-type]
            snapshot_date=snapshot_date,
        )
        print(
            f"[{brand}] snapshot {result['message']} "
            f"date={result['item']['snapshot_date']} rows={result['rows']}"
        )
        batch = _find_snapshot_batch(repository, brand, snapshot_date)
    if batch is None:
        raise RuntimeError(f"[{brand}] snapshot not found after creation for {snapshot_date.isoformat()}")
    return batch


def _load_snapshot_rows(repository: ProductRepository, batch: dict[str, Any]) -> list[dict[str, Any]]:
    snapshot_date = batch.get("snapshot_date")
    if not isinstance(snapshot_date, date):
        raise RuntimeError(f"Invalid snapshot_date: {snapshot_date!r}")
    snapshot_row_table = fine_table_snapshot_row_table_for_date(snapshot_date)
    with repository.engine.connect() as connection:
        rows = connection.execute(
            select(snapshot_row_table.c.payload)
            .where(snapshot_row_table.c.batch_id == batch["id"])
            .order_by(snapshot_row_table.c.row_index)
        ).mappings()
        payloads = []
        for row in rows:
            payload = row["payload"]
            if isinstance(payload, dict):
                payloads.append(dict(payload))
            elif isinstance(payload, str):
                payloads.append(json.loads(payload))
        return payloads


def _export_workbook(
    *,
    brand: str,
    snapshot_date: date,
    rows: list[dict[str, Any]],
    output_root: Path,
) -> Path:
    folder_name = _brand_label(brand)
    output_dir = output_root / folder_name
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{folder_name}精细表_{snapshot_date.isoformat()}.xlsx"

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "精细表"

    columns = _columns_for_rows(rows)
    worksheet.append([label for _key, label in columns])
    for row in rows:
        worksheet.append([_cell_value(row, key, brand) for key, _label in columns])

    style_excel_worksheet(
        worksheet,
        width_by_header={
            "图片路径": 42,
            "图片URL": 42,
            "其他平台30天店铺拆分": 42,
        },
        text_headers=TEXT_HEADERS,
        min_width=10,
        max_width=60,
    )
    workbook.save(output_path)
    return output_path


def export_brand(
    request: _Request,
    *,
    brand: str,
    snapshot_date: date,
    output_root: Path,
    create_missing_snapshot: bool,
    refresh_snapshot: bool,
) -> tuple[Path, int]:
    repository = request.app.state.repository
    batch = _ensure_snapshot(
        request,
        brand=brand,
        snapshot_date=snapshot_date,
        create_missing_snapshot=create_missing_snapshot,
        refresh_snapshot=refresh_snapshot,
    )
    rows = _load_snapshot_rows(repository, batch)
    output_path = _export_workbook(
        brand=brand,
        snapshot_date=snapshot_date,
        rows=rows,
        output_root=output_root,
    )
    return output_path, len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export daily fine-table snapshots to shared folders")
    parser.add_argument("--brand", choices=sorted(TABLE_NAMES), default=None)
    parser.add_argument("--snapshot-date", type=date.fromisoformat, default=date.today())
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--no-create-snapshot", action="store_true")
    parser.add_argument("--refresh-snapshot", action="store_true")
    args = parser.parse_args()

    settings = load_settings(require_database=True)
    assert settings.database_url is not None
    output_root = args.output_root or settings.fine_table_export_root
    if output_root is None:
        raise ValueError("FINE_TABLE_EXPORT_ROOT is required")

    request = _Request(app=_App(state=_AppState(settings=settings, repository=ProductRepository(settings.database_url))))
    brands = [args.brand] if args.brand else sorted(TABLE_NAMES)

    for brand in brands:
        output_path, row_count = export_brand(
            request,
            brand=brand,
            snapshot_date=args.snapshot_date,
            output_root=output_root,
            create_missing_snapshot=not args.no_create_snapshot,
            refresh_snapshot=args.refresh_snapshot,
        )
        print(f"[{brand}] exported rows={row_count} path={output_path}")


if __name__ == "__main__":
    main()
