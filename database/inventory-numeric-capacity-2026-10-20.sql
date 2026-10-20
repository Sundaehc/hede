DO $migration$
DECLARE
    saved_views jsonb;
    saved_view jsonb;
    permission jsonb;
    column_comment jsonb;
    default_grantee record;
    migration_user text := current_user;
    old_record_node oid;
    old_detail_node oid;
BEGIN
    PERFORM set_config('lock_timeout', '3s', true);
    PERFORM set_config('statement_timeout', '30s', true);
    PERFORM set_config('search_path', 'pg_catalog', true);

    IF (SELECT count(*) FROM information_schema.columns
        WHERE table_schema = 'public'
          AND ((table_name = 'inventory_records' AND column_name IN ('total_count', 'amount'))
            OR (table_name = 'inventory_details' AND column_name IN ('quantity', 'unit_price', 'amount')))
          AND data_type = 'numeric' AND numeric_precision IN (10, 18) AND numeric_scale = 2) <> 5 THEN
        RAISE EXCEPTION '经营历程字段结构不符合预期，未执行扩容';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND ((table_name = 'inventory_records' AND column_name IN ('total_count', 'amount'))
            OR (table_name = 'inventory_details' AND column_name IN ('quantity', 'unit_price', 'amount')))
          AND numeric_precision = 10) THEN
        RETURN;
    END IF;
    IF NOT pg_try_advisory_xact_lock(42917001) THEN
        RAISE EXCEPTION '单据导入正在写入，请等待结束后再扩容';
    END IF;
    IF to_regclass('public.inventory_import_tasks') IS NOT NULL THEN
        LOCK TABLE public.inventory_import_tasks IN SHARE MODE NOWAIT;
        IF EXISTS (SELECT 1 FROM public.inventory_import_tasks WHERE status IN ('queued', 'running')) THEN
            RAISE EXCEPTION '后台导入仍在执行，请等待结束后再扩容';
        END IF;
    END IF;
    LOCK TABLE public.inventory_records, public.inventory_details IN ACCESS EXCLUSIVE MODE NOWAIT;
    SELECT relfilenode INTO old_record_node FROM pg_class WHERE oid = 'public.inventory_records'::regclass;
    SELECT relfilenode INTO old_detail_node FROM pg_class WHERE oid = 'public.inventory_details'::regclass;

    SELECT coalesce(jsonb_agg(view_snapshot ORDER BY view_snapshot->>'schema', view_snapshot->>'name'), '[]'::jsonb)
    INTO saved_views
    FROM (
        SELECT jsonb_build_object(
            'oid', view_table.oid, 'schema', namespace.nspname, 'name', view_table.relname,
            'kind', view_table.relkind, 'owner', pg_get_userbyid(view_table.relowner),
            'definition', pg_get_viewdef(view_table.oid, true),
            'options', array_to_string(view_table.reloptions, ', '),
            'comment', obj_description(view_table.oid, 'pg_class'),
            'column_comments', (SELECT coalesce(jsonb_agg(jsonb_build_object('name', attribute.attname,
                'comment', col_description(view_table.oid, attribute.attnum))), '[]'::jsonb)
                FROM pg_attribute attribute WHERE attribute.attrelid = view_table.oid
                AND attribute.attnum > 0 AND NOT attribute.attisdropped
                AND col_description(view_table.oid, attribute.attnum) IS NOT NULL),
            'column_acl', EXISTS (SELECT 1 FROM pg_attribute attribute
                WHERE attribute.attrelid = view_table.oid AND attribute.attacl IS NOT NULL),
            'permissions', (SELECT jsonb_agg(jsonb_build_object(
                'grantee', CASE WHEN acl.grantee = 0 THEN 'PUBLIC' ELSE pg_get_userbyid(acl.grantee) END,
                'grantor', pg_get_userbyid(acl.grantor), 'privilege', acl.privilege_type,
                'grantable', acl.is_grantable))
                FROM aclexplode(coalesce(view_table.relacl, acldefault('r', view_table.relowner))) acl)
        ) AS view_snapshot
        FROM pg_class view_table JOIN pg_namespace namespace ON namespace.oid = view_table.relnamespace
        WHERE view_table.oid IN (
            SELECT rewrite.ev_class FROM pg_depend dependency JOIN pg_rewrite rewrite ON rewrite.oid = dependency.objid
            WHERE dependency.classid = 'pg_rewrite'::regclass AND dependency.refclassid = 'pg_class'::regclass
              AND dependency.refobjid IN ('public.inventory_records'::regclass, 'public.inventory_details'::regclass)
              AND rewrite.ev_class <> dependency.refobjid
        )
    ) snapshots;

    FOR saved_view IN SELECT value FROM jsonb_array_elements(saved_views) LOOP
        IF saved_view->>'kind' <> 'v' OR NOT (
            (saved_view->>'schema' = 'mcp_readonly' AND saved_view->>'name' IN ('inventory_records', 'inventory_details', 'purchase_orders'))
            OR (saved_view->>'schema' = 'public' AND saved_view->>'name' = 'v_inventory_records_normalized')
        ) OR (saved_view->>'column_acl')::boolean THEN
            RAISE EXCEPTION '存在未支持的视图依赖或列级权限：%.% ，未执行扩容', saved_view->>'schema', saved_view->>'name';
        END IF;
        IF EXISTS (SELECT 1 FROM pg_depend dependency JOIN pg_rewrite rewrite ON rewrite.oid = dependency.objid
            WHERE dependency.classid = 'pg_rewrite'::regclass AND dependency.refclassid = 'pg_class'::regclass
            AND dependency.refobjid = (saved_view->>'oid')::oid AND rewrite.ev_class <> dependency.refobjid) THEN
            RAISE EXCEPTION '视图存在下游依赖，未执行扩容：%.%', saved_view->>'schema', saved_view->>'name';
        END IF;
        FOR permission IN SELECT value FROM jsonb_array_elements(saved_view->'permissions') LOOP
            IF permission->>'grantor' <> saved_view->>'owner' THEN
                RAISE EXCEPTION '视图存在非所有者授权，未执行扩容：%.%', saved_view->>'schema', saved_view->>'name';
            END IF;
        END LOOP;
    END LOOP;

    FOR saved_view IN SELECT value FROM jsonb_array_elements(saved_views) LOOP
        EXECUTE format('DROP VIEW %I.%I', saved_view->>'schema', saved_view->>'name');
    END LOOP;
    ALTER TABLE public.inventory_records
        ALTER COLUMN total_count TYPE numeric(18,2), ALTER COLUMN amount TYPE numeric(18,2);
    ALTER TABLE public.inventory_details
        ALTER COLUMN quantity TYPE numeric(18,2), ALTER COLUMN unit_price TYPE numeric(18,2),
        ALTER COLUMN amount TYPE numeric(18,2);

    IF old_record_node <> (SELECT relfilenode FROM pg_class WHERE oid = 'public.inventory_records'::regclass)
        OR old_detail_node <> (SELECT relfilenode FROM pg_class WHERE oid = 'public.inventory_details'::regclass) THEN
        RAISE EXCEPTION '数据库执行了非预期的表重写，扩容已回滚';
    END IF;
    FOR saved_view IN SELECT value FROM jsonb_array_elements(saved_views) LOOP
        EXECUTE format('CREATE VIEW %I.%I %s AS %s', saved_view->>'schema', saved_view->>'name',
            CASE WHEN coalesce(saved_view->>'options', '') = '' THEN '' ELSE format('WITH (%s)', saved_view->>'options') END,
            saved_view->>'definition');
        EXECUTE format('ALTER VIEW %I.%I OWNER TO %I', saved_view->>'schema', saved_view->>'name', saved_view->>'owner');
        EXECUTE format('SET LOCAL ROLE %I', saved_view->>'owner');
        FOR default_grantee IN
            SELECT DISTINCT acl.grantee FROM pg_class relation
            CROSS JOIN LATERAL aclexplode(coalesce(relation.relacl, acldefault('r', relation.relowner))) acl
            WHERE relation.oid = to_regclass(format('%I.%I', saved_view->>'schema', saved_view->>'name'))
              AND acl.grantee <> relation.relowner
        LOOP
            EXECUTE format('REVOKE ALL ON %I.%I FROM %s', saved_view->>'schema', saved_view->>'name',
                CASE WHEN default_grantee.grantee = 0 THEN 'PUBLIC' ELSE quote_ident(pg_get_userbyid(default_grantee.grantee)) END);
        END LOOP;
        FOR permission IN SELECT value FROM jsonb_array_elements(saved_view->'permissions') LOOP
            IF permission->>'grantee' <> saved_view->>'owner' THEN
                EXECUTE format('GRANT %s ON %I.%I TO %s%s', permission->>'privilege', saved_view->>'schema', saved_view->>'name',
                    CASE WHEN permission->>'grantee' = 'PUBLIC' THEN 'PUBLIC' ELSE quote_ident(permission->>'grantee') END,
                    CASE WHEN (permission->>'grantable')::boolean THEN ' WITH GRANT OPTION' ELSE '' END);
            END IF;
        END LOOP;
        EXECUTE format('COMMENT ON VIEW %I.%I IS %L', saved_view->>'schema', saved_view->>'name', saved_view->>'comment');
        FOR column_comment IN SELECT value FROM jsonb_array_elements(saved_view->'column_comments') LOOP
            EXECUTE format('COMMENT ON COLUMN %I.%I.%I IS %L', saved_view->>'schema', saved_view->>'name',
                column_comment->>'name', column_comment->>'comment');
        END LOOP;
        EXECUTE format('SET LOCAL ROLE %I', migration_user);
    END LOOP;
END
$migration$;
