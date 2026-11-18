"""Validate required derived worksheets before replacing JST stock data."""
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile


def require_stock_worksheets(path: Path, required: tuple[str, ...]) -> None:
    with ZipFile(path) as archive:
        workbook = ET.fromstring(archive.read('xl/workbook.xml'))
    namespace = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
    sheet_names = [sheet.attrib['name'] for sheet in workbook.findall(f'{namespace}sheets/{namespace}sheet')]
    missing = [name for name in required if name not in sheet_names]
    if missing:
        raise ValueError(
            f'{path.name} 缺少必需工作表：{"、".join(missing)}；'
            f'现有工作表：{"、".join(sheet_names) or "无"}。'
            '请先完成源文件的汇总处理后重试；未替换本次库存数据。'
        )
