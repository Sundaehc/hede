\set ON_ERROR_STOP on
BEGIN;
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '10s';
SET LOCAL search_path = pg_catalog;
\ir manifest.sql

DO $review$
DECLARE
    target_function record;
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_stat_activity
        WHERE usename IN ('hede_mcp_products', 'hede_mcp_design', 'hede_mcp_control')
    ) THEN
        RAISE EXCEPTION 'Stop MCP and disconnect its database accounts before restoring PUBLIC privileges';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_temp.reviewed_mcp_functions reviewed
        JOIN pg_proc routine ON routine.oid = to_regprocedure(reviewed.signature)
        WHERE routine.proacl IS DISTINCT FROM ARRAY[
            format('%s=X/%s', routine.proowner::regrole, routine.proowner::regrole)::aclitem
        ]
    ) THEN
        RAISE EXCEPTION 'ACL changed since the reviewed revocation; refuse to overwrite later grants';
    END IF;
    FOR target_function IN SELECT signature FROM pg_temp.reviewed_mcp_functions ORDER BY signature LOOP
        EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO PUBLIC', target_function.signature);
    END LOOP;
END
$review$;
COMMIT;
