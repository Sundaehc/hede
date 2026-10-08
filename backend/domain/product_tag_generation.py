from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import and_, delete, exists, insert, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from domain.product_tag_schema import (
    PRODUCT_STYLE_ENTITIES_TABLE,
    PRODUCT_TAG_ASSIGNMENTS_TABLE,
    PRODUCT_TAG_DEFINITIONS_TABLE,
    ensure_product_tag_schema,
)


GENERATED_TAG_GROUPS = (
    "品类",
    "季节",
    "年份",
    "等级",
    "材质",
    "结构",
    "风格",
    "功能",
    "运营",
    "数据质量",
)

_GROUP_SORT_ORDER = {group: index for index, group in enumerate(GENERATED_TAG_GROUPS)}
_YEAR_PATTERN = re.compile(r"(?:19|20)\d{2}|\d{2}(?=年)")
_TOKEN_SPLIT_PATTERN = re.compile(r"[,，、;；+/]+")
_BUSINESS_TIMEZONE = timezone(timedelta(hours=8))
_SELECTED_FIELDS = (
    "category", "season_category", "year", "product_level", "upper_material",
    "lining_material", "outsole_material", "sole_style", "fashion_elements",
    "toe_shape", "closure_type", "selling_points", "internal_height_increase",
    "launch_date", "image_path",
)


def _text(value: object) -> str:
    normalized = str(value or "").strip()
    return "" if normalized in {"0", "无", "暂无", "未知", "None", "null"} else normalized


def _tag_code(field: str, value: str) -> str:
    digest = hashlib.sha1(f"{field}:{value}".encode("utf-8")).hexdigest()[:12]
    return f"archive_{field}_{digest}"


def _apply_manual_overrides(
    generated: dict[str, dict[str, object]],
    existing: dict[str, dict[str, object]],
) -> dict[str, dict[str, object]]:
    merged = {}
    for code, definition in generated.items():
        override = existing.get(code)
        if not override or not override.get("is_manual_override"):
            merged[code] = definition
            continue
        merged[code] = {
            **definition,
            "tag_name": override["tag_name"],
            "tag_group": override["tag_group"],
            "is_active": override["is_active"],
            "is_manual_override": True,
            "sort_order": override["sort_order"],
        }
    return merged


def _add_tag(
    definitions: dict[str, dict[str, object]],
    product_tags: dict[tuple[str, int], dict[str, dict[str, object]]],
    *,
    brand: str,
    product_id: int,
    field: str,
    group: str,
    name: str,
    value: str,
) -> None:
    normalized = _text(value)
    if not normalized or group not in _GROUP_SORT_ORDER:
        return
    code = _tag_code(field, normalized)
    definitions.setdefault(
        code,
        {
            "tag_code": code,
            "tag_name": name,
            "tag_group": group,
            "value_type": "multiple",
            "source_type": "rule",
            "is_active": True,
            "is_manual_override": False,
            "sort_order": _GROUP_SORT_ORDER[group],
        },
    )
    product_tags[(brand, product_id)][code] = {
        "field": field,
        "value": normalized,
    }


def _add_exact_field_tags(
    row: dict[str, object],
    brand: str,
    product_id: int,
    definitions: dict[str, dict[str, object]],
    product_tags: dict[tuple[str, int], dict[str, dict[str, object]]],
) -> None:
    exact_fields = (
        ("category", "品类", "品类"),
        ("season_category", "季节", "季节"),
        ("product_level", "等级", "等级"),
        ("toe_shape", "结构", "鞋头"),
        ("closure_type", "结构", "闭合方式"),
        ("sole_style", "结构", "跟底款式"),
    )
    for field, group, label in exact_fields:
        value = _text(row.get(field))
        if value:
            _add_tag(
                definitions,
                product_tags,
                brand=brand,
                product_id=product_id,
                field=field,
                group=group,
                name=f"{label}：{value}",
                value=value,
            )

    year = _text(row.get("year"))
    year_match = _YEAR_PATTERN.search(year)
    if year_match:
        year_value = year_match.group(0)
        _add_tag(
            definitions,
            product_tags,
            brand=brand,
            product_id=product_id,
            field="year",
            group="年份",
            name=f"年份：{year_value}",
            value=year_value,
        )


