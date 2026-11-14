"""Shared supplier replenishment settings, isolated by archive brand."""
from datetime import datetime, timezone

from sqlalchemy import JSON, CheckConstraint, Column, DateTime, Integer, MetaData, Table, Text, insert, select, update
from sqlalchemy.exc import IntegrityError

from storage.stock_alert_rules import RuleConflict


REPLENISHMENT_RULES = Table(
    "stock_replenishment_rules", MetaData(),
    Column("brand", Text, primary_key=True), Column("supplier", Text, primary_key=True),
    Column("lead_days", Integer, nullable=False), Column("min_order_qty", Integer, nullable=False),
    Column("cover_days", Integer, nullable=False), Column("size_ratios", JSON, nullable=False),
    Column("version", Integer, nullable=False), Column("updated_by", Integer),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("lead_days BETWEEN 0 AND 365"),
    CheckConstraint("min_order_qty BETWEEN 1 AND 1000000"),
    CheckConstraint("cover_days BETWEEN 1 AND 365"),
)


class StockReplenishmentRuleRepository:
    def __init__(self, engine):
        self.engine = engine

    def create_tables(self):
        REPLENISHMENT_RULES.create(self.engine, checkfirst=True)

    def list_rules(self, brand):
        with self.engine.connect() as connection:
            return {row["supplier"]: dict(row) for row in connection.execute(
                select(REPLENISHMENT_RULES).where(REPLENISHMENT_RULES.c.brand == brand)).mappings()}

    def save(self, *, brand, supplier, lead_days, min_order_qty, cover_days, size_ratios, version, user_id):
        values = {"lead_days": lead_days, "min_order_qty": min_order_qty, "cover_days": cover_days,
                  "size_ratios": size_ratios, "version": version + 1, "updated_by": user_id,
                  "updated_at": datetime.now(timezone.utc)}
        try:
            with self.engine.begin() as connection:
                if version == 0:
                    connection.execute(insert(REPLENISHMENT_RULES).values(brand=brand, supplier=supplier, **values))
                elif connection.execute(update(REPLENISHMENT_RULES).where(
                    REPLENISHMENT_RULES.c.brand == brand, REPLENISHMENT_RULES.c.supplier == supplier,
                    REPLENISHMENT_RULES.c.version == version).values(**values)).rowcount != 1:
                    raise RuleConflict("供应商规则已被其他页面修改，请关闭设置并刷新后重试")
        except IntegrityError:
            raise RuleConflict("该供应商已有新规则，请关闭设置并刷新后重试") from None
