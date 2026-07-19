"""Print the first rows of a product-goods workbook without loading its formulas."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from zipfile import ZipFile
from xml.etree.ElementTree import iterparse

from scripts.import_product_goods_manual_fields import (
    PRODUCT_SHEET_NAME,
    XML_NAMESPACE,
    _cell_value,
    _column_index,
    _shared_strings,
    _sheet_xml_path,
    _xlsx_sheet_names,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--rows", type=int, default=5)
    parser.add_argument("--max-columns", type=int, default=None)
    parser.add_argument("--list-sheets", action="store_true")
    parser.add_argument("--sheet", default=PRODUCT_SHEET_NAME)
    args = parser.parse_args()
    with ZipFile(args.path) as archive:
        if args.list_sheets:
            print(json.dumps({"path": str(args.path), "sheets": _xlsx_sheet_names(archive)}, ensure_ascii=True))
            return
        shared_strings = _shared_strings(archive)
        sheet_path = _sheet_xml_path(archive, args.sheet)
        rows = []
        with archive.open(sheet_path) as stream:
            for _, element in iterparse(stream, events=("end",)):
                if element.tag != f"{XML_NAMESPACE}row":
                    continue
                row_number = int(element.attrib.get("r") or 0)
                if row_number > args.rows:
                    break
                values = {
                    _column_index(cell.attrib.get("r", "")): _cell_value(cell, shared_strings)
                    for cell in element.iter(f"{XML_NAMESPACE}c")
                    if args.max_columns is None or _column_index(cell.attrib.get("r", "")) < args.max_columns
                }
                rows.append((row_number, values))
                element.clear()
    print(json.dumps({"path": str(args.path), "rows": rows}, ensure_ascii=True))


if __name__ == "__main__":
    main()
