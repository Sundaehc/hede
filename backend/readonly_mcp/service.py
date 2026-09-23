import hashlib
import time
from uuid import uuid4

from mcp.server.mcpserver.exceptions import ToolError

from readonly_mcp.catalog import allowed_datasets, describe
from readonly_mcp.sql_policy import validate_query


class QueryService:
    def __init__(self, control, executor):
        self.control = control
        self.executor = executor

    def invoke(self, principal: dict, tool: str, *, dataset: str = "", sql: str = "", params: dict | None = None) -> dict:
        request_id = uuid4().hex
        sql_hash = hashlib.sha256(sql.encode()).hexdigest() if tool == "query_readonly" else None
        started = time.monotonic()
        try:
            self.control.audit(request_id, principal, tool, sql_hash, "started")
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
                result = self.executor.execute(principal["profile"], validated)
                row_count = result["row_count"]
            status = "completed"
            return {"request_id": request_id, **result}
        except ValueError as error:
            status = "rejected"
            raise ToolError(str(error)) from None
        except Exception:
            raise ToolError(f"查询失败或超时，请缩小范围后重试；审计编号：{request_id}") from None
        finally:
            try:
                self.control.audit(request_id, principal, tool, sql_hash, status, row_count, int((time.monotonic() - started) * 1000))
            except Exception:
                raise ToolError(f"审计记录失败，结果不予返回；审计编号：{request_id}") from None
