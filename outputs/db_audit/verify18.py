import sys
from pathlib import Path
sys.path.insert(0, r"E:\hede\outputs\db_audit")
from audit import database_url
import psycopg
from psycopg.rows import dict_row
q = """
SELECT
 count(*) FILTER (WHERE r.deleted_at IS NULL AND (r.date IS NULL OR r.total_count IS NULL)) AS live_null_date_or_total,
 count(*) FILTER (WHERE r.deleted_at IS NULL AND r.total_count IS NULL
                    AND r.document_type IN ('应付款减少','应付款增加','应收款减少','应收款增加')) AS live_null_total_settlement,
 count(*) FILTER (WHERE r.deleted_at IS NULL AND r.supplier IS NULL
                    AND r.document_type IN ('应付款减少','应付款增加','应收款减少','应收款增加')) AS live_no_supplier_settlement,
 count(*) FILTER (WHERE r.deleted_at IS NULL AND r.supplier IS NULL) AS live_no_supplier
FROM public.inventory_records r
"""
with psycopg.connect(database_url(), autocommit=True) as conn:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(q)
        for k, v in cur.fetchone().items():
            print(f"{k} = {v}")