def _add_keyword_tags(
    row: dict[str, object],
    brand: str,
    product_id: int,
    definitions: dict[str, dict[str, object]],
    product_tags: dict[tuple[str, int], dict[str, dict[str, object]]],
) -> None:
    keyword_rules = (
        ("upper_material", "材质", "鞋面材质：牛皮", ("牛皮",)),
        ("upper_material", "材质", "鞋面材质：羊皮", ("羊皮",)),
        ("upper_material", "材质", "鞋面材质：猪皮", ("猪皮",)),
        ("upper_material", "材质", "鞋面材质：马皮", ("马皮",)),
        ("upper_material", "材质", "鞋面材质：头层", ("头层",)),
        ("upper_material", "材质", "鞋面材质：剖层", ("剖层",)),
        ("upper_material", "材质", "鞋面材质：织物", ("织物",)),
        ("upper_material", "材质", "鞋面材质：网布", ("网布",)),
        ("upper_material", "材质", "鞋面材质：网面", ("网面",)),
        ("upper_material", "材质", "鞋面材质：合成革", ("合成革",)),
        ("upper_material", "材质", "鞋面材质：超纤", ("超纤",)),
        ("upper_material", "材质", "鞋面材质：复合材料", ("复合材料",)),
        ("lining_material", "材质", "内里材质：绒", ("绒",)),
        ("lining_material", "材质", "内里材质：毛", ("毛",)),
        ("lining_material", "材质", "内里材质：羊毛", ("羊毛",)),
        ("lining_material", "材质", "内里材质：织物", ("织物",)),
        ("lining_material", "材质", "内里材质：网布", ("网布",)),
        ("lining_material", "材质", "内里材质：布里", ("布里",)),
        ("lining_material", "材质", "内里材质：皮", ("皮",)),
        ("outsole_material", "材质", "鞋底材质：橡胶", ("橡胶",)),
        ("outsole_material", "材质", "鞋底材质：发泡", ("发泡",)),
        ("outsole_material", "材质", "鞋底材质：EVA", ("EVA",)),
        ("outsole_material", "材质", "鞋底材质：聚氨酯", ("聚氨酯",)),
        ("outsole_material", "材质", "鞋底材质：PU", ("PU",)),
        ("outsole_material", "材质", "鞋底材质：TPU", ("TPU",)),
        ("outsole_material", "材质", "鞋底材质：TPR", ("TPR",)),
        ("outsole_material", "材质", "鞋底材质：PVC", ("PVC",)),
    )
    keywords_by_field: dict[str, list[str]] = defaultdict(list)
    for field, _group, _name, keywords in keyword_rules:
        keywords_by_field[field].extend(keywords)

    for field, group, name, keywords in keyword_rules:
        value = _text(row.get(field))
        matched = value and any(
            keyword in value
            and not any(
                other != keyword and keyword in other and other in value
                for other in keywords_by_field[field]
            )
            for keyword in keywords
        )
        if matched:
            _add_tag(
                definitions,
                product_tags,
                brand=brand,
                product_id=product_id,
                field=f"{field}:{name}",
                group=group,
                name=name,
                value=name,
            )

    for field, label in (("fashion_elements", "流行元素"), ("selling_points", "卖点")):
        for token in _TOKEN_SPLIT_PATTERN.split(_text(row.get(field))):
            token = token.strip()
            if 1 < len(token) <= 30:
                _add_tag(
                    definitions,
                    product_tags,
                    brand=brand,
                    product_id=product_id,
                    field=field,
                    group="风格",
                    name=f"{label}：{token}",
                    value=token,
                )

    searchable = " ".join(_text(row.get(field)) for field in ("lining_material", "outsole_material", "selling_points", "internal_height_increase", "sole_style"))
    function_rules = (
        ("保暖", ("绒", "毛", "羊毛", "保暖")),
        ("轻便", ("发泡", "EVA", "轻便")),
        ("透气", ("织物", "网布", "透气")),
        ("增高", ("增高", "厚底", "内增高")),
    )
    for name, keywords in function_rules:
        if any(keyword in searchable for keyword in keywords):
            _add_tag(
                definitions,
                product_tags,
                brand=brand,
                product_id=product_id,
                field=f"function:{name}",
                group="功能",
                name=name,
                value=name,
            )


