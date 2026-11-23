"""Additional fields from the daily VIP product-detail workbook."""

from sqlalchemy import Integer, Numeric, text
from sqlalchemy.engine import Connection


VIP_DAILY_DETAIL_FIELDS = (
    ("return_quantity", "退货件数", Integer()),
    ("reject_quantity", "拒收件数", Integer()),
    ("reject_return_quantity", "拒退件数", Integer()),
    ("exchange_quantity", "换货件数", Integer()),
    ("return_amount", "退货金额", Numeric(18, 2)),
    ("reject_amount", "拒收金额", Numeric(18, 2)),
    ("reject_return_amount", "拒退金额", Numeric(18, 2)),
    ("exchange_amount", "换货金额", Numeric(18, 2)),
    ("return_rate", "退货率(退货件数/销售量)", Numeric(18, 8)),
    ("reject_rate", "拒收率(拒收件数/销售量)", Numeric(18, 8)),
    ("reject_return_rate", "拒退率", Numeric(18, 8)),
    ("exchange_rate", "换货率(换货件数/销售量)", Numeric(18, 8)),
    ("available_stock", "可售库存", Integer()),
    ("lowest_market_price", "最低市场价", Numeric(18, 2)),
    ("lowest_take_home_price", "最低到手价", Numeric(18, 2)),
    ("lowest_vip_price", "最低唯品价", Numeric(18, 2)),
)


def migrate_vip_daily_detail(connection: Connection, *, drop: bool = False) -> None:
    """Apply the detail-only migration; attached year partitions inherit the change."""
    connection.exec_driver_sql("SET LOCAL lock_timeout = '5s'")
    tables = connection.execute(text("""
        SELECT c.relname
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND c.relkind IN ('r', 'p') AND NOT c.relispartition
          AND c.relname ~ '^vip_daily_sales(_[0-9]{4})?$'
        ORDER BY c.relname
    """)).scalars().all()
    for table in tables:
        if drop:
            clauses = [f"DROP COLUMN IF EXISTS {name}" for name, _, _ in VIP_DAILY_DETAIL_FIELDS]
        else:
            clauses = [
                f"ADD COLUMN IF NOT EXISTS {name} {kind.compile(connection.dialect)}"
                for name, _, kind in VIP_DAILY_DETAIL_FIELDS
            ]
        connection.exec_driver_sql(f"ALTER TABLE public.{table} {', '.join(clauses)}")
