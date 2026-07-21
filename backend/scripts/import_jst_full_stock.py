"""Replace the JST full inventory table from the daily inventory workbook."""

from __future__ import annotations

from config import load_settings
from storage.vip_repository import VipRepository


def main() -> None:
    settings = load_settings(require_database=True)
    assert settings.database_url is not None
    assert settings.jst_full_stock_file is not None

    source_file = settings.jst_full_stock_file
    if not source_file.exists():
        raise FileNotFoundError(f"聚水潭库存文件不存在: {source_file}")

    result = VipRepository(settings.database_url).import_full_stock(source_file)
    print(result["message"])


if __name__ == "__main__":
    main()
