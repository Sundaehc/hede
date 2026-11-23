import json, os
from collections import Counter
from datetime import date
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET

from storage.daily_sales_repository import DailySalesRepository, _header, _payload_value
from storage.date_normalization import parse_date
from storage.vip_repository import _xlsx_sheet_rows

path = Path(os.environ['VIP_NOV20_SOURCE'])
with ZipFile(path) as z:
    sheets = [e.get('name') for e in ET.fromstring(z.read('xl/workbook.xml')).iter() if e.tag.endswith('}sheet')]
print('sheets:', sheets, flush=True)
it = _xlsx_sheet_rows(path)
_, header_values = next(it)
headers = {i: _header(v) for i, v in header_values.items() if _header(v)}
print('headers:', list(headers.values()), flush=True)
assert len(headers) == len(set(headers.values()))
assert {'日期', '商品ID', 'SIZE_ID', '销售量', '销售额'} <= set(headers.values())
date_column = next(i for i, h in headers.items() if h == '日期')
dates, totals, missing, keys = Counter(), Counter(), Counter(), Counter()
brands, barcodes, groups = set(), set(), Counter()
day = date(2026, 11, 20)
for number, values in it:
    if not values:
        continue
    sales_date = parse_date(values.get(date_column, ''))
    dates[str(sales_date)] += 1
    if sales_date != day:
        continue
    raw = {header: _payload_value(values.get(i, '')) for i,header in headers.items()}
    row = DailySalesRepository._map_vip(raw) | {'sales_date':sales_date}
    keys[DailySalesRepository._vip_key(row)] += 1
    for f in ('goods_id','size_id','barcode','sales_quantity','sales_amount'):
        if row[f] in (None,''):
            missing[f]+=1
    for f in ('sales_quantity','sales_amount','customer_count'):
        if row[f] is not None:
            totals[f] += row[f]
    if row['brand_sn']:
        brands.add(row['brand_sn'])
    if row['barcode']:
        barcodes.add(row['barcode'])
    if (row['sales_quantity'] or 0) > 0:
        groups['positive_sales_rows'] += 1
    if (row['sales_quantity'] or 0) < 0:
        groups['negative_sales_rows'] += 1
    for f in ('sales_quantity', 'sales_amount'):
        if row[f] is None and raw['销售量' if f == 'sales_quantity' else '销售额'] not in ('', None, '-', '—', '--'):
            groups['unparsed_' + f] += 1
print(json.dumps({'dates':dates,'totals':totals,'distinct_keys':len(keys),'duplicate_rows':sum(n-1 for n in keys.values()),'distinct_brands':len(brands),'distinct_barcodes':len(barcodes),'missing':missing,'groups':groups}, ensure_ascii=False, default=str), flush=True)
assert len(sheets) == 1 and set(dates) == {day.isoformat()} and len(keys) == dates[day.isoformat()]
assert not missing['goods_id'] and not missing['size_id'] and not groups['unparsed_sales_amount'] and not groups['unparsed_sales_quantity']