from __future__ import annotations

from decimal import Decimal
from typing import Mapping
import unicodedata

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Alignment, Border, Font, Side
from openpyxl.worksheet.page import PageMargins
from openpyxl.worksheet.worksheet import Worksheet
from openpyxl.utils import get_column_letter


def build_ending_inventory_workbook(result: Mapping[str, object], *, display_mode: str = "goods") -> Workbook:
    """Write the bounded query result without retaining an Excel cell grid."""
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("期末库存商品")
    sheet.sheet_view.showGridLines = False
    barcode = display_mode == "barcode"
    text_headers = ["商品货号", "商品名称", "颜色"]
    if barcode:
        text_headers += ["商品编码", "颜色条码", "尺码名称", "尺码条码", "编码提示"]
    # Keep identifiers visible without freezing the whole wide barcode section.
    sheet.freeze_panes = "C2"
    sheet.sheet_format.defaultRowHeight = 18
    widths = [30, 30, 14] + ([36, 12, 10, 12, 28] if barcode else []) + [12] * 4
    for index, width in enumerate(widths, 1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.paperSize = Worksheet.PAPERSIZE_A4
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    sheet.page_margins = PageMargins(left=0.3, right=0.3, top=0.35, bottom=0.45, header=0.15, footer=0.2)
    sheet.print_title_rows = "1:1"
    sheet.print_title_cols = "A:B"
    sheet.oddFooter.center.text = "第 &P 页 / 共 &N 页"
    sheet.oddFooter.center.size = 8
    sheet.oddFooter.center.color = "666666"
    body_font = Font(name="微软雅黑", size=10, color="000000")
    bold_font = Font(name="微软雅黑", size=10, bold=True, color="000000")
    alignments = {
        key: Alignment(horizontal=key, vertical="center") for key in ("left", "right", "center")
    }
    wrapped_text = Alignment(horizontal="left", vertical="center", wrap_text=True)
    grid_line = Side(style="thin", color="D9D9D9")
    grid_border = Border(left=grid_line, right=grid_line, top=grid_line, bottom=grid_line)

    def cells(values, *, header=False, bold=False):
        row = []
        for value in values:
            cell = WriteOnlyCell(sheet, value=value)
            if isinstance(value, str):
                # Codes and formula-like names are literal text in the file.
                cell.data_type = "s"
                cell.number_format = "@"
            else:
                cell.number_format = "#,##0;-#,##0;0" if isinstance(value, int) else "#,##0.00;-#,##0.00;0"
            cell.alignment = alignments["center" if header else "left" if isinstance(value, str) else "right"]
            cell.font = bold_font if header or bold else body_font
            cell.border = grid_border
            row.append(cell)
        return row

    def number(value):
        quantity = Decimal(str(value or 0))
        return int(quantity) if quantity == quantity.to_integral_value() else float(quantity)

    sheet.row_dimensions[1].height = 24
    sheet.append(cells([*text_headers, "期初库存", "本期入库", "本期出库", "期末库存"], header=True))
    fields = ("beginning_qty", "inbound_qty", "outbound_qty", "ending_qty")
    sums = [Decimal(0)] * 4
    for row_number, item in enumerate(result["items"], start=2):
        quantities = [Decimal(str(item[field])) for field in fields]
        sums = [total + qty for total, qty in zip(sums, quantities)]
        row_values = [
            item["product_code"] or "", item["product_name"] or "", item["color_name"] or item["color_spec"] or "",
            *([item.get(key) or "" for key in ("barcode", "color_barcode", "size_name", "size_barcode", "barcode_issue")] if barcode else []),
            *(number(qty) for qty in quantities),
        ]
        row_cells = cells(row_values)
        line_count = 1
        for index, capacity in enumerate([width - 4 for width in widths[:len(text_headers)]]):
            text = row_values[index]
            lines = 0
            for line in text.splitlines() or [""]:
                width = sum(2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1 for char in line)
                lines += max(1, (width + capacity - 1) // capacity)
            line_count = max(line_count, lines)
            row_cells[index].alignment = wrapped_text
        sheet.row_dimensions[row_number].height = min(409, max(18, line_count * 14 + 4))
        sheet.append(row_cells)
    last_data_row = 1 + len(result["items"])
    sheet.auto_filter.ref = f"A1:{get_column_letter(len(widths))}{last_data_row}"
    sheet.row_dimensions[last_data_row + 1].height = 20
    sheet.append(cells(["清单合计", *([""] * (len(text_headers) - 1)), *(number(qty) for qty in sums)], bold=True))
    sheet.print_area = f"A1:{get_column_letter(len(widths))}{last_data_row + 1}"
    return workbook
