from fastapi import HTTPException


def raise_product_import_errors(errors: list[dict[str, object]], *, message: str | None = None) -> None:
    """Keep every invalid source row, including repeated codes in different documents."""
    if not errors:
        return
    errors.sort(key=lambda error: (int(error.get("row_number") or 0), str(error.get("brand") or "")))
    raise HTTPException(status_code=400, detail={
        "code": "product_validation",
        "message": message or f"发现 {len(errors)} 条商品资料错误。请联系商品部维护商品信息档案后重新预检查；本次未导入任何数据。",
        "total": len(errors),
        "errors": errors,
    })
