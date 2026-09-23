CREATE TEMP TABLE reviewed_mcp_functions (
    signature text PRIMARY KEY,
    definition_md5 text NOT NULL
) ON COMMIT DROP;

INSERT INTO reviewed_mcp_functions VALUES
('public.gin_extract_query_trgm(text,internal,smallint,internal,internal,internal,internal)', '908112f5743e0dc3307ce7da24a3d095'),
('public.gin_extract_value_trgm(text,internal)', '42bc3d69fe7ae6ba4409315e68686e93'),
('public.gin_trgm_consistent(internal,smallint,text,integer,internal,internal,internal,internal)', '3b5516ee327d210cf276d0f7cbec6a1b'),
('public.gin_trgm_triconsistent(internal,smallint,text,integer,internal,internal,internal)', 'ebb9557e4d7f2342aa65aa319bf2f6ad'),
('public.gtrgm_compress(internal)', '0ac3144cfd060482fab5339fe0e2a9e1'),
('public.gtrgm_consistent(internal,text,smallint,oid,internal)', '00d55f7471e62f08ca85d8d4e61991e7'),
('public.gtrgm_decompress(internal)', '217b0af3efb9f430e911c6e2aeb0aa99'),
('public.gtrgm_distance(internal,text,smallint,oid,internal)', '374c53a6404b5daf685b2c4222c76a54'),
('public.gtrgm_in(cstring)', '193067f7484db5f8d7995e7d69d563b0'),
('public.gtrgm_options(internal)', '18b083f2c473ca71bc90b18732d82493'),
('public.gtrgm_out(public.gtrgm)', 'a9d539b1258986ddb03f20181228d7e8'),
('public.gtrgm_penalty(internal,internal,internal)', '4f0a4190629a524609fe1b21fc480341'),
('public.gtrgm_picksplit(internal,internal)', '366a79f83941d97999f208690619b79d'),
('public.gtrgm_same(public.gtrgm,public.gtrgm,internal)', 'f4cc5578236bf6accefb8a772a2112da'),
('public.gtrgm_union(internal,internal)', 'b0ed52e23500e2c4e55743396994daf5'),
('public.hede_link_purchase_order_detail_product()', '3afbd308593ea36ccb5a1d1669004bc4'),
('public.hede_refresh_document_product_links()', 'ceb206c09e3119073039b7921ae60869'),
('public.hede_replace_purchase_product_cache(json,text,text,text,text)', '97d20c1ea949c9586379bd4e82c5ec9b'),
('public.hede_sync_product_archive_identity()', '978862128b7dab300d6e5058499449b5'),
('public.reject_cold_partition_write()', 'c4bb4546c376d18e5ef9724a63b04453'),
('public.set_limit(real)', 'c30ba59e63bc3cb36608046c50620e39'),
('public.show_limit()', '4be49f417a851b1848da525e573e408d'),
('public.show_trgm(text)', '42aa0974abb454971132812dcce06cac'),
('public.similarity(text,text)', 'fd931cb85ba442355f277550b8836710'),
('public.similarity_dist(text,text)', '831e333ae2231e3fb1e6e88a55ccc0a0'),
('public.similarity_op(text,text)', 'c62f80a7a7107d232daf8683decbfaf5'),
('public.smiley_copy_set_updated_at()', '4bf4e7e337b4f4aa6a689b61a5215c33'),
('public.strict_word_similarity(text,text)', '523450d477b4e105989795603c58761a'),
('public.strict_word_similarity_commutator_op(text,text)', '49fe0d7b5f628c2f13e21ad6d0c5d28f'),
('public.strict_word_similarity_dist_commutator_op(text,text)', 'e4384ee3a07267eb13f09bb4b042f334'),
('public.strict_word_similarity_dist_op(text,text)', 'bc660db5cc387e8821747f1ecfb347eb'),
('public.strict_word_similarity_op(text,text)', 'fa21d1ae2c217ba161bb3f7777e5e020'),
('public.word_similarity(text,text)', 'f9acfb3b071c96db4b1bb593b621c747'),
('public.word_similarity_commutator_op(text,text)', '98ece0ccacd71230bea0e7805d310670'),
('public.word_similarity_dist_commutator_op(text,text)', 'db36854b61d077b4cb945606bab01fc6'),
('public.word_similarity_dist_op(text,text)', 'ab0c2cb7ec6c0cbe0937ec3288d2cfda'),
('public.word_similarity_op(text,text)', '9cb3bc9ce246a2c4c4d17c7205f4a17f');

DO $review$
BEGIN
    IF current_user <> 'postgres' OR NOT (SELECT rolsuper FROM pg_roles WHERE rolname = current_user) THEN
        RAISE EXCEPTION 'Reviewed deployment requires the postgres administrator';
    END IF;
    IF (SELECT extversion FROM pg_extension WHERE extname = 'pg_trgm') IS DISTINCT FROM '1.6' THEN
        RAISE EXCEPTION 'pg_trgm version changed; repeat permission review';
    END IF;
    IF (SELECT count(*) FROM pg_temp.reviewed_mcp_functions) <> 37 OR EXISTS (
        SELECT 1 FROM pg_temp.reviewed_mcp_functions reviewed
        LEFT JOIN pg_proc routine ON routine.oid = to_regprocedure(reviewed.signature)
        WHERE routine.oid IS NULL
            OR pg_get_userbyid(routine.proowner) <> 'postgres'
            OR routine.prosecdef
            OR md5(pg_get_functiondef(routine.oid)) <> reviewed.definition_md5
    ) THEN
        RAISE EXCEPTION 'Reviewed function definition, owner or security mode changed; stop and re-audit';
    END IF;
END
$review$;
