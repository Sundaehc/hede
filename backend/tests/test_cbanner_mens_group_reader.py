from __future__ import annotations

from openpyxl import Workbook

from fileio.cbanner_mens_group_reader import read_cbanner_mens_group_map


def test_read_cbanner_mens_group_map_reads_product_detail_sheet(tmp_path):
    source_root = tmp_path / "千百度男鞋"
    workbook_dir = source_root / "2026年" / "6月份"
    workbook_dir.mkdir(parents=True)
    workbook_path = workbook_dir / "赫德货品表（千百度男鞋）6.4.xlsx"
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "商品明细表"
    worksheet.append(["标题行"])
    worksheet.append(["货号", "品名", "组别"])
    worksheet.append([" A1001 ", "男鞋", "一组"])
    worksheet.append(["A1002", "男鞋", "二组"])
    workbook.save(workbook_path)
    workbook.close()

    group_map = read_cbanner_mens_group_map(source_root)

    assert group_map == {"A1001": "一组", "A1002": "二组"}
