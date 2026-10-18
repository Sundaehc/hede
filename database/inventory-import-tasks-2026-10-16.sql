CREATE TABLE IF NOT EXISTS public.inventory_import_tasks (
    id TEXT PRIMARY KEY,
    request_hash TEXT NOT NULL,
    user_id BIGINT,
    filename TEXT NOT NULL,
    status TEXT NOT NULL,
    result JSON,
    error TEXT,
    error_status INTEGER,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    heartbeat_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    finished_at TIMESTAMPTZ
);

