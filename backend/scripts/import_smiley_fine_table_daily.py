"""Run the daily Smiley fine-table import with bounded retries."""

from __future__ import annotations

import argparse
from datetime import date, datetime, time as day_time
from pathlib import Path
import subprocess
import sys
import time
from typing import Callable

from config import load_settings
from scripts.import_smiley_fine_table import default_file_for_date


def _parse_retry_until(value: str | None, *, business_date: date) -> datetime | None:
    if not value:
        return None
    return datetime.combine(business_date, day_time.fromisoformat(value))


def _run_with_retry(
    run_attempt: Callable[[], int],
    *,
    retry_until: datetime | None,
    retry_interval_seconds: int,
    now: Callable[[], datetime] = datetime.now,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    attempt = 0
    while True:
        attempt += 1
        print(f"[ATTEMPT] Smiley fine-table import attempt={attempt}", flush=True)
        exit_code = int(run_attempt())
        if exit_code == 0:
            print(f"[SUCCESS] Smiley fine-table import completed attempt={attempt}", flush=True)
            return 0

        current_time = now()
        if retry_until is None or current_time >= retry_until:
            print(
                "[RETRY-STOP] Smiley fine-table import is still unresolved at the retry deadline",
                flush=True,
            )
            return exit_code or 1

        sleep_seconds = min(
            max(retry_interval_seconds, 1),
            max(int((retry_until - current_time).total_seconds()), 1),
        )
        print(
            f"[RETRY] Smiley source/import not ready; retrying in {sleep_seconds}s",
            flush=True,
        )
        sleep(sleep_seconds)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import today's Smiley fine table and retry while the source is unavailable"
    )
    parser.add_argument("--business-date", type=date.fromisoformat, default=date.today())
    parser.add_argument("--source-file", type=Path, default=None)
    parser.add_argument("--retry-until", default=None, help="Retry until local time HH:MM")
    parser.add_argument("--retry-interval-seconds", type=int, default=1800)
    args = parser.parse_args()
    if args.retry_interval_seconds < 1:
        raise ValueError("--retry-interval-seconds must be at least 1")

    settings = load_settings(require_database=True)
    source_root = settings.smiley_fine_table_root
    if source_root is None and args.source_file is None:
        raise ValueError("SMILEY_FINE_TABLE_ROOT is required")
    source_file = args.source_file or default_file_for_date(source_root, args.business_date)
    retry_until = _parse_retry_until(args.retry_until, business_date=args.business_date)

    command = [
        sys.executable,
        "-m",
        "scripts.import_smiley_fine_table",
        "--replace",
        "--snapshot-date",
        args.business_date.isoformat(),
        "--file",
        str(source_file),
    ]

    def run_attempt() -> int:
        try:
            if not source_file.is_file():
                print(f"[WAIT] Smiley source file does not exist: {source_file}", flush=True)
                return 1
        except OSError as exc:
            print(
                f"[WAIT] Smiley source file is unavailable: {type(exc).__name__}: {exc}",
                flush=True,
            )
            return 1
        return subprocess.call(command)

    return _run_with_retry(
        run_attempt,
        retry_until=retry_until,
        retry_interval_seconds=args.retry_interval_seconds,
    )


if __name__ == "__main__":
    raise SystemExit(main())
