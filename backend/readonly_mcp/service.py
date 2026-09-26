import hashlib
import json
import time
from uuid import uuid4

from mcp.server.mcpserver.exceptions import ToolError

from readonly_mcp.catalog import allowed_datasets, describe
from readonly_mcp.sql_policy import validate_query


AUDIT_RESULT_COLUMNS = {
    "brand", "id", "sku", "original_sku", "product_id", "source_product_id",
    "product_name", "color", "size", "size_name", "document_number",
}


def audit_parameter_types(params):
    if not isinstance(params, dict):
        return None
    values = {
        name: {
            "type": type(value).__name__,
            "length": len(value) if isinstance(value, str) else None,
        }
        for name, value in sorted(params.items())
    }
    return json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def audit_result_summary(result):
    if not isinstance(result, dict):
        return None
    columns = result.get("columns")
    rows = result.get("rows")
    if not isinstance(columns, list) or not isinstance(rows, list):
        return None
    selected = [(index, str(column)) for index, column in enumerate(columns)
                if str(column).lower() in AUDIT_RESULT_COLUMNS]
    if not selected:
        return None
    summary = {
        "columns": [column for _, column in selected],
        "rows": [[row[index] if index < len(row) else None for index, _ in selected] for row in rows],
        "truncated": bool(result.get("truncated")),
    }
    encoded = json.dumps(summary, ensure_ascii=False, separators=(",", ":"))
    while len(encoded.encode("utf-8")) > 65536 and summary["rows"]:
        summary["rows"].pop()
        summary["truncated"] = True
        encoded = json.dumps(summary, ensure_ascii=False, separators=(",", ":"))
    return encoded


class QueryService:
    def __init__(self, control, executor):
        self.control = control
        self.executor = executor

    def invoke(self, principal: dict, tool: str, *, dataset: str = "", sql: str = "", params: dict | None = None) -> dict:
        request_id = uuid4().hex
        sql_hash = hashlib.sha256(sql.encode()).hexdigest() if tool == "query_readonly" else None
        query_sql = sql.strip() if tool == "query_readonly" and isinstance(sql, str) else None
        query_params = audit_parameter_types(params) if tool == "query_readonly" else None
        datasets = (dataset,) if tool == "describe_dataset" and dataset else ()
        result_summary = None
        started = time.monotonic()
        try:
            self.control.audit(request_id, principal, tool, sql_hash, "started", 0, 0, datasets, query_sql, query_params, result_summary)
        except Exception:
            raise ToolError("审计服务不可用，本次查询未执行") from None
        status = "failed"
        row_count = 0
        try:
            if tool == "list_datasets":
                result = {"datasets": [{"name": name, "description": value["description"]} for name, value in allowed_datasets(principal).items()]}
            elif tool == "describe_dataset":
                result = describe(dataset, principal)
            else:
                validated = validate_query(sql, params, principal)
                datasets = validated.datasets
                result = self.executor.execute(principal["profile"], validated)
                row_count = result["row_count"]
                result_summary = audit_result_summary(result)
            status = "completed"
            return {"request_id": request_id, **result}
        except ValueError as error:
            status = "rejected"
            raise ToolError(str(error)) from None
        except Exception:
            raise ToolError(f"查询失败或超时，请缩小范围后重试；审计编号：{request_id}") from None
        finally:
            try:
                self.control.audit(request_id, principal, tool, sql_hash, status, row_count, int((time.monotonic() - started) * 1000), datasets, query_sql, query_params, result_summary)
            except Exception:
                raise ToolError(f"审计记录失败，结果不予返回；审计编号：{request_id}") from None
