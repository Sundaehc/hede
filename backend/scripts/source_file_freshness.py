from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Iterable


def require_business_date_source(
    source_file: Path,
    business_date: date,
) -> dict[str, object]:
    """Require a non-empty source file modified on the task business date."""
    try:
        stat = source_file.stat()
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"源文件不存在: {source_file}") from exc
    except OSError as exc:
        raise OSError(f"源文件无法访问: {source_file}: {type(exc).__name__}: {exc}") from exc

    if stat.st_size <= 0:
        raise ValueError(f"源文件为空: {source_file}")

    modified_at = datetime.fromtimestamp(stat.st_mtime).astimezone()
    if modified_at.date() != business_date:
        raise ValueError(
            f"源文件不是 {business_date.isoformat()} 当日文件: {source_file}; "
            f"最后修改时间={modified_at.isoformat(timespec='seconds')}"
        )

    return {
        "source_file": str(source_file),
        "size_bytes": stat.st_size,
        "modified_at": modified_at.isoformat(timespec="seconds"),
    }


def require_business_date_sources(
    source_files: Iterable[Path],
    business_date: date,
) -> list[dict[str, object]]:
    """Validate every file before callers start any database replacement."""
    return [
        require_business_date_source(source_file, business_date)
        for source_file in source_files
    ]
