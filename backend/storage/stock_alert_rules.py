"""Small, shared brand/season rule settings with optimistic concurrency."""
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, DateTime, Integer, MetaData, Numeric, Table, Text, insert, select, update
from sqlalchemy.exc import IntegrityError

RULES = Table("stock_alert_rules", MetaData(),
    Column("brand", Text, primary_key=True), Column("season", Text, primary_key=True), Column("kind", Text, primary_key=True),
    Column("age_days", Integer, nullable=False), Column("rate", Numeric(5, 2), nullable=False),
    Column("version", Integer, nullable=False), Column("updated_by", Integer), Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("age_days BETWEEN 1 AND 3650"), CheckConstraint("rate BETWEEN 0 AND 100"),
    CheckConstraint("kind IN ('zero', 'slow')"))


class RuleConflict(ValueError):
    pass


class StockAlertRuleRepository:
    def __init__(self, engine):
        self.engine = engine

    def create_tables(self):
        RULES.create(self.engine, checkfirst=True)

    def list_rules(self, brand):
        with self.engine.connect() as connection:
            return {(row["kind"], row["season"]): dict(row) for row in connection.execute(
                select(RULES).where(RULES.c.brand == brand)).mappings()}

    def save(self, *, brand, season, kind, age_days, rate, version, user_id):
        values = {"age_days": age_days, "rate": rate, "version": version + 1,
                  "updated_by": user_id, "updated_at": datetime.now(timezone.utc)}
        scope = (RULES.c.brand == brand, RULES.c.season == season, RULES.c.kind == kind)
        try:
            with self.engine.begin() as connection:
                if version == 0:
                    connection.execute(insert(RULES).values(brand=brand, season=season, kind=kind, **values))
                elif connection.execute(update(RULES).where(*scope, RULES.c.version == version).values(**values)).rowcount != 1:
                    raise RuleConflict("规则已被其他页面修改，请关闭设置并刷新后重试")
        except IntegrityError:
            raise RuleConflict("该范围已有新规则，请关闭设置并刷新后重试") from None
