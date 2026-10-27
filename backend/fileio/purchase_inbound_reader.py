from __future__ import annotations

from collections.abc import Iterator
import posixpath
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

from openpyxl.utils.escape import unescape


NAMESPACE = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
RELATIONSHIP_NAMESPACE = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def _column_index(reference: str) -> int:
    position = 0
    for character in reference:
        if not character.isalpha():
            break
        position = position * 26 + ord(character.upper()) - ord("A") + 1
    return position - 1


def _cell_value(cell, shared_strings: list[str]) -> str:
    if cell.get("t") == "inlineStr":
        value = "".join(node.text or "" for node in cell.iter(f"{NAMESPACE}t"))
    else:
        node = cell.find(f"{NAMESPACE}v")
        value = node.text or "" if node is not None else ""
        if cell.get("t") == "s":
            value = shared_strings[int(value)]
    return unescape(value).strip()


def _rows(source, *, accelerated: bool) -> Iterator:
    if accelerated:
        from lxml import etree

        for _, row in etree.iterparse(source, events=("end",), tag=f"{NAMESPACE}row"):
            yield row
            parent = row.getparent()
            row.clear()
            while row.getprevious() is not None:
                del parent[0]
    else:
        sheet_data = None
        for event, element in ElementTree.iterparse(source, events=("start", "end")):
            if event == "start" and element.tag == f"{NAMESPACE}sheetData":
                sheet_data = element
            elif event == "end" and element.tag == f"{NAMESPACE}row":
                yield element
                element.clear()
                if sheet_data is not None:
                    sheet_data.remove(element)


def iter_purchase_inbound_rows(
    path: Path, *, accelerated: bool | None = None,
) -> Iterator[tuple[str, int, dict[int, str]]]:
    if accelerated is None:
        try:
            import lxml.etree
        except ImportError:
            accelerated = False
        else:
            accelerated = True
    with ZipFile(path) as archive:
        shared_strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            with archive.open("xl/sharedStrings.xml") as source:
                root = ElementTree.parse(source).getroot()
            shared_strings = [
                unescape("".join(node.text or "" for node in item.iter(f"{NAMESPACE}t")))
                for item in root.findall(f"{NAMESPACE}si")
            ]
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        relationships = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {item.get("Id"): item.get("Target", "") for item in relationships}
        for sheet in workbook.findall(f"{NAMESPACE}sheets/{NAMESPACE}sheet"):
            target = targets[sheet.get(f"{RELATIONSHIP_NAMESPACE}id")]
            sheet_path = target.lstrip("/") if target.startswith("/") else posixpath.normpath(f"xl/{target}")
            with archive.open(sheet_path) as source:
                for row in _rows(source, accelerated=accelerated):
                    values = {
                        _column_index(cell.get("r", "")): _cell_value(cell, shared_strings)
                        for cell in row
                        if cell.tag == f"{NAMESPACE}c"
                    }
                    yield sheet.get("name", ""), int(row.get("r", "0")), values
