"""Derive optimization findings from raw.json produced by audit.py."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = json.loads((HERE / "raw.json").read_text(encoding="utf-8"))
OUT: list[str] = []


def p(line: str = "") -> None:
    OUT.append(line)


def mb(n) -> str:
    try:
        return f"{float(n) / 1048576:,.1f}MB"
    except Exception:
        return str(n)


tables = {f"{t['schema']}.{t['table_name']}": t for t in RAW["tables"]}
indexes = RAW["indexes"]
index_keys = RAW["index_keys"]
index_columns = RAW["index_columns"]

p("# DB AUDIT DERIVED FINDINGS")
p(f"server={RAW['server_version']} db={RAW['database']} size={RAW['db_size_pretty']}")
p(f"tables={len(tables)} indexes={len(indexes)}")
p()
p("## EXTENSIONS")
p(json.dumps(RAW["extensions"], ensure_ascii=False))
p(json.dumps(RAW.get("available_extensions"), ensure_ascii=False))
p()
p("## SETTINGS")
for s in RAW["settings"]:
    p(f"  {s['name']:<40} {str(s['setting']):<16} unit={str(s['unit']):<8} boot={str(s['boot_val']):<10} src={s['source']}")
p()
p("## DB STATS")
p(json.dumps(RAW["db_stats"], ensure_ascii=False, indent=1))
p()
p("## WAL")
p(json.dumps(RAW.get("wal_stats"), ensure_ascii=False))
p()
p("## IO")
p(json.dumps(RAW.get("io_stats"), ensure_ascii=False, indent=1))
p()

# ---------- index column signatures ----------
cols_by_index: dict[str, list[str]] = defaultdict(list)
for r in index_columns:
    key = r["index_name"]
    cols_by_index[key].append((r["pos"], r["column_name"] or r["expr"] or "?"))
sig: dict[str, list[str]] = {}
for r in index_columns:
    sig.setdefault(r["index_name"], [])
for k, v in cols_by_index.items():
    sig[k] = [c for _, c in sorted(v)]

by_table = defaultdict(list)
for r in index_keys:
    if not r["indisvalid"]:
        continue
    by_table[r["table_name"]].append(r)

p("## DUPLICATE INDEXES (identical key columns)")
dup_bytes = 0
for tbl, idxs in sorted(by_table.items()):
    groups = defaultdict(list)
    for r in idxs:
        key = tuple(sig.get(r["index_name"], []))
        groups[key].append(r)
    for key, group in groups.items():
        if len(group) > 1:
            p(f"  {tbl}: columns={key}")
            for g in group:
                p(f"      {g['index_name']}  {mb(g['index_bytes'])} unique={g['indisunique']}")
                if not g["indisprimary"]:
                    dup_bytes += int(g["index_bytes"])
p(f"  -> reclaimable from duplicates (excluding PKs): {mb(dup_bytes)}")
p()

p("## REDUNDANT PREFIX INDEXES (left-prefix of a wider index)")
prefix_bytes = 0
for tbl, idxs in sorted(by_table.items()):
    for a in idxs:
        ca = sig.get(a["index_name"], [])
        if not ca:
            continue
        for b in idxs:
            if a["index_name"] == b["index_name"]:
                continue
            cb = sig.get(b["index_name"], [])
            if len(cb) > len(ca) and cb[: len(ca)] == ca:
                # keep the more capable one: wider unique, or primary
                if a["indisprimary"]:
                    break
                p(f"  {tbl}: {a['index_name']} {mb(a['index_bytes'])} is prefix of "
                  f"{b['index_name']} {mb(b['index_bytes'])} (cols={ca})")
                prefix_bytes += int(a["index_bytes"])
                break
p(f"  -> reclaimable from prefix redundancy: {mb(prefix_bytes)}")
p()

p("## UNUSED NON-UNIQUE INDEXES (idx_scan = 0)")
unused = RAW["user_indexes_unused"]
tot = 0
for u in unused:
    pass
# recompute bytes from index_keys
size_by_name = {r["index_name"]: int(r["index_bytes"]) for r in index_keys}
for u in sorted(unused, key=lambda x: -size_by_name.get(u["index_name"], 0)):
    tot += size_by_name.get(u["index_name"], 0)
    p(f"  {u['table_name']:<45} {u['index_name']:<55} {mb(size_by_name.get(u['index_name'],0))}")
p(f"  -> total unused (non-unique, non-PK) index space: {mb(tot)}  count={len(unused)}")
p()

p("## FOREIGN KEYS WITHOUT A LEADING INDEX")
fk_ok = 0
fk_bad = []
for fk in RAW["foreign_keys"]:
    tbl = fk["child"].split(".")[-1]
    cols = fk["cols"] or []
    found = False
    for r in by_table.get(fk["child"], []) + by_table.get(tbl, []):
        c = sig.get(r["index_name"], [])
        if c[: len(cols)] == cols:
            found = True
            break
    if found:
        fk_ok += 1
    else:
        fk_bad.append((fk["child"], fk["conname"], cols, fk["definition"]))
for child, conname, cols, definition in fk_bad:
    size = tables.get(child.split(".")[-1], {}).get("total_bytes", 0)
    p(f"  {child:<45} {conname:<35} cols={cols} size={mb(size)}")
p(f"  -> FKs indexed: {fk_ok}, missing leading index: {len(fk_bad)}")
p()

p("## TABLES WITHOUT PRIMARY KEY")
for t in RAW["no_pk_tables"]:
    key = f"{t['schema']}.{t['table_name']}"
    info = tables.get(key, {})
    p(f"  {key:<55} live={t['n_live_tup']:>9} total={mb(info.get('total_bytes',0))} "
      f"indexes={info.get('n_indexes')}")
p()

p("## SEQUENCE HEADROOM (< 25% used)")
for s in RAW["sequences"]:
    lv, mx = s["last_value"], s["max_value"]
    try:
        lvf, mxf = float(lv), float(mx)
    except Exception:
        continue
    if mxf <= 0:
        continue
    used = lvf / mxf
    if used > 0.75:
        p(f"  {s['schema']}.{s['sequence']:<45} {s['data_type']:<8} used={used*100:6.2f}% last={lv}")
p()

p("## DEAD TUPLES / AUTOVACUUM PRESSURE")
rows = sorted(RAW["tables"], key=lambda t: -(t["n_dead_tup"] or 0))
for t in rows[:25]:
    live = t["n_live_tup"] or 0
    dead = t["n_dead_tup"] or 0
    if dead == 0:
        continue
    ratio = dead / max(live + dead, 1) * 100
    p(f"  {t['schema']}.{t['table_name']:<45} live={live:>10} dead={dead:>9} {ratio:5.1f}% "
      f"last_autovac={t['last_autovacuum']} opts={t['reloptions']}")
p()

p("## NEVER ANALYZED TABLES WITH ROWS")
for t in RAW["never_analyzed"]:
    p(f"  {t['schema']}.{t['table_name']:<50} live={t['n_live_tup']} total="
      f"{mb(tables.get(t['schema']+'.'+t['table_name'],{}).get('total_bytes',0))}")
p()

p("## INDEX-HEAVY TABLES (index bytes > heap bytes, size > 200MB)")
for key, t in sorted(tables.items(), key=lambda kv: -kv[1]["index_bytes"]):
    if t["total_bytes"] > 200 * 1048576 and t["index_bytes"] > t["heap_bytes"] > 0:
        p(f"  {key:<50} heap={mb(t['heap_bytes'])} idx={mb(t['index_bytes'])} "
          f"indexes={t['n_indexes']} live={t['n_live_tup']}")
p()

p("## TABLES WITH MANY INDEXES")
for key, t in sorted(tables.items(), key=lambda kv: -kv[1]["n_indexes"]):
    if t["n_indexes"] >= 8:
        p(f"  {key:<50} indexes={t['n_indexes']} cols={t['n_columns']} "
          f"idx_bytes={mb(t['index_bytes'])} live={t['n_live_tup']}")
p()

p("## TOAST-HEAVY TABLES")
for t in RAW["toast_heavy"]:
    p(f"  {t['schema']}.{t['table_name']:<45} toast={t['toast_size']}")
p()

p("## EMPTY / ZERO-LIVE TABLES (stats estimate = 0)")
for key, t in sorted(tables.items(), key=lambda kv: -kv[1]["total_bytes"]):
    if t["n_live_tup"] == 0 and t["total_bytes"] > 10 * 1048576:
        p(f"  {key:<50} est_rows={t['est_rows']} live=0 total={mb(t['total_bytes'])} "
          f"heap={mb(t['heap_bytes'])} idx={mb(t['index_bytes'])} "
          f"last_analyze={t['last_analyze']} last_autoanalyze={t['last_autoanalyze']}")
p()

p("## BACKUP / TEMP-LOOKING TABLES")
for key, t in tables.items():
    n = t["table_name"]
    if any(k in n for k in ("backup", "restore", "_bak", "_old", "tmp", "_copy")) or n.endswith("_temp"):
        p(f"  {key:<55} live={t['n_live_tup']:>10} total={mb(t['total_bytes'])}")
p()

p("## PARTITIONING")
p(json.dumps(RAW.get("partitions"), ensure_ascii=False, indent=1))
p(json.dumps(RAW.get("inherited_children"), ensure_ascii=False, indent=1))
p()

p("## TABLESPACES")
p(json.dumps(RAW.get("tablespaces"), ensure_ascii=False, indent=1))
p()

p("## YEAR-SUFFIXED TABLE FAMILIES (candidates for partitioning)")
fams = defaultdict(list)
for key, t in tables.items():
    name = t["table_name"]
    for suffix in ("_2024", "_2025", "_2026", "_2027"):
        if name.endswith(suffix):
            fams[name[: -len(suffix)]].append((name, t))
            break
for fam, items in sorted(fams.items(), key=lambda kv: -sum(i[1]["total_bytes"] for i in kv[1])):
    tot_b = sum(i[1]["total_bytes"] for i in items)
    p(f"  {fam}: {len(items)} tables, {mb(tot_b)}")
    for name, t in items:
        p(f"      {name:<50} live={t['n_live_tup']:>10} total={mb(t['total_bytes'])} "
          f"idx={mb(t['index_bytes'])} est_rows={t['est_rows']}")
p()

(HERE / "findings.txt").write_text("\n".join(OUT), encoding="utf-8")
print("\n".join(OUT))
print(f"\n[written] {HERE / 'findings.txt'}")