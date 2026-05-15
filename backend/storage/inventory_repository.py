from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

from pathlib import Path

from openpyxl import load_workbook
from sqlalchemy import and_, case, create_engine, delete, desc, func, insert, select, update

from domain.inventory_schema import INVENTORY_DETAIL_TABLE, INVENTORY_TABLE, JST_STOCK_TABLE, SUPPLIER_TABLE, WAREHOUSE_TABLE
from domain.schema import METADATA


class InventoryRepository:
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

    # ── Inventory Records ──────────────────────────────────────────

    def list_records(
        self,
        *,
        date_start: str | None = None,
        date_end: str | None = None,
        supplier: str | None = None,
        warehouse: str | None = None,
        document_type: str | None = None,
        page: int,
        page_size: int,
    ) -> dict[str, object]:
        table = INVENTORY_TABLE
        count_statement = select(func.count()).select_from(table)
        items_statement = select(table)

        conditions = []
        if date_start:
            conditions.append(table.c.date >= date_start)
        if date_end:
            conditions.append(table.c.date <= date_end)
        if supplier:
            conditions.append(table.c.supplier == supplier)
        if warehouse:
            conditions.append(table.c.warehouse == warehouse)
        if document_type:
            conditions.append(table.c.document_type == document_type)

        if conditions:
            criterion = conditions[0] if len(conditions) == 1 else and_(*conditions)
            items_statement = items_statement.where(criterion)
            count_statement = count_statement.where(criterion)

        items_statement = items_statement.order_by(desc(table.c.id)).offset((page - 1) * page_size).limit(page_size)

        with self.engine.connect() as connection:
            total = connection.execute(count_statement).scalar_one()
            items = [dict(row) for row in connection.execute(items_statement).mappings()]

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def get_record(self, record_id: int) -> dict[str, object] | None:
        table = INVENTORY_TABLE
        statement = select(table).where(table.c.id == record_id)
        with self.engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
        return None if row is None else dict(row)

    def create_record(self, record: Mapping[str, object]) -> dict[str, object]:
        table = INVENTORY_TABLE
        statement = insert(table).values(**self._prepare_record(record)).returning(table)
        with self.engine.begin() as connection:
            row = connection.execute(statement).mappings().one()
        return dict(row)

    def update_record(self, record_id: int, record: Mapping[str, object]) -> dict[str, object] | None:
        table = INVENTORY_TABLE
        payload = self._prepare_record(record)
        payload.pop("id", None)
        statement = update(table).where(table.c.id == record_id).values(**payload).returning(table)
        with self.engine.begin() as connection:
            row = connection.execute(statement).mappings().first()
        return None if row is None else dict(row)

    def delete_record(self, record_id: int) -> bool:
        table = INVENTORY_TABLE
        statement = delete(table).where(table.c.id == record_id)
        with self.engine.begin() as connection:
            result = connection.execute(statement)
        return result.rowcount > 0

    def delete_records(self, ids: list[int]) -> int:
        if not ids:
            return 0
        table = INVENTORY_TABLE
        statement = delete(table).where(table.c.id.in_(ids))
        with self.engine.begin() as connection:
            result = connection.execute(statement)
        return result.rowcount

    # ── Suppliers ──────────────────────────────────────────────────

    def list_suppliers(self) -> list[dict[str, object]]:
        statement = select(SUPPLIER_TABLE).order_by(SUPPLIER_TABLE.c.id)
        with self.engine.connect() as connection:
            return [dict(row) for row in connection.execute(statement).mappings()]

    def create_supplier(self, data: Mapping[str, object]) -> dict[str, object]:
        statement = insert(SUPPLIER_TABLE).values(**dict(data)).returning(SUPPLIER_TABLE)
        with self.engine.begin() as connection:
            row = connection.execute(statement).mappings().one()
        return dict(row)

    def update_supplier(self, supplier_id: int, data: Mapping[str, object]) -> dict[str, object] | None:
        payload = dict(data)
        payload.pop("id", None)
        statement = update(SUPPLIER_TABLE).where(SUPPLIER_TABLE.c.id == supplier_id).values(**payload).returning(SUPPLIER_TABLE)
        with self.engine.begin() as connection:
            row = connection.execute(statement).mappings().first()
        return None if row is None else dict(row)

    def delete_supplier(self, supplier_id: int) -> bool:
        statement = delete(SUPPLIER_TABLE).where(SUPPLIER_TABLE.c.id == supplier_id)
        with self.engine.begin() as connection:
            result = connection.execute(statement)
        return result.rowcount > 0

    def get_supplier_by_name(self, name: str) -> dict[str, object] | None:
        statement = select(SUPPLIER_TABLE).where(SUPPLIER_TABLE.c.name == name)
        with self.engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
        return None if row is None else dict(row)

    # ── Warehouses ─────────────────────────────────────────────────

    def list_warehouses(self) -> list[dict[str, object]]:
        statement = select(WAREHOUSE_TABLE).order_by(WAREHOUSE_TABLE.c.id)
        with self.engine.connect() as connection:
            return [dict(row) for row in connection.execute(statement).mappings()]

    def create_warehouse(self, data: Mapping[str, object]) -> dict[str, object]:
        statement = insert(WAREHOUSE_TABLE).values(**dict(data)).returning(WAREHOUSE_TABLE)
        with self.engine.begin() as connection:
            row = connection.execute(statement).mappings().one()
        return dict(row)

    def update_warehouse(self, warehouse_id: int, data: Mapping[str, object]) -> dict[str, object] | None:
        payload = dict(data)
        payload.pop("id", None)
        statement = update(WAREHOUSE_TABLE).where(WAREHOUSE_TABLE.c.id == warehouse_id).values(**payload).returning(WAREHOUSE_TABLE)
        with self.engine.begin() as connection:
            row = connection.execute(statement).mappings().first()
        return None if row is None else dict(row)

    def delete_warehouse(self, warehouse_id: int) -> bool:
        statement = delete(WAREHOUSE_TABLE).where(WAREHOUSE_TABLE.c.id == warehouse_id)
        with self.engine.begin() as connection:
            result = connection.execute(statement)
        return result.rowcount > 0

    def get_warehouse_by_name(self, name: str) -> dict[str, object] | None:
        statement = select(WAREHOUSE_TABLE).where(WAREHOUSE_TABLE.c.name == name)
        with self.engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
        return None if row is None else dict(row)

    # ── Inventory Details ───────────────────────────────────────────

    def list_details(self, document_id: int) -> list[dict[str, object]]:
        table = INVENTORY_DETAIL_TABLE
        statement = select(table).where(table.c.document_id == document_id).order_by(table.c.id)
        with self.engine.connect() as connection:
            return [dict(row) for row in connection.execute(statement).mappings()]

    def create_detail(self, data: Mapping[str, object]) -> dict[str, object]:
        table = INVENTORY_DETAIL_TABLE
        payload = self._coerce_empty(data)
        statement = insert(table).values(**payload).returning(table)
        with self.engine.begin() as connection:
            row = connection.execute(statement).mappings().one()
        self.recalculate_totals(payload.get("document_id"))
        return dict(row)

    def update_detail(self, detail_id: int, data: Mapping[str, object]) -> dict[str, object] | None:
        table = INVENTORY_DETAIL_TABLE
        payload = self._coerce_empty(data)
        document_id = payload.pop("document_id", None)
        statement = update(table).where(table.c.id == detail_id).values(**payload).returning(table)
        with self.engine.begin() as connection:
            row = connection.execute(statement).mappings().first()
        if row is None:
            return None
        if document_id is not None:
            self.recalculate_totals(document_id)
        else:
            detail = dict(row)
            self.recalculate_totals(detail.get("document_id"))
        return dict(row)

    def delete_detail(self, detail_id: int) -> bool:
        table = INVENTORY_DETAIL_TABLE
        # Get document_id before deleting for recalculation
        with self.engine.connect() as connection:
            detail = connection.execute(select(table.c.document_id).where(table.c.id == detail_id)).first()
        document_id = detail[0] if detail else None
        statement = delete(table).where(table.c.id == detail_id)
        with self.engine.begin() as connection:
            result = connection.execute(statement)
        if result.rowcount > 0 and document_id is not None:
            self.recalculate_totals(document_id)
        return result.rowcount > 0

    def recalculate_totals(self, document_id: object) -> None:
        table = INVENTORY_DETAIL_TABLE
        stmt = select(
            func.coalesce(func.sum(table.c.quantity), 0),
            func.coalesce(func.sum(table.c.amount), 0),
        ).where(table.c.document_id == document_id)
        with self.engine.connect() as connection:
            total_count, amount = connection.execute(stmt).one()
        update_stmt = (
            update(INVENTORY_TABLE)
            .where(INVENTORY_TABLE.c.id == document_id)
            .values(total_count=total_count, amount=amount)
        )
        with self.engine.begin() as connection:
            connection.execute(update_stmt)

    # ── Ending Inventory ─────────────────────────────────────────────

    def get_ending_inventory(
        self,
        *,
        jst_stock_root: Path | None,
        stock_date: str,
        date_start: str | None = None,
        date_end: str | None = None,
        product_code: str | None = None,
        page: int,
        page_size: int,
    ) -> dict[str, object]:
        # Read beginning stock from DB (or Excel fallback)
        beginning_stock = self._read_jst_stock(jst_stock_root, stock_date) if jst_stock_root else {}

        # Build the aggregated inventory changes query
        detail = INVENTORY_DETAIL_TABLE
        record = INVENTORY_TABLE

        inbound = func.sum(case(
            (record.c.document_type == "工厂进货单", detail.c.quantity),
            else_=0,
        ))
        return_qty = func.sum(case(
            (record.c.document_type == "工厂退货单", detail.c.quantity),
            else_=0,
        ))

        joined = detail.join(record, detail.c.document_id == record.c.id)
        conditions = []
        if date_start:
            conditions.append(record.c.date >= date_start)
        if date_end:
            conditions.append(record.c.date <= date_end)
        if product_code:
            conditions.append(detail.c.product_code.like(f"{product_code}%"))
        criterion = and_(*conditions) if conditions else None

        base = (
            select(
                detail.c.product_code,
                detail.c.product_name,
                detail.c.color_spec,
                inbound.label("inbound_qty"),
                return_qty.label("return_qty"),
            )
            .select_from(joined)
            .group_by(detail.c.product_code, detail.c.product_name, detail.c.color_spec)
        )
        if criterion is not None:
            base = base.where(criterion)

        # Subquery for counting total groups
        sub = base.subquery()
        count_stmt = select(func.count()).select_from(sub)
        with self.engine.connect() as connection:
            total = connection.execute(count_stmt).scalar_one()

        # Paginated query
        data_stmt = (
            select(sub)
            .order_by(sub.c.product_code)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        with self.engine.connect() as connection:
            rows = [dict(row) for row in connection.execute(data_stmt).mappings()]

        # Merge with beginning stock and calculate ending inventory
        from decimal import Decimal

        def _fmt(v: int | Decimal) -> str:
            if isinstance(v, int):
                return str(v)
            d = v.normalize()
            return str(d) if d.as_tuple().exponent < 0 else str(int(d))

        items = []
        for row in rows:
            code = row.get("product_code") or ""
            beginning = beginning_stock.get(str(code), 0)
            inbound_val = row.get("inbound_qty") or Decimal("0")
            return_val = row.get("return_qty") or Decimal("0")
            ending = beginning + inbound_val - return_val

            items.append({
                "product_code": row.get("product_code"),
                "product_name": row.get("product_name"),
                "color_spec": row.get("color_spec"),
                "beginning_qty": _fmt(beginning),
                "inbound_qty": _fmt(inbound_val),
                "return_qty": _fmt(return_val),
                "ending_qty": _fmt(ending),
            })

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def _read_jst_stock(self, jst_stock_root: Path | None, stock_date: str) -> dict:
        """Read beginning stock from DB, fallback to Excel if no data."""
        if jst_stock_root is None:
            return {}

        # Try DB first
        table = JST_STOCK_TABLE
        stmt = select(table.c.product_code, table.c.available_qty).where(table.c.stock_date == stock_date)
        with self.engine.connect() as connection:
            rows = connection.execute(stmt).all()

        if rows:
            return {str(row.product_code): int(row.available_qty) for row in rows}

        # Fallback to Excel
        return self._read_jst_stock_from_excel(jst_stock_root, stock_date)

    def import_jst_stock(self, jst_stock_root: Path | None, stock_date: str) -> dict[str, object]:
        """Import daily stock from 聚水潭 Excel into jst_daily_stock table."""
        if jst_stock_root is None:
            return {"imported": 0, "message": "JST_STOCK_ROOT 未配置"}

        data = self._read_jst_stock_from_excel(jst_stock_root, stock_date)
        if not data:
            return {"imported": 0, "message": f"未找到 {stock_date} 的库存数据"}

        table = JST_STOCK_TABLE
        imported = 0
        with self.engine.begin() as connection:
            for product_code, qty in data.items():
                # UPSERT: delete existing then insert
                connection.execute(
                    delete(table).where(
                        and_(table.c.stock_date == stock_date, table.c.product_code == product_code)
                    )
                )
                connection.execute(
                    insert(table).values(
                        stock_date=stock_date,
                        product_code=product_code,
                        available_qty=qty,
                    )
                )
                imported += 1

        return {"imported": imported, "message": f"已导入 {imported} 条 {stock_date} 库存数据"}

    @staticmethod
    def _read_jst_stock_from_excel(jst_stock_root: Path, stock_date: str) -> dict:
        """Read product available stock from 聚水潭 daily stock Excel."""

        stock_dir = jst_stock_root / stock_date
        if not stock_dir.exists():
            return {}

        # Try common extensions
        candidates = []
        for ext in (".xlsx", ".xls", ".xlsm"):
            p = stock_dir / f"商品库存{ext}"
            if p.exists():
                candidates.append(p)

        stock_file = candidates[0] if candidates else None
        if stock_file is None:
            return {}

        wb = load_workbook(stock_file, data_only=True, read_only=True)
        ws = wb["Sheet1"] if "Sheet1" in wb.sheetnames else wb.active
        if ws is None:
            wb.close()
            return {}
        iterator = ws.iter_rows(values_only=True)
        header_row = next(iterator, None)
        if header_row is None:
            wb.close()
            return {}

        headers = [str(h).strip() if h else "" for h in header_row]

        # Find column indices for "商品编码" and "可用数"
        code_idx = None
        avail_idx = None
        for i, h in enumerate(headers):
            if "商品编码" in h or h == "商品编码":
                code_idx = i
            elif "可用数" in h or "可用库存" in h:
                avail_idx = i

        if code_idx is None or avail_idx is None:
            wb.close()
            return {}

        result = {}
        for row in iterator:
            code = str(row[code_idx]).strip() if code_idx < len(row) and row[code_idx] is not None else ""
            avail = row[avail_idx] if avail_idx < len(row) else None
            if code and avail is not None:
                try:
                    result[code] = int(float(str(avail)))
                except Exception:
                    result[code] = 0

        wb.close()
        return result

    # ── Helpers ────────────────────────────────────────────────────

    @staticmethod
    def _coerce_empty(data: Mapping[str, object]) -> dict[str, object]:
        return {k: (None if v == "" else v) for k, v in data.items()}

    @staticmethod
    def _prepare_record(record: Mapping[str, object]) -> dict[str, object]:
        payload = {}
        for key, value in record.items():
            if value == "":
                payload[key] = None
            else:
                payload[key] = value
        raw_payload = payload.get("raw_payload")
        if isinstance(raw_payload, Mapping):
            payload["raw_payload"] = {
                k: str(v) if isinstance(v, Decimal) else v
                for k, v in raw_payload.items()
            }
        return payload
