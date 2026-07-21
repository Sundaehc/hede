"""Import shop-to-channel mappings from a product-goods sales worksheet."""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET

from sqlalchemy import create_engine, delete

from config import DEFAULT_CBANNER_WOMENS_PRODUCT_DETAIL_SOURCE, load_settings
from domain.product_goods_shop_channel_schema import PRODUCT_GOODS_SHOP_CHANNEL_MAPPINGS_TABLE


XLSX_NAMESPACE = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
RELATIONSHIP_NAMESPACE = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PACKAGE_RELATIONSHIP_NAMESPACE = "{http://schemas.openxmlformats.org/package/2006/relationships}"
DEFAULT_SOURCE_FILE = DEFAULT_CBANNER_WOMENS_PRODUCT_DETAIL_SOURCE / "赫德货品表（千百度）7.20.xlsx"


def _column_index(reference: str) -> int:
    index = 0
    for character in reference:
        if not character.isalpha():
            break
        index = index * 26 + ord(character.upper()) - ord("A") + 1
    return index - 1


def _shared_strings(archive: ZipFile) -> list[str]:
    try:
        source = archive.open("xl/sharedStrings.xml")
    except KeyError:
        return []
    with source:
        root = ET.parse(source).getroot()
    return ["".join(item.itertext()) for item in root.findall(f"{XLSX_NAMESPACE}si")]


def _sheet_path(archive: ZipFile, sheet_name: str) -> str:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    sheet = next(
        (item for item in workbook.findall(f"{XLSX_NAMESPACE}sheets/{XLSX_NAMESPACE}sheet") if item.attrib.get("name") == sheet_name),
        None,
    )
    if sheet is None:
        raise ValueError(f"未找到 sheet: {sheet_name}")
    relationship_id = sheet.attrib.get(f"{RELATIONSHIP_NAMESPACE}id")
    relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    target = next(
        (
            item.attrib.get("Target")
            for item in relationships.findall(f"{PACKAGE_RELATIONSHIP_NAMESPACE}Relationship")
            if item.attrib.get("Id") == relationship_id
        ),
        None,
    )
    if not target:
        raise ValueError(f"无法定位 sheet: {sheet_name}")
    return f"xl/{target.lstrip('/')}"


def _cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        inline = cell.find(f"{XLSX_NAMESPACE}is")
        return "".join(inline.itertext()) if inline is not None else ""
    value = cell.find(f"{XLSX_NAMESPACE}v")
    if value is None or value.text is None:
        return ""
    if cell_type == "s":
        return shared_strings[int(value.text)]
    return value.text


def iter_shop_channel_rows(file_path: Path, *, sheet_name: str):
    with ZipFile(file_path) as archive:
        shared_strings = _shared_strings(archive)
        sheet_path = _sheet_path(archive, sheet_name)
        with archive.open(sheet_path) as source:
            channel_columns: list[int] | None = None
            for _, row in ET.iterparse(source, events=("end",)):
                if row.tag != f"{XLSX_NAMESPACE}row":
                    continue
                values = {
                    _column_index(cell.attrib.get("r", "")): _cell_value(cell, shared_strings).strip()
                    for cell in row.findall(f"{XLSX_NAMESPACE}c")
                }
                row.clear()
                if channel_columns is None:
                    channel_columns = [index for index, value in values.items() if value == "渠道"]
                    if len(channel_columns) < 2:
                        raise ValueError(f"{sheet_name} 未找到店铺和映射渠道两列")
                    continue
                shop_name = values.get(channel_columns[0], "")
                channel = values.get(channel_columns[-1], "")
                if shop_name and channel and channel != "#N/A":
                    yield shop_name, channel


def import_shop_channel_mappings(file_path: Path, *, brand: str, sheet_name: str) -> dict[str, object]:
    mappings: dict[str, set[str]] = defaultdict(set)
    source_rows = 0
    for shop_name, channel in iter_shop_channel_rows(file_path, sheet_name=sheet_name):
        source_rows += 1
        mappings[shop_name].add(channel)
    conflicts = {shop_name: sorted(channels) for shop_name, channels in mappings.items() if len(channels) > 1}
    if conflicts:
        sample = next(iter(conflicts.items()))
        raise ValueError(f"店铺映射存在冲突: {sample[0]} -> {', '.join(sample[1])}")

    settings = load_settings(require_database=True)
    assert settings.database_url is not None
    engine = create_engine(settings.database_url, future=True)
    rows = [
        {
            "brand": brand,
            "shop_name": shop_name,
            "channel": next(iter(channels)),
            "source_workbook": file_path.name,
            "source_sheet": sheet_name,
        }
        for shop_name, channels in sorted(mappings.items())
    ]
    with engine.begin() as connection:
        PRODUCT_GOODS_SHOP_CHANNEL_MAPPINGS_TABLE.create(connection, checkfirst=True)
        connection.execute(delete(PRODUCT_GOODS_SHOP_CHANNEL_MAPPINGS_TABLE).where(PRODUCT_GOODS_SHOP_CHANNEL_MAPPINGS_TABLE.c.brand == brand))
        if rows:
            connection.execute(PRODUCT_GOODS_SHOP_CHANNEL_MAPPINGS_TABLE.insert(), rows)
    return {
        "brand": brand,
        "source": str(file_path),
        "sheet": sheet_name,
        "source_rows": source_rows,
        "shops": len(rows),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="导入货品表店铺渠道映射")
    parser.add_argument("--file", type=Path, default=DEFAULT_SOURCE_FILE)
    parser.add_argument("--brand", default="cbanner_womens")
    parser.add_argument("--sheet", default="2025年销量")
    args = parser.parse_args()
    if not args.file.exists():
        raise FileNotFoundError(f"映射源文件不存在: {args.file}")
    print(import_shop_channel_mappings(args.file, brand=args.brand, sheet_name=args.sheet))


if __name__ == "__main__":
    main()
