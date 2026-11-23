import os, sys, traceback
from collections import Counter
from datetime import date
from pathlib import Path
from openpyxl import load_workbook
from storage.daily_sales_repository import DailySalesRepository, _header, _payload_value
from storage.date_normalization import parse_date
from storage.vip_repository import _xlsx_sheet_rows
from config import load_settings
from sqlalchemy import create_engine, text

def main():
    p = Path(os.environ['JST_NOV20_SOURCE'])
    book = load_workbook(p, read_only=True, data_only=True)
    print('sheets:', [(w.title, w.max_row, w.max_column) for w in book.worksheets], flush=True)
    book.close()
    it = _xlsx_sheet_rows(p)
    _, header_values = next(it)
    headers = {i:_header(v) for i,v in header_values.items() if _header(v)}
    print('headers:', list(headers.values()), flush=True)
    assert len(headers) == len(set(headers.values()))
    dcol = next(i for i, v in headers.items() if v == '日期')
    dates, totals, missing, keys, channels, issues = Counter(), Counter(), Counter(), Counter(), set(), Counter()
    metrics = ('sales_quantity','return_quantity','net_sales_quantity','sales_amount','net_sales_amount')
    for line, values in it:
        if not values: continue
        day = parse_date(values.get(dcol,''))
        dates[str(day)] += 1
        if day != date(2026,11,20): continue
        raw = {header:_payload_value(values.get(i,'')) for i,header in headers.items()}
        row = DailySalesRepository._map_jst(raw)
        row['sales_date'] = day
        key = DailySalesRepository._jst_key(row)
        keys[key] += 1
        channels.add(row['channel'])
        for field in (*DailySalesRepository._jst_key_columns, *metrics):
            if row[field] is None or row[field] == '': missing[field] += 1
        for metric in metrics:
            if row[metric] is not None: totals[metric] += row[metric]
        if all(row[m] is not None for m in metrics[:3]) and row['sales_quantity']-row['return_quantity'] != row['net_sales_quantity']:
            issues['quantity_not_reconciled'] += 1
    print('dates:', dates)
    print('distinct_keys:', len(keys), 'duplicate_rows:', sum(n-1 for n in keys.values()), 'distinct_channels:', len(channels))
    print('missing_fields:', missing, 'totals:', totals, 'issues:', issues, flush=True)
    assert dates['2026-11-20'] > 0 and len(keys) == dates['2026-11-20']
    settings = load_settings(require_database=True)
    engine = create_engine(settings.database_url, connect_args={'connect_timeout':5})
    try:
        with engine.connect() as c:
            print('database check:', c.execute(text("SELECT sales_date, count(*) AS rows, sum(net_sales_quantity) AS net FROM public.jst_daily_sales WHERE sales_date BETWEEN '2026-11-19' AND '2026-11-21' GROUP BY sales_date ORDER BY sales_date")).all())
    except Exception as e:
        print('database check failed:', type(e).__name__, str(e).splitlines()[0], flush=True)
        return 2
    return 0

try:
    raise SystemExit(main())
except Exception:
    traceback.print_exc()
    raise SystemExit(1)