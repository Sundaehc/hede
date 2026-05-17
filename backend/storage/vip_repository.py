from __future__ import annotations

import re
from pathlib import Path

from openpyxl import load_workbook
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import insert as pg_insert

from domain.schema import METADATA
from domain.vip_schema import VIP_DAILY_TABLE, VIP_OPS_TABLE, JST_PRICE_TABLE, VIP_REALTIME_TABLE
from domain.vip_sources import (
    VIP_DAILY_COLUMN_ALIASES,
    VIP_OPS_COLUMN_ALIASES,
    JST_PRICE_COLUMN_ALIASES,
    VIP_REALTIME_COLUMN_ALIASES,
)


def _period_from_filename(filename: str) -> str | None:
    if "日罗" in filename:
        return "1d"
    if "月罗" in filename:
        return "30d"
    m = re.match(r"(\d+)", filename)
    if m:
        return f"{m.group(1)}d"
    return None


def _report_type_from_filename(filename: str) -> str | None:
    if "环比" in filename:
        return "环比"
    if "罗盘" in filename:
        return "罗盘"
    return None


class VipRepository:
    def __init__(self, database_url: str):
        import orjson

        def _json_serializer(value):
            return orjson.dumps(value).decode("utf-8")

        self.engine = create_engine(
            database_url,
            future=True,
            json_serializer=_json_serializer,
        )
        METADATA.create_all(self.engine, checkfirst=True)

    # ── vip_product_daily (环比/罗盘) ──────────────────────────────

    def import_daily(self, file_path: Path) -> dict[str, object]:
        filename = file_path.stem
        report_type = _report_type_from_filename(filename)
        period = _period_from_filename(filename)

        if report_type is None or period is None:
            return {"imported": 0, "message": f"无法识别报表类型/周期: {filename}"}

        rows = self._read_excel(file_path, VIP_DAILY_COLUMN_ALIASES)
        if not rows:
            return {"imported": 0, "message": "无数据行"}

        date_range = ""
        for row in rows:
            row["report_type"] = report_type
            row["period"] = period
            if not date_range and row.get("date"):
                date_range = str(row["date"])
            row["date_range"] = date_range

        # On conflict, update all columns except pk and key cols
        update_cols = [
            c for c in rows[0]
            if c not in ("id", "report_type", "period", "date_range", "goods_id")
        ]

        self._upsert(
            VIP_DAILY_TABLE,
            rows,
            ["report_type", "period", "date_range", "goods_id"],
            update_cols,
        )

        return {
            "imported": len(rows),
            "message": f"{filename}: {len(rows)} 条 ({report_type} / {period})",
        }

    # ── vip_product_realtime (实时商品) ─────────────────────────────

    def import_realtime(self, file_path: Path) -> dict[str, object]:
        rows = self._read_excel(file_path, VIP_REALTIME_COLUMN_ALIASES)
        if not rows:
            return {"imported": 0, "message": "无数据行"}

        update_cols = [c for c in rows[0] if c not in ("id", "goods_id")]

        self._upsert(VIP_REALTIME_TABLE, rows, ["goods_id"], update_cols)

        return {
            "imported": len(rows),
            "message": f"{file_path.name}: {len(rows)} 条",
        }

    # ── vip_product_ops (常态商品运营) ──────────────────────────────

    def import_ops(self, file_path: Path) -> dict[str, object]:
        rows = self._read_excel(file_path, VIP_OPS_COLUMN_ALIASES)
        if not rows:
            return {"imported": 0, "message": "无数据行"}

        update_cols = [c for c in rows[0] if c not in ("id", "goods_id")]

        self._upsert(VIP_OPS_TABLE, rows, ["goods_id"], update_cols)

        return {
            "imported": len(rows),
            "message": f"{file_path.name}: {len(rows)} 条",
        }

    # ── vip_product_price (物价信息) ──────────────────────────────

    def import_price(self, file_path: Path) -> dict[str, object]:
        """Import 物价信息 Excel. Header is on row 4 (1-indexed)."""
        wb = load_workbook(file_path, data_only=True, read_only=True)
        ws = wb.active
        assert ws is not None
        sheet_title = ws.title
        rows_iter = ws.iter_rows(values_only=True)

        # Skip first 3 rows (title, blank, blank), header on row 4
        for _ in range(3):
            next(rows_iter, None)

        header_row = next(rows_iter, None)
        if header_row is None:
            wb.close()
            return {"imported": 0, "message": "未找到表头（第4行）"}

        headers = [str(h).strip() if h else "" for h in header_row]
        column_map = {h: JST_PRICE_COLUMN_ALIASES[h] for h in headers if h in JST_PRICE_COLUMN_ALIASES}

        rows_to_upsert: list[dict] = []
        for row_num, row in enumerate(rows_iter, start=4):  # data starts at row 5
            record: dict[str, object] = {
                "source_workbook": file_path.stem,
                "source_sheet": sheet_title,
                "source_row_number": str(row_num),
            }
            raw: dict[str, object] = {}
            for idx, h in enumerate(headers):
                value = row[idx] if idx < len(row) else None
                raw[h] = value
                col = column_map.get(h)
                if col:
                    record[col] = str(value).strip() if value is not None else None
            record["raw_payload"] = raw
            rows_to_upsert.append(record)

        wb.close()

        if not rows_to_upsert:
            return {"imported": 0, "message": "无数据行"}

        from sqlalchemy import delete

        codes = {str(r.get("goods_code", "")) for r in rows_to_upsert}
        with self.engine.begin() as conn:
            for i in range(0, len(codes), 500):
                chunk = list(codes)[i:i + 500]
                conn.execute(delete(JST_PRICE_TABLE).where(JST_PRICE_TABLE.c.goods_code.in_(chunk)))
        self._batch_insert(JST_PRICE_TABLE, rows_to_upsert)

        return {
            "imported": len(rows_to_upsert),
            "message": f"{file_path.name}: {len(rows_to_upsert)} 条",
        }

    # ── import_all: 按日期目录全量导入 ─────────────────────────────

    def import_all(self, dir_path: Path) -> dict[str, object]:
        if not dir_path.exists():
            return {"success": False, "message": f"目录不存在: {dir_path}"}

        batch_date = dir_path.name
        results: list[dict] = []
        daily_files: list[Path] = []

        for ext in (".xlsx", ".xlsm", ".xls"):
            for file_path in sorted(dir_path.glob(f"*{ext}")):
                if file_path.name.startswith("~$"):
                    continue
                filename = file_path.stem

                if "实时商品" in filename:
                    results.append(self.import_realtime(file_path))
                elif "常态商品运营" in filename:
                    results.append(self.import_ops(file_path))
                elif "合并" in filename and "物价" in filename:
                    results.append(self.import_price(file_path))
                elif _report_type_from_filename(filename) and _period_from_filename(filename):
                    daily_files.append(file_path)

        for file_path in daily_files:
            results.append(self.import_daily(file_path))

        total = sum(r.get("imported", 0) for r in results)
        return {
            "success": True,
            "batch_date": batch_date,
            "total_imported": total,
            "details": results,
        }

    # ── Helpers ────────────────────────────────────────────────────

    def _upsert(self, table, rows: list[dict], key_cols: list[str], update_cols: list[str], chunk_size: int = 500) -> None:
        """Upsert rows using ON CONFLICT DO UPDATE."""
        for i in range(0, len(rows), chunk_size):
            chunk = rows[i:i + chunk_size]
            set_ = {col: getattr(pg_insert(table).excluded, col) for col in update_cols}
            stmt = pg_insert(table).values(chunk).on_conflict_do_update(
                index_elements=key_cols,
                set_=set_,
            )
            with self.engine.begin() as conn:
                conn.execute(stmt)

    def _batch_insert(self, table, rows: list[dict], chunk_size: int = 500) -> None:
        from sqlalchemy import insert

        with self.engine.begin() as conn:
            for i in range(0, len(rows), chunk_size):
                conn.execute(insert(table), rows[i:i + chunk_size])

    def _read_excel(self, file_path: Path, aliases: dict[str, str]) -> list[dict]:
        """Read an Excel file, map headers to canonical columns, return rows as dicts."""
        wb = load_workbook(file_path, data_only=True, read_only=True)
        ws = wb.active
        assert ws is not None
        sheet_title = ws.title
        iterator = ws.iter_rows(values_only=True)
        header_row = next(iterator, None)
        if header_row is None:
            wb.close()
            return []

        headers = [str(h).strip() if h else "" for h in header_row]
        column_map = {h: aliases[h] for h in headers if h in aliases}

        rows: list[dict] = []
        for row_num, row in enumerate(iterator, start=2):
            record: dict[str, object] = {
                "source_workbook": file_path.stem,
                "source_sheet": sheet_title,
                "source_row_number": str(row_num),
            }
            raw: dict[str, object] = {}
            for idx, h in enumerate(headers):
                value = row[idx] if idx < len(row) else None
                raw[h] = value
                col = column_map.get(h)
                if col:
                    record[col] = str(value).strip() if value is not None else None
            record["raw_payload"] = raw
            rows.append(record)

        wb.close()
        return rows
