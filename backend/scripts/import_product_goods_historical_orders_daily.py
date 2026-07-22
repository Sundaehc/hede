"""Replace the latest daily product-goods orders from the newest brand workbooks."""

from __future__ import annotations

import argparse
import re
import traceback
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from config import load_settings
from scripts.import_product_goods_historical_orders import iter_rows, replace_order_date_rows
from storage.task_status_repository import ScheduledTaskStatusRepository


TASK_NAME_PREFIX = "import_product_goods_orders"
WORKBOOK_SUFFIXES = {".xlsx", ".xlsm"}
MONTH_DAY_PATTERN = re.compile(r"(?<!\d)(?P<month>0?[1-9]|1[0-2])[._-](?P<day>0?[1-9]|[12]\d|3[01])(?!\d)")
YEAR_PATTERN = re.compile(r"(?<!\d)(20\d{2})(?!\d)")


@dataclass(frozen=True)
class BrandSource:
    brand: str
    root: Path
    required_name_parts: tuple[str, ...]
    excluded_name_parts: tuple[str, ...] = ()


def _date_hint(path: Path) -> date | None:
    month_day_matches = list(MONTH_DAY_PATTERN.finditer(path.stem))
    if not month_day_matches:
        return None
    year_matches = YEAR_PATTERN.findall(str(path.parent))
    year = int(year_matches[-1]) if year_matches else date.today().year
    match = month_day_matches[-1]
    try:
        return date(year, int(match.group("month")), int(match.group("day")))
    except ValueError:
        return None


def latest_workbook(source: BrandSource) -> Path:
    if not source.root.exists():
        raise FileNotFoundError(f"目录不存在: {source.root}")

    candidates = [
        path
        for path in source.root.rglob("*")
        if path.is_file()
        and path.suffix.lower() in WORKBOOK_SUFFIXES
        and not path.name.startswith("~$")
        and all(part in path.name for part in source.required_name_parts)
        and not any(part in path.name for part in source.excluded_name_parts)
    ]
    if not candidates:
        raise FileNotFoundError(f"未找到货品表文件: {source.root}")
    return max(
        candidates,
        key=lambda path: (_date_hint(path) or date.min, path.stat().st_mtime, path.name),
    )


def _latest_order_rows(path: Path, *, brand: str) -> tuple[date, list[dict[str, object]]]:
    rows = list(iter_rows(path, brand=brand))
    if not rows:
        raise ValueError(f"订单数据页没有有效记录: {path}")
    latest_date = max(row["order_date"] for row in rows)
    assert isinstance(latest_date, date)
    return latest_date, [row for row in rows if row["order_date"] == latest_date]


def _run_source(source: BrandSource, *, status_repo: ScheduledTaskStatusRepository, dry_run: bool) -> dict[str, object]:
    workbook = latest_workbook(source)
    order_date, rows = _latest_order_rows(workbook, brand=source.brand)
    task_name = f"{TASK_NAME_PREFIX}_{source.brand}"
    result: dict[str, object] = {
        "brand": source.brand,
        "source": str(workbook),
        "order_date": order_date.isoformat(),
        "rows": len(rows),
    }
    if dry_run:
        return result

    status_repo.mark_running(task_name, order_date, source_path=workbook)
    try:
        result.update(replace_order_date_rows(rows, brand=source.brand, order_date=order_date))
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        status_repo.mark_finished(
            task_name,
            order_date,
            status="failed",
            message=message,
            result={**result, "traceback": traceback.format_exc()},
            source_path=workbook,
        )
        raise
    status_repo.mark_finished(
        task_name,
        order_date,
        status="success",
        message=f"订单数据已更新: {len(rows)} 条",
        result=result,
        source_path=workbook,
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="导入男女鞋最新货品表中的最新订单日期")
    parser.add_argument("--brand", choices=("cbanner_mens", "cbanner_womens", "eblan"), action="append")
    parser.add_argument("--mens-root", type=Path, default=None)
    parser.add_argument("--womens-root", type=Path, default=None)
    parser.add_argument("--eblan-root", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    settings = load_settings(require_database=not args.dry_run)
    mens_root = args.mens_root or settings.cbanner_mens_group_source
    womens_root = args.womens_root or settings.cbanner_womens_product_detail_source
    eblan_root = args.eblan_root or settings.eblan_product_goods_order_source
    assert mens_root is not None, "CBANNER_MENS_GROUP_SOURCE is required"
    assert womens_root is not None, "CBANNER_WOMENS_PRODUCT_DETAIL_SOURCE is required"
    assert eblan_root is not None, "EBLAN_PRODUCT_DETAIL_SOURCE is required"
    sources = (
        BrandSource("cbanner_womens", womens_root, ("赫德货品表", "千百度"), ("男鞋",)),
        BrandSource("cbanner_mens", mens_root, ("赫德货品表", "千百度男鞋")),
        BrandSource("eblan", eblan_root, ("伊伴货品表",)),
    )
    selected_brands = set(args.brand or ("cbanner_womens", "cbanner_mens", "eblan"))
    status_repo = ScheduledTaskStatusRepository(settings.database_url) if settings.database_url else None
    failed = False
    for source in sources:
        if source.brand not in selected_brands:
            continue
        try:
            assert status_repo is not None or args.dry_run
            result = _run_source(source, status_repo=status_repo, dry_run=args.dry_run)
            print(f"[OK] {result}")
        except Exception as exc:  # pragma: no cover - task logging is exercised in production
            failed = True
            print(f"[FAILED] {source.brand}: {type(exc).__name__}: {exc}\n{traceback.format_exc()}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
