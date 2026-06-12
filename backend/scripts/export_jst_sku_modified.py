"""Export JST SKU data by modified time.

Run from backend:
    python -m scripts.export_jst_sku_modified

Required .env values:
    JST_API_KEY
    JST_API_SECRET
    JST_ACCESS_TOKEN
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib import parse, request

from dotenv import load_dotenv


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
API_URL = "https://openapi.jushuitan.com/open/sku/query"
DATE_FMT = "%Y-%m-%d %H:%M:%S"


def _parse_dt(value: str) -> datetime:
    try:
        if len(value) == 10:
            return datetime.strptime(value, "%Y-%m-%d")
        return datetime.strptime(value, DATE_FMT)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid datetime: {value!r}") from exc


def _json_dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _sign(params: dict[str, str], app_secret: str) -> str:
    sign_str = app_secret
    for key in sorted(params):
        if key == "sign":
            continue
        sign_str += str(key)
        sign_str += str(params[key])
    return hashlib.md5(sign_str.encode("utf-8")).hexdigest()


def _post_form(params: dict[str, str], timeout: int) -> dict[str, Any]:
    body = parse.urlencode(params).encode("utf-8")
    req = request.Request(
        API_URL,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
        method="POST",
    )
    with request.urlopen(req, timeout=timeout) as resp:
        payload = resp.read().decode("utf-8")
    return json.loads(payload)


def _iter_windows(start: datetime, end: datetime, delta: timedelta):
    cursor = start
    while cursor < end:
        window_end = min(cursor + delta, end)
        yield cursor, window_end
        cursor = window_end


def _write_csv(jsonl_path: Path, csv_path: Path) -> int:
    fields: list[str] = []
    seen: set[str] = set()
    row_count = 0

    with jsonl_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            row = json.loads(line)
            row_count += 1
            for key in row:
                if key not in seen:
                    seen.add(key)
                    fields.append(key)

    with jsonl_path.open("r", encoding="utf-8") as src, csv_path.open(
        "w", encoding="utf-8-sig", newline=""
    ) as dst:
        writer = csv.DictWriter(dst, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for line in src:
            if line.strip():
                writer.writerow(json.loads(line))

    return row_count


def export(args: argparse.Namespace) -> dict[str, Any]:
    load_dotenv(BACKEND_ROOT / ".env", override=False)

    app_key = args.app_key or os.getenv("JST_API_KEY")
    app_secret = args.app_secret or os.getenv("JST_API_SECRET")
    access_token = (
        args.access_token
        or os.getenv("JST_ACCESS_TOKEN")
        or os.getenv("JST_API_ACCESS_TOKEN")
    )
    missing = [
        name
        for name, value in (
            ("JST_API_KEY", app_key),
            ("JST_API_SECRET", app_secret),
            ("JST_ACCESS_TOKEN", access_token),
        )
        if not value
    ]
    if missing:
        raise SystemExit(
            "Missing required credential(s): "
            + ", ".join(missing)
            + ". Add JST_ACCESS_TOKEN to backend/.env or pass --access-token."
        )

    end = args.end or datetime.now()
    start = args.start or (end - timedelta(days=365 * 2))
    if start >= end:
        raise SystemExit("--start must be earlier than --end")

    window = timedelta(hours=args.window_hours)
    max_window = timedelta(days=7)
    if window <= timedelta(0) or window > max_window:
        raise SystemExit("--window-hours must be > 0 and <= 168")

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"{start:%Y-%m-%d}_to_{end:%Y-%m-%d}"
    jsonl_path = args.jsonl or output_dir / f"jst_sku_modified_{suffix}.jsonl"
    csv_path = args.csv or output_dir / f"jst_sku_modified_{suffix}.csv"

    total = 0
    windows = 0
    with jsonl_path.open("w", encoding="utf-8") as out:
        for begin, finish in _iter_windows(start, end, window):
            windows += 1
            page_index = 1
            while True:
                biz = {
                    "page_index": page_index,
                    "page_size": args.page_size,
                    "modified_begin": begin.strftime(DATE_FMT),
                    "modified_end": finish.strftime(DATE_FMT),
                    "date_field": "modified",
                }
                if args.fields:
                    biz["flds"] = args.fields
                if args.load_sku_bin:
                    biz["loadSkuBin"] = True

                common = {
                    "access_token": access_token,
                    "app_key": app_key,
                    "biz": _json_dumps(biz),
                    "charset": "utf-8",
                    "timestamp": str(int(time.time())),
                    "version": "2",
                }
                common["sign"] = _sign(common, app_secret)
                response = _post_form(common, args.timeout)
                if response.get("code") != 0:
                    raise SystemExit(
                        "JST API error "
                        f"code={response.get('code')} msg={response.get('msg')} "
                        f"window={begin.strftime(DATE_FMT)}~{finish.strftime(DATE_FMT)} "
                        f"page={page_index}"
                    )

                data = response.get("data") or {}
                rows = data.get("datas") or []
                for row in rows:
                    out.write(_json_dumps(row) + "\n")
                total += len(rows)

                if args.verbose:
                    print(
                        f"{begin.strftime(DATE_FMT)} ~ {finish.strftime(DATE_FMT)} "
                        f"page={page_index} rows={len(rows)} total={total}"
                    )

                if not data.get("has_next"):
                    break
                page_index += 1
                time.sleep(args.sleep)

            time.sleep(args.sleep)

    csv_count = _write_csv(jsonl_path, csv_path)
    return {
        "rows": total,
        "csv_rows": csv_count,
        "windows": windows,
        "jsonl": str(jsonl_path),
        "csv": str(csv_path),
        "start": start.strftime(DATE_FMT),
        "end": end.strftime(DATE_FMT),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=_parse_dt)
    parser.add_argument("--end", type=_parse_dt)
    parser.add_argument("--window-hours", type=int, default=168)
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--fields", default="")
    parser.add_argument("--load-sku-bin", action="store_true")
    parser.add_argument("--sleep", type=float, default=0.2)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "outputs")
    parser.add_argument("--jsonl", type=Path)
    parser.add_argument("--csv", type=Path)
    parser.add_argument("--app-key")
    parser.add_argument("--app-secret")
    parser.add_argument("--access-token")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if not 1 <= args.page_size <= 100:
        raise SystemExit("--page-size must be between 1 and 100")

    result = export(args)
    print(_json_dumps(result))


if __name__ == "__main__":
    main()
