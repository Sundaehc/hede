"""Index quality reports from the shared workbooks, without altering the source files."""
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import file_digest, sha256
import os
from pathlib import Path
import re
from threading import Lock
from time import monotonic
import unicodedata
from zipfile import BadZipFile

from openpyxl import load_workbook

SUMMARY_DIR = "质检报告汇总"
NATIVE_BRANDS = {
    "NI质检表格汇总.xlsx": {"ni"},
    "伊伴质检表格汇总.xlsx": {"eblan"},
    "千百度质检表格汇总.xlsx": {"cbanner_womens", "cbanner_mens"},
    "烟斗质检货号汇总.xlsx": {"yandou"},
    "笑脸质检表格汇总.xlsx": {"smiley"},
}
RESULT_HEADERS = {"检查结果", "检测结果", "检验结果", "质检结果", "报告名称"}
REPORT_EXTENSIONS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}
REPORT_NUMBER = re.compile(r"(?<![0-9])[0-9]{8,15}(?![0-9])")
RESULT_SEPARATOR = re.compile(r"[\r\n;；]+")
SKU_SEPARATOR = re.compile(r"[\s,，、/／;；]+")
CACHE_SECONDS = 300


class QualitySourceUnavailable(Exception):
    pass


def _normalize(value):
    if value is None:
        return ""
    return unicodedata.normalize("NFKC", str(value)).strip()


def _sku(value):
    return _normalize(value).upper()


def _report_name(value):
    value = _normalize(value)
    ext = Path(value).suffix.lower()
    return (re.sub(r"\s+", "", value[:-len(ext)] if ext in REPORT_EXTENSIONS else value).upper(),
            ext if ext in REPORT_EXTENSIONS else "")


@dataclass(frozen=True)
class SummaryReference:
    name: str
    workbook: str
    sheet: str
    row: int


@dataclass(frozen=True)
class QualityCatalog:
    root: Path
    references: dict[str, list[SummaryReference]]
    by_name: dict[str, list[Path]]
    by_number: dict[str, list[Path]]


@dataclass(frozen=True)
class MatchedReport:
    id: str
    name: str
    sources: list[SummaryReference]
    status: str
    path: Path | None

    def public(self):
        modified_at = None
        if self.path is not None:
            try:
                modified_at = datetime.fromtimestamp(self.path.stat().st_mtime, tz=timezone.utc).isoformat()
            except OSError:
                pass
        return {
            "id": self.id,
            "name": self.name,
            "file_name": self.path.name if self.path else None,
            "modified_at": modified_at,
            "status": self.status,
            "sources": [{"workbook": source.workbook, "sheet": source.sheet, "row": source.row}
                        for source in self.sources],
        }


def _index_workbook(path, references):
    workbook = load_workbook(path, read_only=True, data_only=True, keep_links=False)
    has_summary = False
    try:
        for sheet in workbook:
            columns = None
            for row_number, row in enumerate(sheet.values, 1):
                if columns is None:
                    if row_number > 12:
                        break
                    headers = [re.sub(r"\s+", "", _normalize(value)) for value in row]
                    result_columns = [index for index, header in enumerate(headers) if header in RESULT_HEADERS]
                    if "原始货号" in headers and result_columns:
                        columns = headers.index("原始货号"), result_columns
                        has_summary = True
                    continue
                sku_column, result_columns = columns
                codes = _sku(row[sku_column])
                if not codes or codes.startswith(("#", "=")):
                    continue
                # Keep a literal original code and support cells listing several original codes.
                keys = {codes, *(code for code in SKU_SEPARATOR.split(codes)
                                 if re.fullmatch(r"[A-Z0-9_-]+", code) and any(char.isdigit() for char in code))}
                for index in result_columns:
                    for name in RESULT_SEPARATOR.split(_normalize(row[index])):
                        name = name.strip()
                        if not name or name.startswith(("#", "=")):
                            continue
                        reference = SummaryReference(name, path.name, sheet.title, row_number)
                        for key in keys:
                            references[key].append(reference)
    finally:
        workbook.close()
    return has_summary


