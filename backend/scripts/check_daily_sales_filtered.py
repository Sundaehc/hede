from __future__ import annotations

from sqlalchemy import create_engine, text

from config import load_settings


SKU = "QT653891S30"
DAY = "2026-05-25"
EXCLUDED = ("取消", "异常", "被拆分", "已付款待审核")


def main() -> None:
    engine = create_engine(load_settings().database_url)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                select coalesce(status, '') as status,
                       coalesce(shop_name, '') as shop_name,
                       sum(quantity)::integer as qty
                from jst_monthly_orders
                where style_code = :sku
                  and order_time_at >= cast(:day as date)
                  and order_time_at < cast(:day as date) + interval '1 day'
                group by coalesce(status, ''), coalesce(shop_name, '')
                order by qty desc
                """
            ),
            {"sku": SKU, "day": DAY},
        ).mappings().all()

    total = sum(row["qty"] for row in rows)
    filtered = sum(
        row["qty"]
        for row in rows
        if row["status"] not in EXCLUDED
    )
    filtered_non_vip = sum(
        row["qty"]
        for row in rows
        if row["status"] not in EXCLUDED and "唯品" not in row["shop_name"]
    )
    print(f"sku={SKU} day={DAY}")
    print(f"raw={total}")
    print(f"filtered_status={filtered}")
    print(f"filtered_status_non_vip={filtered_non_vip}")
    for row in rows:
        print(f"{row['status']}\t{row['shop_name']}\t{row['qty']}")


if __name__ == "__main__":
    main()
