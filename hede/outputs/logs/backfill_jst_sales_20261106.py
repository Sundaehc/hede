from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

from sqlalchemy import create_engine, select, text
from config import load_settings
from domain.daily_sales_schema import jst_daily_sales_table_for_year
from domain.task_status_schema import SCHEDULED_TASK_STATUS_TABLE
from storage.daily_sales_repository import DailySalesRepository, _header
from storage.date_normalization import parse_date
from storage.factory_channel_sales_summary_repository import FactoryChannelSalesSummaryRepository
from storage.task_status_repository import ScheduledTaskStatusRepository
from storage.vip_repository import _xlsx_sheet_rows

TARGET = date(2026, 11, 6)
SOURCE = ROOT.parent / 'Desktop' / '销售主题分析_多维分析_20261108093027_207383867_1.xlsx'
AUDIT = ROOT / 'outputs/logs/jst-sales-20261106-desktop'
TASK = 'import_jst_daily_sales'
KEYS = DailySalesRepository._jst_key_columns
METRICS = ('sales_order_count', 'shipped_order_count', 'return_order_count',
           'sales_quantity', 'shipped_quantity', 'return_quantity', 'net_sales_quantity',
           'sales_amount', 'net_sales_amount', 'cost_amount', 'gross_profit')
TABLE = jst_daily_sales_table_for_year(2026)


def dump(value):
    return json.dumps(value, ensure_ascii=True, default=str, sort_keys=True)


def save(name, value):
    AUDIT.mkdir(parents=True, exist_ok=True)
    (AUDIT / name).write_text(dump(value), encoding='utf-8')


def inspect_source():
    assert SOURCE.is_file(), str(SOURCE)
    iterator = _xlsx_sheet_rows(SOURCE)
    _, first = next(iterator)
    headers = {index: _header(value) for index, value in first.items() if _header(value)}
    assert len(headers) == len(set(headers.values())), 'Duplicate column headers'
    date_column = next(index for index, name in headers.items() if name == '日期')
    expected = {}
    dates = Counter()
    invalid_dates = []
    duplicates = []
    for number, values in iterator:
        if not values:
            continue
        day = parse_date(values.get(date_column, ''))
        dates[str(day)] += 1
        if day is None:
            invalid_dates.append({'row': number, 'value': values.get(date_column)})
        if day != TARGET:
            continue
        raw = {header: values.get(index, '') for index, header in headers.items()}
        row = DailySalesRepository._map_jst(raw)
        row['sales_date'] = day
        row['source_row_number'] = number
        assert row['channel'] and (row['product_code'] or row['style_code']), f'Missing product/channel at row {number}'
        key = tuple(row[column] for column in KEYS)
        if key in expected:
            duplicates.append({'row': number, 'previous_row': expected[key]['source_row_number']})
        expected[key] = row
    assert expected, 'No rows for requested date'
    assert not duplicates, f'Duplicate business keys: {duplicates[:5]}'
    totals = {column: sum((row[column] or 0 for row in expected.values()), Decimal(0)) for column in METRICS}
    report = {
        'source': str(SOURCE), 'sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        'headers': list(headers.values()), 'date_counts': dict(dates),
        'invalid_date_rows': invalid_dates[:10], 'target_date': TARGET,
        'target_rows': len(expected), 'duplicate_keys': len(duplicates),
        'totals': totals,
        'null_metric_counts': {column: sum(row[column] is None for row in expected.values()) for column in METRICS},
    }
    return expected, report


def snapshot(engine):
    with engine.begin() as connection:
        connection.execute(text('SET TRANSACTION READ ONLY'))
        connection.execute(text("SET LOCAL statement_timeout = '45s'"))
        connection.execute(text('SET LOCAL max_parallel_workers_per_gather = 0'))
        sales = [dict(row) for row in connection.execute(text('''
            SELECT sales_date, count(*) AS rows,
                   sum(sales_quantity) AS sales_quantity,
                   sum(return_quantity) AS return_quantity,
                   sum(net_sales_quantity) AS net_sales_quantity,
                   sum(sales_amount) AS sales_amount,
                   sum(net_sales_amount) AS net_sales_amount,
                   md5(string_agg(md5(row_to_json(t)::text), '' ORDER BY id)) AS fingerprint
            FROM jst_daily_sales_2026 t
            WHERE sales_date BETWEEN :start AND :end
            GROUP BY sales_date ORDER BY sales_date
        '''), {'start': date(2026, 11, 5), 'end': date(2026, 11, 7)}).mappings()]
        summaries = [dict(row) for row in connection.execute(text('''
            SELECT sales_date, count(*) AS rows,
                   md5(string_agg(md5(row_to_json(t)::text), '' ORDER BY id)) AS fingerprint
            FROM factory_channel_sales_daily_summaries t
            WHERE sales_date BETWEEN :start AND :end
            GROUP BY sales_date ORDER BY sales_date
        '''), {'start': date(2026, 11, 5), 'end': date(2026, 11, 7)}).mappings()]
        statuses = [dict(row) for row in connection.execute(
            select(SCHEDULED_TASK_STATUS_TABLE).where(
                SCHEDULED_TASK_STATUS_TABLE.c.task_name == TASK,
                SCHEDULED_TASK_STATUS_TABLE.c.business_date.between(date(2026, 11, 5), date(2026, 11, 7)),
            )).mappings()]
        rows = [dict(row) for row in connection.execute(select(TABLE).where(TABLE.c.sales_date == TARGET)).mappings()]
    return {'sales': sales, 'summaries': summaries, 'statuses': statuses}, rows


