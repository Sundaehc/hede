"""Validate exact, cross-page detail selections before running an export."""
from pydantic import BaseModel, ConfigDict, Field, StrictStr
from fastapi import HTTPException


class DetailExportSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rows: list[StrictStr] = Field(min_length=1, max_length=100_000)

    def selected_rows(self, display_mode: str = "goods") -> list[str]:
        for row in self.rows:
            parts = row.split(":", 2)
            detail_id = parts[0]
            valid = (detail_id.isascii() and detail_id.isdigit() and not detail_id.startswith("0")
                     and len(detail_id) <= 19 and int(detail_id) <= 9223372036854775807)
            if display_mode == "barcode":
                valid = valid and len(parts) == 3 and parts[1] in {"0", "1"}
                if len(parts) == 3 and parts[1] == "1" and parts[2] != "":
                    valid = False
            else:
                valid = valid and len(parts) == 1
            if not valid or len(row) > 512:
                raise HTTPException(status_code=400, detail="所选明细标识无效，请重新查询后选择")
        return list(dict.fromkeys(self.rows))


def ensure_selection_complete(selected_rows: list[str], result: dict) -> None:
    if result["total"] != len(selected_rows):
        raise HTTPException(status_code=409, detail="部分已选明细已变更、删除或不再符合筛选条件，请重新查询后选择")
