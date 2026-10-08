import sys
sys.path.insert(0, r"E:\hede\outputs\db_audit")
from audit import database_url
import psycopg
from psycopg.rows import dict_row
with psycopg.connect(database_url(), autocommit=True) as conn:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT COALESCE(document_type,'(空)') AS dtype, count(*) AS n,
                   min(date) AS first_date, max(date) AS last_date
            FROM public.inventory_records
            WHERE deleted_at IS NULL AND supplier IS NULL
            GROUP BY 1 ORDER BY 2 DESC
        """)
        print("=== 183 张缺供应商的单据按类型 ===")
        for r in cur.fetchall():
            print(f"  {r['dtype']:<16} {r['n']:>5}  {r['first_date']} ~ {r['last_date']}")
        cur.execute("""
            SELECT count(*) AS n FROM public.inventory_records
            WHERE deleted_at IS NULL AND supplier IS NULL
              AND document_type IN ('进货单','进货订单','进货退货单')
        """)
        print("其中进货类 =", cur.fetchone()["n"])