def _add_lifecycle_and_quality_tags(
    row: dict[str, object],
    brand: str,
    product_id: int,
    definitions: dict[str, dict[str, object]],
    product_tags: dict[tuple[str, int], dict[str, dict[str, object]]],
    *,
    business_date: date | None = None,
) -> None:
    launch_date = _text(row.get("launch_date"))
    parsed_date = None
    for parser in (date.fromisoformat, lambda value: datetime.strptime(value, "%Y/%m/%d").date()):
        try:
            parsed_date = parser(launch_date)
            break
        except (TypeError, ValueError):
            continue
    if parsed_date is not None:
        today = business_date or date.today()
        if parsed_date >= today - timedelta(days=180):
            _add_tag(
                definitions,
                product_tags,
                brand=brand,
                product_id=product_id,
                field="launch_date:new",
                group="运营",
                name="新品（近180天上市）",
                value="new_180_days",
            )
    quality_rules = (
        ("image_path", "缺图片"),
        ("launch_date", "缺上市日期"),
        ("upper_material", "缺鞋面材质"),
        ("category", "缺品类"),
    )
    for field, name in quality_rules:
        if not _text(row.get(field)):
            _add_tag(
                definitions,
                product_tags,
                brand=brand,
                product_id=product_id,
                field=f"quality:{field}",
                group="数据质量",
                name=name,
                value=field,
            )


def _generate_for_row(row, brand, definitions, product_tags, *, business_date: date | None = None) -> None:
    if row.get("deleted_at") is not None:
        return
    product_id = int(row["id"])
    _add_exact_field_tags(row, brand, product_id, definitions, product_tags)
    _add_keyword_tags(row, brand, product_id, definitions, product_tags)
    _add_lifecycle_and_quality_tags(row, brand, product_id, definitions, product_tags, business_date=business_date)


def _changed_product_ids(product_ids, product_tags, existing_tags) -> list[int]:
    return [
        product_id for product_id in product_ids
        if product_tags.get(product_id, {}) != existing_tags.get(product_id, {})
    ]


def sync_changed_product_tags(repository, business_date: date, *, batch_size: int = 500) -> dict[str, int]:
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    definitions_table = PRODUCT_TAG_DEFINITIONS_TABLE
    assignments_table = PRODUCT_TAG_ASSIGNMENTS_TABLE
    result = {"brands": 0, "products": 0, "updated_products": 0, "tag_definitions": 0, "assignments": 0}
    start = datetime.combine(business_date, time.min, _BUSINESS_TIMEZONE)
    end = start + timedelta(days=1)
    expired_new_tag_date = business_date - timedelta(days=181)
    with repository.engine.begin() as connection:
        ensure_product_tag_schema(connection)

    for brand in repository.product_archive_brands():
        table = repository._table_for_brand(brand)
        last_id = 0
        result["brands"] += 1
        while True:
            has_rule_assignment = exists(
                select(assignments_table.c.id).where(
                    assignments_table.c.brand == brand,
                    assignments_table.c.product_id == table.c.id,
                    assignments_table.c.source_type == "rule",
                )
            )
            statement = (
                select(table.c.id, table.c.deleted_at, *(table.c[field] for field in _SELECTED_FIELDS))
                .where(table.c.id > last_id)
                .where(or_(
                    (table.c.created_at >= start) & (table.c.created_at < end),
                    (table.c.updated_at >= start) & (table.c.updated_at < end),
                    (table.c.deleted_at >= start) & (table.c.deleted_at < end),
                    and_(table.c.deleted_at.is_(None), ~has_rule_assignment),
                    and_(table.c.deleted_at.is_(None), table.c.launch_date == expired_new_tag_date.isoformat()),
                    and_(table.c.deleted_at.is_(None), table.c.launch_date == expired_new_tag_date.strftime("%Y/%m/%d")),
                ))
                .order_by(table.c.id)
                .limit(batch_size)
            )
            with repository.engine.connect() as connection:
                rows = connection.execute(statement).mappings().all()
            if not rows:
                break
            last_id = int(rows[-1]["id"])
            definitions: dict[str, dict[str, object]] = {}
            product_tags: dict[tuple[str, int], dict[str, dict[str, object]]] = defaultdict(dict)
            for row in rows:
                _generate_for_row(row, brand, definitions, product_tags, business_date=business_date)

            with repository.engine.begin() as connection:
                if definitions:
                    inserted = connection.execute(
                        pg_insert(definitions_table)
                        .values(list(definitions.values()))
                        .on_conflict_do_nothing(index_elements=["tag_code"])
                        .returning(definitions_table.c.id)
                    ).scalars().all()
                    result["tag_definitions"] += len(inserted)
                    definition_ids = dict(connection.execute(
                        select(definitions_table.c.tag_code, definitions_table.c.id)
                        .where(definitions_table.c.tag_code.in_(definitions))
                    ).all())
                else:
                    definition_ids = {}
                product_ids = [int(row["id"]) for row in rows]
                existing_tags: dict[int, dict[str, dict[str, object]]] = defaultdict(dict)
                for assignment in connection.execute(
                    select(assignments_table.c.product_id, definitions_table.c.tag_code, assignments_table.c.evidence)
                    .join(definitions_table, definitions_table.c.id == assignments_table.c.tag_id)
                    .where(
                        assignments_table.c.brand == brand,
                        assignments_table.c.product_id.in_(product_ids),
                        assignments_table.c.source_type == "rule",
                    )
                ).mappings():
                    existing_tags[int(assignment["product_id"])][str(assignment["tag_code"])] = assignment["evidence"]
                desired_tags = {
                    product_id: product_tags.get((brand, product_id), {})
                    for product_id in product_ids
                }
                changed_ids = _changed_product_ids(product_ids, desired_tags, existing_tags)
                if changed_ids:
                    connection.execute(
                        delete(assignments_table).where(
                            assignments_table.c.brand == brand,
                            assignments_table.c.product_id.in_(changed_ids),
                            assignments_table.c.source_type == "rule",
                        )
                    )
                assignment_rows = [
                    {
                        "tag_id": definition_ids[code], "brand": brand,
                        "product_id": product_id, "target_type": "sku", "source_type": "rule",
                        "confidence": 100, "evidence": evidence, "status": "confirmed",
                        "is_locked": False,
                    }
                    for product_id in changed_ids
                    for tags in (desired_tags[product_id],)
                    for code, evidence in tags.items()
                ]
                if assignment_rows:
                    connection.execute(insert(assignments_table), assignment_rows)
            result["products"] += len(rows)
            result["updated_products"] += len(changed_ids)
            result["assignments"] += len(assignment_rows)
    return result