def compare(expected, actual):
    indexed = {tuple(row[column] for column in KEYS): row for row in actual}
    differences = []
    for key, wanted in expected.items():
        got = indexed.get(key)
        if got is None:
            differences.append({'source_row': wanted['source_row_number'], 'reason': 'missing'})
            continue
        for column, value in wanted.items():
            if isinstance(value, Decimal):
                places = 4 if column == 'cost_price' else 2
                value = value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
            if got.get(column) != value:
                differences.append({'source_row': wanted['source_row_number'], 'column': column, 'expected': value, 'actual': got.get(column)})
        if got['source_workbook'] != SOURCE.name:
            differences.append({'source_row': wanted['source_row_number'], 'reason': 'wrong provenance'})
    return {'expected_rows': len(expected), 'database_rows': len(actual),
            'extra_database_keys': len(set(indexed) - set(expected)),
            'differences': len(differences), 'examples': differences[:10]}


def neighbors(snapshot_value):
    return {name: [row for row in snapshot_value[name] if row['sales_date'] != TARGET] for name in ('sales', 'summaries')}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    expected, source = inspect_source()
    save('source.json', source)
    print('SOURCE ' + dump(source), flush=True)
    database_url = load_settings(require_database=True).database_url
    engine = create_engine(database_url, pool_size=1, max_overflow=0, connect_args={'connect_timeout': 8})
    try:
        before, old_rows = snapshot(engine)
        if not args.apply:
            save('before.json', before)
            save('before-target-rows.json', old_rows)
            print('BEFORE ' + dump(before), flush=True)
            print('COMPARISON ' + dump(compare(expected, old_rows)), flush=True)
            return
        assert (AUDIT / 'before.json').exists(), 'Inspect before applying'
        inspected = json.loads((AUDIT / 'before.json').read_text(encoding='utf-8'))
        assert dump(before) == dump(inspected), 'Database changed since inspection; inspect again'
        assert not old_rows, 'Target date now contains data; review before overwriting'
        statuses = ScheduledTaskStatusRepository(database_url)
        statuses.mark_running(TASK, TARGET, source_path=SOURCE)
        try:
            repository = DailySalesRepository(database_url)
            try:
                imported = repository.import_jst_daily_sales_range(SOURCE, date_start=TARGET, date_end=TARGET, batch_size=1000)
            finally:
                repository.engine.dispose()
            save('import.json', imported)
            print('IMPORTED ' + dump(imported), flush=True)
            assert imported['sales_dates'] == [TARGET.isoformat()]
            assert imported['matched'] == imported['upserted'] == len(expected)
            summary_repository = FactoryChannelSalesSummaryRepository(database_url)
            try:
                summary = summary_repository.refresh(sales_year=2026, date_start=TARGET, date_end=TARGET)
            finally:
                summary_repository.engine.dispose()
            save('summary.json', summary)
            print('SUMMARY ' + dump(summary), flush=True)
            after, new_rows = snapshot(engine)
            verification = compare(expected, new_rows)
            assert verification['differences'] == 0, dump(verification)
            assert verification['extra_database_keys'] == 0, dump(verification)
            assert neighbors(after) == neighbors(before), 'Adjacent date data changed'
            result = {**imported, 'manual_backfill': True, 'factory_channel_summary': summary, 'verification': verification}
            statuses.mark_finished(TASK, TARGET, status='success', message='Manual desktop workbook backfill completed and verified for 2026-11-06', result=result, source_path=SOURCE)
            final_snapshot, _ = snapshot(engine)
            target_status = next(row for row in final_snapshot['statuses'] if row['business_date'] == TARGET)
            assert target_status['status'] == 'success'
            save('after.json', final_snapshot)
            save('result.json', result)
            print('VERIFIED ' + dump(result), flush=True)
        except Exception as error:
            statuses.mark_finished(TASK, TARGET, status='failed', message=f'Manual backfill verification failed: {type(error).__name__}: {error}', source_path=SOURCE)
            raise
        finally:
            statuses.engine.dispose()
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
