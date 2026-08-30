"""Repair database field names used as headers in historical fine-table exports.

The default mode only reports affected workbooks. Pass ``--apply`` to update
the first worksheet header row in place. Workbook entries are copied as a
stream so large historical exports do not need to be loaded into memory.
"""

from __future__ import annotations

import argparse
import html
import os
import re
import shutil
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from config import load_settings
from scripts.export_fine_table_daily import KNOWN_COLUMNS


HEADER_END = b"</row>"
SHEET_PATH = "xl/worksheets/sheet1.xml"
HEADER_TEXT_PATTERN = re.compile(rb"<t(?:\s[^>]*)?>(.*?)</t>")
SNAKE_CASE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
HEADER_LABELS = {key: label for key, label in KNOWN_COLUMNS if key != label}


def _read_header_prefix(source) -> tuple[bytes, bytes]:
    buffer = bytearray()
    while HEADER_END not in buffer:
        chunk = source.read(64 * 1024)
        if not chunk:
            raise ValueError("The first worksheet does not contain a header row")
        buffer.extend(chunk)
    end_index = buffer.index(HEADER_END) + len(HEADER_END)
    return bytes(buffer[:end_index]), bytes(buffer[end_index:])


def _header_values(prefix: bytes) -> list[str]:
    return [
        html.unescape(match.group(1).decode("utf-8"))
        for match in HEADER_TEXT_PATTERN.finditer(prefix)
    ]


def inspect_workbook(path: Path) -> tuple[dict[str, str], list[str]]:
    with ZipFile(path) as workbook:
        with workbook.open(SHEET_PATH) as worksheet:
            prefix, _remainder = _read_header_prefix(worksheet)
    headers = _header_values(prefix)
    replacements = {header: HEADER_LABELS[header] for header in headers if header in HEADER_LABELS}
    unknown_english = sorted(
        {header for header in headers if SNAKE_CASE_PATTERN.fullmatch(header) and header not in replacements}
    )
    return replacements, unknown_english


def _replace_header_values(prefix: bytes, replacements: dict[str, str]) -> bytes:
    repaired = prefix.decode("utf-8")
    for old_value, new_value in replacements.items():
        pattern = re.compile(
            rf"(<t(?:\s[^>]*)?>){re.escape(html.escape(old_value))}(</t>)"
        )
        repaired, count = pattern.subn(
            lambda match: f"{match.group(1)}{html.escape(new_value)}{match.group(2)}",
            repaired,
        )
        if count == 0:
            raise ValueError(f"Header not found while repairing: {old_value}")
    return repaired.encode("utf-8")


def _copy_entry(
    source_workbook: ZipFile,
    target_workbook: ZipFile,
    entry: ZipInfo,
    replacements: dict[str, str],
) -> None:
    with source_workbook.open(entry) as source, target_workbook.open(entry, "w", force_zip64=True) as target:
        if entry.filename != SHEET_PATH:
            shutil.copyfileobj(source, target, length=1024 * 1024)
            return
        prefix, remainder = _read_header_prefix(source)
        target.write(_replace_header_values(prefix, replacements))
        target.write(remainder)
        shutil.copyfileobj(source, target, length=1024 * 1024)


def repair_workbook(path: Path, replacements: dict[str, str]) -> None:
    original_stat = path.stat()
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{path.stem}.",
            suffix=".tmp.xlsx",
            dir=path.parent,
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)

        with ZipFile(path) as source_workbook, ZipFile(
            temporary_path,
            "w",
            compression=ZIP_DEFLATED,
            allowZip64=True,
        ) as target_workbook:
            target_workbook.comment = source_workbook.comment
            for entry in source_workbook.infolist():
                _copy_entry(source_workbook, target_workbook, entry, replacements)

        remaining, _unknown = inspect_workbook(temporary_path)
        if remaining:
            raise ValueError(f"Headers remain after repair: {', '.join(remaining)}")
        os.replace(temporary_path, path)
        temporary_path = None
        os.utime(path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Repair historical fine-table Excel headers")
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    settings = load_settings(require_database=False)
    root = args.root or settings.fine_table_export_root
    if root is None:
        raise ValueError("FINE_TABLE_EXPORT_ROOT is required")

    workbooks = sorted(root.rglob("*.xlsx"))
    affected_count = 0
    repaired_count = 0
    unknown_headers: set[str] = set()
    for path in workbooks:
        replacements, unknown_english = inspect_workbook(path)
        unknown_headers.update(unknown_english)
        if not replacements:
            continue
        affected_count += 1
        fields = ", ".join(f"{key}->{label}" for key, label in replacements.items())
        print(f"[affected] {path} | {fields}")
        if args.apply:
            repair_workbook(path, replacements)
            repaired_count += 1
            print(f"[repaired] {path}")

    print(
        f"summary scanned={len(workbooks)} affected={affected_count} "
        f"repaired={repaired_count} unknown_english={sorted(unknown_headers)}"
    )


if __name__ == "__main__":
    main()