def build_catalog(root):
    root = root.resolve(strict=True)
    summary_dir = root / SUMMARY_DIR
    if not summary_dir.resolve(strict=True).is_relative_to(root):
        raise QualitySourceUnavailable
    workbooks = sorted(path for path in summary_dir.iterdir()
                       if path.suffix.lower() == ".xlsx" and not path.name.startswith("~$"))
    references, by_name, by_number = defaultdict(list), defaultdict(list), defaultdict(list)
    for path in workbooks:
        if not path.resolve(strict=True).is_relative_to(root) or not _index_workbook(path, references):
            raise QualitySourceUnavailable(f"无法读取质检汇总表头：{path.name}")
    if not workbooks:
        raise QualitySourceUnavailable("质检汇总目录为空")

    def raise_walk_error(error):
        raise error

    for folder, dirs, files in os.walk(root, onerror=raise_walk_error):
        dirs[:] = [name for name in dirs if not (Path(folder) / name).is_junction()]
        for filename in files:
            path = Path(folder) / filename
            if path in workbooks or path.suffix.lower() not in REPORT_EXTENSIONS or filename.startswith("~$"):
                continue
            key, _ = _report_name(filename)
            by_name[key].append(path)
            for number in set(REPORT_NUMBER.findall(key)):
                by_number[number].append(path)
    return QualityCatalog(root, dict(references), dict(by_name), dict(by_number))


class StockQualityReports:
    def __init__(self, root):
        self.root = root
        self._lock = Lock()
        self._catalog = None
        self._expires = 0

    def catalog(self):
        with self._lock:
            if self._catalog is not None and monotonic() < self._expires:
                return self._catalog
            try:
                self._catalog = build_catalog(self.root)
            except (OSError, BadZipFile, ValueError, KeyError) as error:
                raise QualitySourceUnavailable from error
            self._expires = monotonic() + CACHE_SECONDS
            return self._catalog

    def for_product(self, original_sku, brand):
        original = _sku(original_sku)
        if not original:
            return []
        catalog = self.catalog()
        grouped = defaultdict(list)
        for reference in catalog.references.get(original, []):
            workbook_brands = NATIVE_BRANDS.get(reference.workbook)
            if workbook_brands is None or brand in workbook_brands:
                grouped[_report_name(reference.name)].append(reference)
        items = []
        for (key, extension), sources in grouped.items():
            name = sources[0].name
            status, path = _resolve_report(catalog, key, extension, original)
            report_id = sha256(f"{key}\n{extension}".encode()).hexdigest()[:32]
            items.append(MatchedReport(report_id, name, list(dict.fromkeys(sources)), status, path))
        merged = {}
        for item in items:
            key = item.path if item.path else item.id
            current = merged.get(key)
            if current is None:
                merged[key] = item
            else:
                sources = list(dict.fromkeys(current.sources + item.sources))
                preferred = item if item.status == "matched" and current.status != "matched" else current
                merged[key] = MatchedReport(preferred.id, preferred.name, sources, preferred.status, key)
        return list(merged.values())


def _existing_files(catalog, candidates, extension):
    for path in sorted(set(candidates)):
        if extension and path.suffix.lower() != extension:
            continue
        try:
            resolved = path.resolve(strict=True)
            if resolved.is_relative_to(catalog.root) and resolved.is_file():
                yield resolved
        except FileNotFoundError:
            continue


def _single_file(catalog, candidates, extension):
    paths = list(dict.fromkeys(_existing_files(catalog, candidates, extension)))
    if not paths:
        return "missing", None
    if len(paths) == 1:
        return "matched", paths[0]
    if len({path.stat().st_size for path in paths}) == 1:
        hashes = set()
        for path in paths:
            with path.open("rb") as source:
                hashes.add(file_digest(source, "sha256").digest())
            if len(hashes) > 1:
                break
        if len(hashes) == 1:
            return "matched", paths[0]
    return "ambiguous", None


def _resolve_report(catalog, key, extension, original):
    status, path = _single_file(catalog, catalog.by_name.get(key, []), extension)
    if status != "missing":
        return status, path

    # A uniquely identifiable report number can survive a renamed result or a copy suffix.
    # The original code itself cannot serve as proof of a specific report.
    numbers = set(REPORT_NUMBER.findall(key)) - set(REPORT_NUMBER.findall(original))
    if len(numbers) != 1:
        return "missing", None
    candidates = catalog.by_number.get(next(iter(numbers)), [])
    status, path = _single_file(catalog, candidates, extension)
    return ("number_match", path) if path else (status, None)

