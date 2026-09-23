import math
import re
from dataclasses import dataclass

from sqlglot import exp, parse
from sqlglot.optimizer.qualify import qualify
from sqlglot.optimizer.scope import traverse_scope

from readonly_mcp.catalog import allowed_datasets


ALLOWED_NODES = frozenset("""
Select Union Intersect Except Subquery With CTE Table TableAlias Identifier Column Star
From Join Where Group Having Order Ordered Limit Offset Distinct Alias Paren
Literal Null Boolean Placeholder And Or Not EQ NEQ GT GTE LT LTE Is In Between Like ILike
Add Sub Mul Div Mod Neg Case If Cast DataType Count Sum Avg Min Max Coalesce Nullif
Lower Upper Trim Length Round Abs Replace CurrentDate CurrentTimestamp Interval Var
""".split())
ALLOWED_TYPES = frozenset({"TEXT", "VARCHAR", "BIGINT", "INT", "SMALLINT", "DECIMAL", "NUMERIC", "DOUBLE", "FLOAT", "BOOLEAN", "DATE", "TIMESTAMP", "TIMESTAMPTZ"})


@dataclass(frozen=True)
class ValidatedQuery:
    sql: str
    parameters: tuple
    datasets: tuple[str, ...]


def validate_query(sql: str, params: dict | None, principal: dict) -> ValidatedQuery:
    if not isinstance(sql, str) or not sql.strip() or len(sql) > 20000:
        raise ValueError("SQL不能为空且不能超过20000字")
    params = {} if params is None else params
    if not isinstance(params, dict) or len(params) > 100:
        raise ValueError("params必须是最多100项的命名参数对象")
    for name, value in params.items():
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", name):
            raise ValueError("参数名称无效")
        if type(value) not in (str, int, float, bool, type(None)) or isinstance(value, str) and len(value) > 10000:
            raise ValueError("参数只支持有限长度文本、数字、布尔值和null")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("参数不能包含无限数或NaN")
    try:
        statements = parse(sql, dialect="postgres")
    except Exception:
        raise ValueError("SQL解析失败，请使用PostgreSQL只读查询语法") from None
    if len(statements) != 1 or not isinstance(statements[0], (exp.Select, exp.Union, exp.Intersect, exp.Except)):
        raise ValueError("只允许单条SELECT或集合查询，不允许写入或管理命令")
    tree = statements[0]
    nodes = list(tree.walk())
    if len(nodes) > 800:
        raise ValueError("SQL过于复杂，请简化查询")
    for node in nodes:
        if type(node).__name__ not in ALLOWED_NODES:
            raise ValueError("SQL包含不支持或未经授权的语法、函数或操作")
        if isinstance(node, exp.With) and node.args.get("recursive"):
            raise ValueError("不允许递归查询")
        if isinstance(node, exp.Table) and (node.db or node.catalog or node.args.get("only") or not isinstance(node.this, exp.Identifier)):
            raise ValueError("只允许未限定schema的授权数据集名称")
        if isinstance(node, exp.Column) and (node.db or node.catalog):
            raise ValueError("不允许访问其他schema")
        if isinstance(node, exp.DataType) and node.this.value not in ALLOWED_TYPES:
            raise ValueError("不允许转换为此类型")
        if isinstance(node, exp.Join) and (str(node.args.get("kind", "")).upper() in {"CROSS", "SEMI", "ANTI"} or not (node.args.get("on") or node.args.get("using"))):
            raise ValueError("关联必须明确提供ON或USING条件")
    placeholders = list(tree.find_all(exp.Placeholder))
    if any(not isinstance(node.this, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", node.this) for node in placeholders):
        raise ValueError("仅支持:name命名参数")
    names = {node.this for node in placeholders}
    if names != set(params):
        raise ValueError("SQL参数与params键名不一致")
    catalog = allowed_datasets(principal)
    physical_tables = []
    try:
        for scope in traverse_scope(tree):
            for source in scope.sources.values():
                if isinstance(source, exp.Table):
                    if source.name not in catalog:
                        raise ValueError("数据集不存在或没有权限")
                    physical_tables.append(source)
        if not physical_tables or len(physical_tables) > 8:
            raise ValueError("查询必须引用授权数据集且最多8个表引用")
        tree = qualify(tree, dialect="postgres", schema={name: dataset["columns"] for name, dataset in catalog.items()}, infer_schema=False)
    except ValueError:
        raise
    except Exception:
        raise ValueError("字段不存在、字段歧义或SQL不符合授权数据结构") from None
    datasets = set()
    for scope in traverse_scope(tree):
        for source in scope.sources.values():
            if isinstance(source, exp.Table):
                datasets.add(source.name)
                source.set("db", exp.to_identifier("mcp_readonly", quoted=True))
    parameter_order = []
    for node in list(tree.find_all(exp.Placeholder)):
        parameter_order.append(params[node.this])
        node.replace(exp.Parameter(this=exp.Literal.number(len(parameter_order))))
    return ValidatedQuery(tree.sql(dialect="postgres"), tuple(parameter_order), tuple(sorted(datasets)))
