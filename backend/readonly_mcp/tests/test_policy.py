import pytest

from readonly_mcp.sql_policy import validate_query


@pytest.mark.parametrize("sql,params", [
    ("SELECT * FROM products WHERE sku=:sku", {"sku": "ABC'; DROP TABLE products; --"}),
    ("SELECT brand, COUNT(*) AS total FROM products GROUP BY brand ORDER BY total DESC", {}),
    ("WITH recent AS (SELECT id, sku FROM products) SELECT * FROM recent LIMIT 10 OFFSET 1", {}),
    ("SELECT p.sku,h.content FROM products p JOIN copywriting_history h ON p.id=h.product_id AND p.brand=h.brand", {}),
    ("SELECT sku FROM products WHERE replace(trim(launch_date), '/', '-') >= CAST(CURRENT_DATE - INTERVAL '2 days' AS TEXT)", {}),
    ("SELECT COALESCE(color,'未知'), MAX(id), MIN(id) FROM products GROUP BY color", {}),
    ("SELECT sku FROM products UNION SELECT sku FROM products", {}),
    ("SELECT sku FROM products WHERE sku LIKE :pattern OR color=:color", {"pattern": "%abc%", "color": "棕色"}),
])
def test_authorized_queries_compile_to_explicit_safe_schema(sql, params):
    result = validate_query(sql, params, {"profile": "design"})
    assert '"mcp_readonly"."products"' in result.sql
    assert "DROP TABLE" not in result.sql
    assert set(result.datasets) <= {"products", "copywriting_history"}
    assert len(result.parameters) >= len(params)


@pytest.mark.parametrize("sql", [
    "SELECT * FROM auth_users", "SELECT * FROM public.products", "SELECT * FROM pg_catalog.pg_roles",
    "SELECT cost FROM products", "SELECT raw_payload FROM products", "SELECT image_path FROM products",
    "SELECT snapshot FROM copywriting_history", "SELECT system_prompt FROM copywriting",
    "DELETE FROM products", "UPDATE products SET sku='x'", "INSERT INTO products SELECT * FROM products",
    "DROP TABLE products", "ALTER ROLE hede_mcp_products SUPERUSER", "SET ROLE postgres",
    "COPY products TO '/tmp/private'", "SELECT * INTO temporary_output FROM products",
    "SELECT * FROM products; SELECT * FROM products", "SELECT * FROM products FOR UPDATE",
    "SELECT pg_sleep(100) FROM products", "SELECT pg_read_file('/etc/passwd') FROM products",
    "SELECT set_config('default_transaction_read_only','off',false) FROM products",
    "SELECT public.dangerous(sku) FROM products", "SELECT dblink('private','delete') FROM products",
    "SELECT * FROM generate_series(1,100000000)", "SELECT CAST(sku AS regclass) FROM products",
    "WITH deleted AS (DELETE FROM products RETURNING *) SELECT * FROM deleted",
    "WITH RECURSIVE counter AS (SELECT * FROM products UNION ALL SELECT * FROM counter) SELECT * FROM counter",
    "SELECT * FROM products CROSS JOIN products x", "SELECT * FROM products, products x",
    "SELECT (SELECT password_hash FROM auth_users) FROM products", "SELECT pg_catalog.version() FROM products",
    "WITH products AS (SELECT * FROM auth_users) SELECT * FROM products", "SELECT * FROM ONLY products",
    "SELECT * FROM products TABLESAMPLE SYSTEM (1)", "SELECT * FROM products WHERE sku ~ '(a+)+$'",
    "SELECT current_user FROM products", "SELECT 1", "SELECT * FROM products WHERE id=$1",
    "SELECT * FROM products WHERE id=%s", "SELECT length(pg_read_file('/etc/passwd')) FROM products",
])
def test_rejects_unsafe_or_unapproved_sql(sql):
    with pytest.raises(ValueError):
        validate_query(sql, {}, {"profile": "design"})


def test_product_profile_cannot_access_copywriting_even_inside_cte():
    with pytest.raises(ValueError):
        validate_query("WITH hidden AS (SELECT * FROM copywriting_history) SELECT * FROM hidden", {}, {"profile": "products"})


@pytest.mark.parametrize("sql,params", [
    ("SELECT * FROM products WHERE sku=:sku", {}),
    ("SELECT * FROM products", {"unused": 1}),
    ("SELECT * FROM products WHERE sku=:sku", {"sku": ["ABC"]}),
    ("SELECT * FROM products WHERE sku=:sku", {"sku": "x" * 10001}),
    ("SELECT * FROM products WHERE id=:id", {"id": float('nan')}),
    ("SELECT * FROM products WHERE id=:id", {"id": float('inf')}),
])
def test_rejects_mismatched_or_unbounded_parameters(sql, params):
    with pytest.raises(ValueError):
        validate_query(sql, params, {"profile": "products"})


def test_literal_percent_and_named_parameter_are_not_confused():
    result = validate_query("SELECT sku FROM products WHERE sku LIKE '%M%' AND color=:color", {"color": "棕色"}, {"profile": "products"})
    assert "'%M%'" in result.sql
    assert "$1" in result.sql
    assert result.parameters == ("棕色",)
