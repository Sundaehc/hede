from datetime import date
from decimal import Decimal
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
from sqlalchemy import create_engine, text
from config import load_settings
from storage.vip_repository import _xlsx_sheet_rows

settings = load_settings(require_database=True)
business_date = date(2026, 11, 18)
source = settings.jst_stock_root / '11.18' / '商品库存.xlsx'
before = source.stat()
rows = _xlsx_sheet_rows(source)
_, headers = next(rows)
columns = {label: index for index, label in headers.items()}
metrics = ('可用数', '虚拟仓可用数', '公有可用数')
totals = dict.fromkeys(metrics, 0)
expected = {}
for _, row in rows:
    code = row.get(columns['商品编码'], '')
    available = row.get(columns['可用数'], '')
    if not code or available == '':
        continue
    expected[code] = int(Decimal(available))
    for metric in metrics:
        totals[metric] += int(Decimal(row.get(columns[metric], '') or '0'))

engine = create_engine(settings.database_url)
try:
    with engine.connect() as connection:
        connection.execute(text('SET TRANSACTION READ ONLY'))
        actual = dict(connection.execute(text(
            'SELECT product_code, available_qty FROM jst_daily_stock '
            'WHERE stock_date_value = :business_date'
        ), {'business_date': business_date}).all())
finally:
    engine.dispose()
after = source.stat()
report = {
    'business_date': business_date.isoformat(),
    'source_rows': len(expected),
    'source_quantity_totals': totals,
    'database_rows': len(actual),
    'database_quantity_sum': sum(actual.values()),
    'missing_codes': len(expected.keys() - actual.keys()),
    'extra_codes': len(actual.keys() - expected.keys()),
    'different_quantities': sum(actual[code] != expected[code] for code in actual.keys() & expected.keys()),
    'all_rows_match': actual == expected,
    'source_unchanged': (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns),
}
output = Path(__file__).with_name(sys.argv[1])
output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False))
raise SystemExit(0 if report['all_rows_match'] and report['source_unchanged'] else 1)
