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
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname NOT LIKE 'pg\_%' ESCAPE '\' AND rolname <> 'postgres') THEN
        RAISE EXCEPTION 'Additional non-system roles exist; review their dependencies first';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname IN ('mcp_private', 'mcp_readonly')) THEN
        RAISE EXCEPTION 'MCP is already initialized; do not reuse this first-deployment script';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_proc routine JOIN pg_namespace space ON space.oid = routine.pronamespace
        WHERE space.nspname NOT IN ('pg_catalog', 'information_schema') AND EXISTS (
            SELECT 1 FROM aclexplode(COALESCE(routine.proacl, acldefault('f', routine.proowner))) permission
            WHERE permission.grantee = 0 AND permission.privilege_type = 'EXECUTE'
        ) AND NOT EXISTS (
            SELECT 1 FROM pg_temp.reviewed_mcp_functions reviewed
            WHERE to_regprocedure(reviewed.signature) = routine.oid
        )
    ) THEN
        RAISE EXCEPTION 'An additional PUBLIC-executable routine requires review';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_temp.reviewed_mcp_functions reviewed
        JOIN pg_proc routine ON routine.oid = to_regprocedure(reviewed.signature)
        WHERE routine.proacl IS NOT NULL
    ) THEN
        RAISE EXCEPTION 'Function ACL differs from the reviewed default-ACL snapshot';
    END IF;
    FOR target_function IN SELECT signature FROM pg_temp.reviewed_mcp_functions ORDER BY signature LOOP
        EXECUTE format('REVOKE EXECUTE ON FUNCTION %s FROM PUBLIC RESTRICT', target_function.signature);
    END LOOP;
    IF EXISTS (
        SELECT 1 FROM pg_temp.reviewed_mcp_functions reviewed
        JOIN pg_proc routine ON routine.oid = to_regprocedure(reviewed.signature)
        CROSS JOIN LATERAL aclexplode(COALESCE(routine.proacl, acldefault('f', routine.proowner))) permission
        WHERE permission.grantee = 0 AND permission.privilege_type = 'EXECUTE'
    ) THEN
        RAISE EXCEPTION 'Function privilege postcheck failed';
    END IF;
END
$review$;
COMMIT;
