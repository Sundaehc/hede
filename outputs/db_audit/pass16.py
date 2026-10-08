"""Pass 16: definitive empty-table detection (pass12 only checked reltuples < 1,
which misses tables whose stale statistics overstate their size)."""
from __future__ import annotations

import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from audit import database_url  # noqa: E402

OUT = HERE / "completeness5.txt"
OUT.write_text("", encoding="utf-8")
LIMIT = 200 * 1024 * 1024  # exact count for anything under 200 MB

with psycopg.connect(database_url(), autocommit=True) as conn:
    with conn.cursor() as cur:
        cur.execute("SET statement_timeout = '600s'")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT c.relname AS t, c.reltuples::bigint AS est,
                   pg_relation_size(c.oid) AS heap,
                   pg_total_relation_size(c.oid) AS total
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind = 'r' AND n.nspname = 'public'
            ORDER BY c.relname
        """)
        tables = cur.fetchall()

    lines = []
    exact_empty, exact_rows, estimated = [], [], []
    for t in tables:
        name = t["t"]
        if t["heap"] < LIMIT:
            try:
                with conn.cursor() as cur:
                    cur.execute(f'SELECT count(*) FROM public."{name}"')
                    n = cur.fetchone()[0]
                exact_rows.append((name, n, t["heap"], t["est"]))
                if n == 0:
                    exact_empty.append((name, t["heap"]))
            except Exception as exc:  # noqa: BLE001
                conn.rollback()
                lines.append(f"  !! {name}: {type(exc).__name__}: {exc}")
        else:
            estimated.append((name, t["est"], t["heap"]))

    lines.append("=" * 78)
    lines.append(f"A. 精确为空的表 ({len(exact_empty)} 个)")
    lines.append("=" * 78)
    for name, heap in exact_empty:
        lines.append(f"  {name:<48} {heap/1048576:>10.1f} MB")
    lines.append("")
    lines.append("=" * 78)
    lines.append(f"B. 精确计数但非空、且统计值与实际不符的表")
    lines.append("=" * 78)
    bad = [(n, c, h, e) for n, c, h, e in exact_rows if abs(c - e) > max(100, 0.05 * max(c, 1))]
    if not bad:
        lines.append("  无")
    for n, c, h, e in sorted(bad, key=lambda x: -abs(x[1] - x[3])):
        lines.append(f"  {n:<46} 实际={c:>10,}  统计={e:>10,}")
    lines.append("")
    lines.append("=" * 78)
    lines.append(f"C. 精确计数的表 ({len(exact_rows)} 个, 行数降序, 前 40)")
    lines.append("=" * 78)
    lines.append(f"  {'table':<46} {'rows':>12} {'heap':>10}")
    for n, c, h, _e in sorted(exact_rows, key=lambda x: -x[1])[:40]:
        lines.append(f"  {n:<46} {c:>12,} {h/1048576:>9.2f}MB")
    lines.append("")
    lines.append("=" * 78)
    lines.append(f"D. 大于 200MB, 用统计值估算 ({len(estimated)} 个)")
    lines.append("=" * 78)
    for n, e, h in sorted(estimated, key=lambda x: -x[2]):
        lines.append(f"  {n:<46} est={e:>12,} {h/1048576:>10.1f}MB")

    OUT.write_text("\n".join(lines), encoding="utf-8")
print("[done]")