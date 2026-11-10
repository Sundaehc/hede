from __future__ import annotations

from decimal import Decimal
from typing import Mapping
import unicodedata

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.worksheet import Worksheet


def build_ending_inventory_workbook(result: Mapping[str, object]) -> Workbook:
    """Write the bounded query result without retaining an Excel cell grid."""
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("期末库存商品")
    sheet.sheet_view.showGridLines = False
    sheet.freeze_panes = "D2"
    for letter, width in zip("ABCDEFG", (36, 32, 18, 16, 16, 16, 16)):
        sheet.column_dimensions[letter].width = width
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.paperSize = Worksheet.PAPERSIZE_A4
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    sheet.print_title_rows = "1:1"
    body_font = Font(name="宋体", size=10)
    bold_font = Font(name="宋体", size=10, bold=True)
    alignments = {
        key: Alignment(horizontal=key, vertical="center") for key in ("left", "right", "center")
    }
    wrapped_text = Alignment(horizontal="left", vertical="center", wrap_text=True)
    header_fill = PatternFill("solid", fgColor="F2F2F2")

    def cells(values, *, header=False, bold=False):
        row = []
        for value in values:
            cell = WriteOnlyCell(sheet, value=value)
            if isinstance(value, str):
                # Codes and formula-like names are literal text in the file.
                cell.data_type = "s"
                cell.number_format = "@"
            else:
                cell.number_format = "#,##0.00;[Red]-#,##0.00;0"
            cell.font = bold_font if header or bold else body_font
            cell.alignment = alignments["center" if header else "left" if isinstance(value, str) else "right"]
            if header:
                cell.fill = header_fill
            row.append(cell)
        return row

    def number(value):
        quantity = Decimal(str(value or 0))
        return int(quantity) if quantity == quantity.to_integral_value() else float(quantity)

    sheet.row_dimensions[1].height = 24
    sheet.append(cells(["商品货号", "商品名称", "颜色", "期初库存", "本期入库", "本期出库", "期末库存"], header=True))
    fields = ("beginning_qty", "inbound_qty", "outbound_qty", "ending_qty")
    sums = [Decimal(0)] * 4
    for row_number, item in enumerate(result["items"], start=2):
        quantities = [Decimal(str(item[field])) for field in fields]
        sums = [total + qty for total, qty in zip(sums, quantities)]
        row_values = [
            item["product_code"] or "", item["product_name"] or "", item["color_name"] or item["color_spec"] or "",
            *(number(qty) for qty in quantities),
        ]
        row_cells = cells(row_values)
        line_count = 1
        for index, capacity in enumerate((32, 28, 14)):
            text = row_values[index]
            width = sum(2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1 for char in text)
            line_count = max(line_count, (width + capacity - 1) // capacity, len(text.splitlines()))
            row_cells[index].alignment = wrapped_text
        sheet.row_dimensions[row_number].height = min(409, max(22, line_count * 15))
        sheet.append(row_cells)
    last_data_row = 1 + len(result["items"])
    sheet.auto_filter.ref = f"A1:G{last_data_row}"
    sheet.append(cells(["清单合计", "", "", *(number(qty) for qty in sums)], bold=True))
    return workbook
