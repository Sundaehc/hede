from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError

from domain.product_size_group_mapping_schema import PRODUCT_SIZE_GROUP_MAPPINGS_TABLE
from domain.schema import PRODUCT_TABLES
from domain.size_group_schema import SIZE_GROUP_ITEMS_TABLE, SIZE_GROUPS_TABLE


class SizeGroupInUseError(Exception):
    def __init__(self, product_count: int):
        super().__init__(f"尺码组已被 {product_count} 个商品使用")
        self.product_count = product_count


class SizeGroupRepository:
    def __init__(self, engine):
        self.engine = engine

    @staticmethod
    def _normalized_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        seen_sizes: set[str] = set()
        seen_barcodes: set[str] = set()
        for index, item in enumerate(items, start=1):
            size_name = str(item.get("size_name") or "").strip()
            barcode = str(item.get("barcode") or "").strip()
            if not size_name or not barcode:
                raise ValueError("尺码和条码不能为空")
            if size_name in seen_sizes:
                raise ValueError(f"尺码 {size_name} 重复")
            if barcode in seen_barcodes:
                raise ValueError(f"条码 {barcode} 重复")
            seen_sizes.add(size_name)
            seen_barcodes.add(barcode)
            normalized.append({"size_name": size_name, "barcode": barcode, "sort_order": index})
        if not normalized:
            raise ValueError("请至少维护一条尺码明细")
        return normalized

    @staticmethod
    def _groups_from_rows(group_rows, item_rows, usage_by_name: dict[str, int]) -> list[dict[str, Any]]:
        items_by_group: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for row in item_rows:
            item = dict(row)
            items_by_group[int(item["size_group_id"])].append({
                "id": int(item["id"]),
                "size_name": item["size_name"],
                "barcode": item["barcode"],
                "sort_order": int(item["sort_order"] or 0),
            })
        return [
            {
                "id": int(row["id"]),
                "name": row["name"],
                "product_count": usage_by_name.get(str(row["name"]), 0),
                "items": items_by_group.get(int(row["id"]), []),
            }
            for row in group_rows
        ]

    def _usage_by_name(self, connection) -> dict[str, int]:
        usage_by_name: dict[str, int] = defaultdict(int)
        for product_table in PRODUCT_TABLES.values():
            rows = connection.execute(
                select(product_table.c.size_range, func.count().label("count"))
                .where(product_table.c.deleted_at.is_(None))
                .where(product_table.c.size_range.is_not(None))
                .where(func.trim(product_table.c.size_range) != "")
                .group_by(product_table.c.size_range)
            ).mappings()
            for row in rows:
                name = str(row["size_range"] or "").strip()
                if name:
                    usage_by_name[name] += int(row["count"] or 0)
        mapping_rows = connection.execute(
            select(PRODUCT_SIZE_GROUP_MAPPINGS_TABLE.c.size_group_name, func.count().label("count"))
            .group_by(PRODUCT_SIZE_GROUP_MAPPINGS_TABLE.c.size_group_name)
        ).mappings()
        for row in mapping_rows:
            name = str(row["size_group_name"] or "").strip()
            if name:
                usage_by_name[name] += int(row["count"] or 0)
        return dict(usage_by_name)

    def list_groups(self) -> list[dict[str, Any]]:
        with self.engine.connect() as connection:
            group_rows = connection.execute(
                select(SIZE_GROUPS_TABLE).order_by(SIZE_GROUPS_TABLE.c.name)
            ).mappings().all()
            item_rows = connection.execute(
                select(SIZE_GROUP_ITEMS_TABLE)
                .order_by(SIZE_GROUP_ITEMS_TABLE.c.size_group_id, SIZE_GROUP_ITEMS_TABLE.c.sort_order, SIZE_GROUP_ITEMS_TABLE.c.id)
            ).mappings().all()
            usage_by_name = self._usage_by_name(connection)
        return self._groups_from_rows(group_rows, item_rows, usage_by_name)

    def get_group(self, size_group_id: int) -> dict[str, Any] | None:
        return next((item for item in self.list_groups() if item["id"] == size_group_id), None)

    def create_group(self, *, name: str, items: list[dict[str, Any]]) -> dict[str, Any]:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("尺码组名称不能为空")
        normalized_items = self._normalized_items(items)
        try:
            with self.engine.begin() as connection:
                size_group_id = connection.execute(
                    insert(SIZE_GROUPS_TABLE).values(name=normalized_name).returning(SIZE_GROUPS_TABLE.c.id)
                ).scalar_one()
                connection.execute(
                    insert(SIZE_GROUP_ITEMS_TABLE),
                    [{"size_group_id": size_group_id, **item} for item in normalized_items],
                )
        except IntegrityError as exc:
            raise ValueError(f"尺码组 {normalized_name} 已存在") from exc
        result = self.get_group(int(size_group_id))
        assert result is not None
        return result

    def update_group(self, size_group_id: int, *, name: str, items: list[dict[str, Any]]) -> dict[str, Any] | None:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("尺码组名称不能为空")
        normalized_items = self._normalized_items(items)
        try:
            with self.engine.begin() as connection:
                previous_name = connection.execute(
                    select(SIZE_GROUPS_TABLE.c.name).where(SIZE_GROUPS_TABLE.c.id == size_group_id)
                ).scalar()
                if previous_name is None:
                    return None
                connection.execute(
                    update(SIZE_GROUPS_TABLE)
                    .where(SIZE_GROUPS_TABLE.c.id == size_group_id)
                    .values(name=normalized_name, updated_at=func.date_trunc("minute", func.now()))
                )
                if normalized_name != previous_name:
                    for product_table in PRODUCT_TABLES.values():
                        connection.execute(
                            update(product_table)
                            .where(product_table.c.size_range == previous_name)
                            .values(size_range=normalized_name)
                        )
                    connection.execute(
                        update(PRODUCT_SIZE_GROUP_MAPPINGS_TABLE)
                        .where(PRODUCT_SIZE_GROUP_MAPPINGS_TABLE.c.size_group_name == previous_name)
                        .values(size_group_name=normalized_name)
                    )
                connection.execute(delete(SIZE_GROUP_ITEMS_TABLE).where(SIZE_GROUP_ITEMS_TABLE.c.size_group_id == size_group_id))
                connection.execute(
                    insert(SIZE_GROUP_ITEMS_TABLE),
                    [{"size_group_id": size_group_id, **item} for item in normalized_items],
                )
        except IntegrityError as exc:
            raise ValueError(f"尺码组 {normalized_name} 已存在") from exc
        return self.get_group(size_group_id)

    def delete_group(self, size_group_id: int) -> bool:
        with self.engine.begin() as connection:
            name = connection.execute(
                select(SIZE_GROUPS_TABLE.c.name).where(SIZE_GROUPS_TABLE.c.id == size_group_id)
            ).scalar()
            if name is None:
                return False
            usage_by_name = self._usage_by_name(connection)
            product_count = usage_by_name.get(str(name), 0)
            if product_count:
                raise SizeGroupInUseError(product_count)
            connection.execute(delete(SIZE_GROUPS_TABLE).where(SIZE_GROUPS_TABLE.c.id == size_group_id))
        return True