def rebuild_product_tags(repository) -> dict[str, int]:
    product_tags: dict[tuple[str, int], dict[str, dict[str, object]]] = defaultdict(dict)
    definitions: dict[str, dict[str, object]] = {}
    product_count = 0
    brand_count = 0
    with repository.engine.connect() as connection:
        for brand in repository.product_archive_brands():
            table = repository._table_for_brand(brand)
            statement = select(table.c.id, *(table.c[field] for field in _SELECTED_FIELDS)).where(table.c.deleted_at.is_(None))
            rows = connection.execute(statement).mappings()
            brand_count += 1
            for raw_row in rows:
                row = dict(raw_row)
                product_count += 1
                _generate_for_row(row, brand, definitions, product_tags)

    with repository.engine.begin() as connection:
        ensure_product_tag_schema(connection)
        existing_definitions = {
            str(row["tag_code"]): dict(row)
            for row in connection.execute(select(PRODUCT_TAG_DEFINITIONS_TABLE)).mappings()
        }
        definitions = _apply_manual_overrides(definitions, existing_definitions)
        connection.execute(delete(PRODUCT_TAG_ASSIGNMENTS_TABLE))
        connection.execute(delete(PRODUCT_STYLE_ENTITIES_TABLE))
        connection.execute(delete(PRODUCT_TAG_DEFINITIONS_TABLE))
        definition_rows = list(definitions.values())
        definition_id_by_code: dict[str, int] = {}
        if definition_rows:
            returned = connection.execute(
                insert(PRODUCT_TAG_DEFINITIONS_TABLE).returning(
                    PRODUCT_TAG_DEFINITIONS_TABLE.c.id,
                    PRODUCT_TAG_DEFINITIONS_TABLE.c.tag_code,
                ),
                definition_rows,
            ).mappings()
            definition_id_by_code = {str(row["tag_code"]): int(row["id"]) for row in returned}

        assignment_rows = []
        for (brand, product_id), tags in product_tags.items():
            for tag_code, evidence in tags.items():
                assignment_rows.append(
                    {
                        "tag_id": definition_id_by_code[tag_code],
                        "brand": brand,
                        "product_id": product_id,
                        "target_type": "sku",
                        "source_type": "rule",
                        "confidence": 100,
                        "evidence": evidence,
                        "status": "confirmed",
                        "is_locked": False,
                    }
                )
        for start in range(0, len(assignment_rows), 5000):
            connection.execute(insert(PRODUCT_TAG_ASSIGNMENTS_TABLE), assignment_rows[start:start + 5000])

    return {
        "brands": brand_count,
        "products": product_count,
        "tag_definitions": len(definitions),
        "assignments": sum(len(tags) for tags in product_tags.values()),
    }
