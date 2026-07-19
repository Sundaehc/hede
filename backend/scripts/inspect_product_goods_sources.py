"""Inspect compact manual-field coverage across product-goods workbooks."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.import_product_goods_manual_fields import inspect_source


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    for path in args.paths:
        print(json.dumps(inspect_source(path), ensure_ascii=True))


if __name__ == "__main__":
    main()
