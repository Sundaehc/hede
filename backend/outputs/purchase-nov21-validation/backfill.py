from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date
import json
import os
from pathlib import Path

from sqlalchemy import create_engine, text
from config import load_settings
from fileio.purchase_inbound_reader import iter_purchase_inbound_rows
from scripts.import_purchase_inbound_history import REQUIRED_HEADERS, map_record, source_checksum, _import_file
from storage.purchase_inbound_history import refresh_inbound_age_reference

DAY = date(2026, 11, 21)
START = date(2026, 11, 20)
END = date(2026, 11, 23)


def scan(path):
    headers = {}
    by_date = Counter()
    by_group = defaultdict(Counter)
    docids = set()
    line_keys = Counter()
    for sheet, number, values in iter_purchase_inbound_rows(path):
        if sheet not in headers:
            header = {index: value.replace('\n', '').strip() for index, value in values.items() if value}
            assert REQUIRED_HEADERS <= set(header.values()), (sheet, REQUIRED_HEADERS - set(header.values()), list(header.values()))
            assert len(header) == len(set(header.values())), (sheet, 'duplicate headers')
            headers[sheet] = header
            continue
        raw = {key: values.get(i, '') for i, key in headers[sheet].items()}
        if not any(raw.values()):
            continue
        try:
            row = map_record(raw)
        except Exception as error:
            raise ValueError(f'{sheet}:{number} {error}') from error
        by_date[row['inbound_date']] += 1
        if row['inbound_date'] != DAY:
            continue
        docids.add(row['inbound_id'])
        line_keys[(row['inbound_id'], row['goods_code'], row['warehouse'], row['color_spec'])] += 1
        group = (row['status'], row['inbound_type'], row['receipt_class'])
        counts = by_group[group]
        counts.update(rows=1, quantity=row['quantity'], amount=row['amount'] or 0)
    print('workbook:', json.dumps({'sheets':list(headers), 'rows_by_date':{str(day):n for day,n in by_date.items()}, 'documents':len(docids), 'same_document_sku_line_count':sum(n-1 for n in line_keys.values()), 'groups':[[*k, dict(v)] for k,v in sorted(by_group.items(),key=lambda entry:str(entry[0]))]}, ensure_ascii=False, default=str), flush=True)
    return by_date, by_group, docids


def nearby(c):
    return {r[0]:tuple(r[1:]) for r in c.execute(text('''
        SELECT inbound_date, count(*), count(DISTINCT inbound_id), sum(quantity), sum(amount)
        FROM public.jst_purchase_inbound_history
        WHERE inbound_date >= :start AND inbound_date < :end
        GROUP BY inbound_date ORDER BY inbound_date
    '''), {'start':START,'end':END}).all()}


def target_groups(c, source_id):
    return {(s,t,k):(n,q,a) for s,t,k,n,q,a in c.execute(text('''
        SELECT status,inbound_type,receipt_class,count(*),sum(quantity),coalesce(sum(amount),0)
        FROM public.jst_purchase_inbound_history
        WHERE inbound_date=:day AND source_id=:source_id GROUP BY 1,2,3
    '''), {'day':DAY,'source_id':source_id}).all()}


def source_status(c, checksum):
    return c.execute(text('''
        SELECT id,status,imported_rows,first_inbound_date,last_inbound_date
        FROM public.jst_purchase_inbound_history_sources WHERE source_checksum=:checksum
    '''), {'checksum':checksum}).first()


def print_db(c, checksum, docs):
    days = nearby(c)
    src = source_status(c,checksum)
    cnt = c.execute(text('''
        SELECT count(*) FROM public.jst_purchase_inbound_history
        WHERE inbound_date=:day AND inbound_id=ANY(:documents)
    '''), {'day':DAY,'documents':sorted(docs)}).scalar_one()
    print('database:', json.dumps({'nearby':{str(day):vals for day,vals in days.items()},'matching_document_rows':cnt,'identical_source':tuple(src) if src else None}, ensure_ascii=False, default=str), flush=True)
    return days, cnt, src


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    path = Path(os.environ['PURCHASE_NOV21_SOURCE'])
    checksum = source_checksum(path)
    dates, groups, docs = scan(path)
    assert source_checksum(path) == checksum, 'source changed during preflight'
    settings = load_settings(require_database=True)
    engine = create_engine(settings.database_url, connect_args={'connect_timeout':5})
    try:
        if not args.apply:
            with engine.connect() as c:
                print_db(c,checksum,docs)
            return
        assert set(dates) == {DAY} and dates[DAY] > 0, 'Excel must contain only requested date'
        with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as lock:
            assert lock.execute(text('SELECT pg_try_advisory_lock(20261027, 79)')).scalar_one(), 'purchase inbound import is currently in progress'
            try:
                with engine.connect() as c:
                    before, overlaps, existing = print_db(c,checksum,docs)
                if not (existing and existing.status == 'completed'):
                    assert overlaps == 0, 'existing target-document data requires review before replacement'
                    assert source_checksum(path) == checksum, 'source changed after preflight'
                    result = _import_file(engine,path,business_date=DAY)
                    print('import:', json.dumps(result,ensure_ascii=False,default=str), flush=True)
                    assert result['status']=='completed' and result['rows']==dates[DAY] and result['replaced_rows']==0, result
                with engine.connect() as c:
                    after, overlaps, source = print_db(c,checksum,docs)
                    assert all(before.get(d)==after.get(d) for d in set(before)|set(after) if d!=DAY), 'nearby dates changed'
                    assert source and source.status=='completed' and source.imported_rows==dates[DAY] and source.first_inbound_date==source.last_inbound_date==DAY, source
                    assert overlaps==dates[DAY], 'imported document row counts do not match'
                    actual = target_groups(c,source.id)
                    expected = {g:(v['rows'], v['quantity'], v['amount']) for g,v in groups.items()}
                    assert actual==expected, (actual,expected)
                    eligible = c.execute(text('''
                        SELECT count(*),coalesce(sum(quantity),0) FROM public.v_jst_purchase_inbound_age_candidates
                        WHERE inbound_date=:day AND source_id=:source_id
                    '''), {'day':DAY,'source_id':source.id}).one()
                    print('verified:', json.dumps({'rows':dates[DAY],'documents':len(docs),'quantity':sum(v['quantity'] for v in groups.values()),'amount':sum(v['amount'] for v in groups.values()),'age_candidate_rows':eligible[0],'age_candidate_quantity':eligible[1]}, ensure_ascii=False,default=str), flush=True)
                print('refreshing age reference', flush=True)
                refresh_inbound_age_reference(engine)
                with engine.connect() as c:
                    actual = c.execute(text('''
                        WITH imported_keys AS (
                            SELECT DISTINCT goods_code,style_color_code,original_sku,warehouse
                            FROM public.v_jst_purchase_inbound_age_candidates
                            WHERE inbound_date=:day AND source_id=:source_id
                        )
                        SELECT count(*), count(*) FILTER (WHERE ref.last_inbound_date >= :day)
                        FROM imported_keys AS k LEFT JOIN public.mv_jst_purchase_inbound_age_reference AS ref
                            USING (goods_code,style_color_code,original_sku,warehouse)
                    '''), {'day':DAY,'source_id':source.id}).one()
                    assert actual[0]==actual[1], actual
                    print('age reference verified:', actual, flush=True)
            finally:
                lock.execute(text('SELECT pg_advisory_unlock(20261027, 79)'))
    finally:
        engine.dispose()


if __name__=='__main__':
    main()