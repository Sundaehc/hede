from __future__ import annotations

from tempfile import SpooledTemporaryFile

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


BARCODE_EXPORT_COLUMNS = (
    ("品牌", "brand", 18),
    ("货号", "sku", 26),
    ("原始货号", "original_sku", 26),
    ("品名", "product_name", 28),
    ("颜色", "color", 16),
    ("颜色代码", "color_code", 14),
    ("尺码组", "size_range", 22),
    ("尺码", "size_name", 12),
    ("尺码条码", "size_barcode", 16),
    ("条码构成逻辑", "barcode_build_rule", 30),
    ("完整条码", "barcode", 38),
    ("资料提示", "issue", 38),
)
EXCEL_MAX_DATA_ROWS = 1_048_575


def build_product_barcode_export(rows, brand_labels: dict[str, str]):
    """Write the query cursor to XLSX without accumulating all expanded rows."""
    workbook = Workbook(write_only=True)
    buffer = SpooledTemporaryFile(max_size=4 * 1024 * 1024, mode="w+b")
    header_font = Font(name="宋体", size=10, bold=True)
    body_font = Font(name="宋体", size=10)
    header_fill = PatternFill("solid", fgColor="F2F2F2")
    warning_font = Font(name="宋体", size=10, color="9C5700")
    alignment = Alignment(horizontal="left", vertical="center")

    def new_sheet():
        number = len(workbook.worksheets) + 1
        sheet = workbook.create_sheet("条码搜索" if number == 1 else f"条码搜索{number}")
        sheet.freeze_panes = "A2"
        sheet.sheet_view.showGridLines = False
        sheet.sheet_format.defaultRowHeight = 22
        sheet.row_dimensions[1].height = 26
        cells = []
        for index, (label, _, width) in enumerate(BARCODE_EXPORT_COLUMNS, start=1):
            sheet.column_dimensions[get_column_letter(index)].width = width
            cell = WriteOnlyCell(sheet, value=label)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cells.append(cell)
        sheet.append(cells)
        return sheet

    worksheet = new_sheet()
    count = 0
    sheet_count = 0
    try:
        for row in rows:
            if sheet_count == EXCEL_MAX_DATA_ROWS:
                worksheet.auto_filter.ref = f"A1:L{sheet_count + 1}"
                worksheet = new_sheet()
                sheet_count = 0
            cells = []
            for _, field, _ in BARCODE_EXPORT_COLUMNS:
                value = row.get(field)
                if field == "brand":
                    value = brand_labels.get(str(value), value)
                cell = WriteOnlyCell(worksheet, value=ILLEGAL_CHARACTERS_RE.sub("", str(value or "")))
                # Store identifiers as literal strings, preserving leading zeroes,
                # long numbers and values that Excel might otherwise treat as formulas.
                cell.data_type = "s"
                cell.number_format = "@"
                cell.font = warning_font if field == "issue" and value else body_font
                cell.alignment = alignment
                cells.append(cell)
            worksheet.append(cells)
            count += 1
            sheet_count += 1
        worksheet.auto_filter.ref = f"A1:L{sheet_count + 1}"
        workbook.save(buffer)
        buffer.seek(0)
        return buffer, count
    except BaseException:
        buffer.close()
        raise
    finally:
        workbook.close()
