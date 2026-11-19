from decimal import Decimal
from typing import Literal

LedgerSortKey = Literal["row_number", "date", "document_number", "summary", "increase_amount", "decrease_amount", "balance"]
LedgerSortDirection = Literal["asc", "desc"]


def sort_counterparty_ledger(ledger: dict, sort_by: LedgerSortKey, direction: LedgerSortDirection) -> dict:
    """Reorder display rows after chronological balances have been calculated."""
    numeric = sort_by in {"row_number", "increase_amount", "decrease_amount", "balance"}

    def key(item: dict):
        value = item.get(sort_by)
        return Decimal(str(value or "0")) if numeric else str(value or "").casefold()

    return {**ledger, "items": sorted(ledger.get("items", []), key=key, reverse=direction == "desc")}
