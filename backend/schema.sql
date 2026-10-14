CREATE TABLE IF NOT EXISTS tasks (
    id uuid PRIMARY KEY,
    request_key uuid UNIQUE NOT NULL,
    prompt text NOT NULL,
    mode text NOT NULL CHECK (mode IN ('demo', 'live')),
    status text NOT NULL DEFAULT 'queued',
    cancel_requested boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    finished_at timestamptz,
    heartbeat_at timestamptz
);
CREATE TABLE IF NOT EXISTS answers (
    task_id uuid NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    provider text NOT NULL,
    model text NOT NULL,
    actual_model text,
    status text NOT NULL DEFAULT 'queued',
    content text NOT NULL DEFAULT '',
    error text,
    started_at timestamptz,
    finished_at timestamptz,
    input_tokens integer,
    output_tokens integer,
    cached_tokens integer,
    cache_write_tokens integer,
    usage_complete boolean NOT NULL DEFAULT false,
    cost_usd numeric(18, 10),
    cost_status text NOT NULL DEFAULT 'pending',
    rates jsonb NOT NULL DEFAULT '{}',
    rates_date text NOT NULL DEFAULT '',
    rates_model text NOT NULL DEFAULT '',
    finish_reason text,
    PRIMARY KEY (task_id, provider)
);
CREATE INDEX IF NOT EXISTS tasks_created_idx ON tasks(created_at DESC);
CREATE INDEX IF NOT EXISTS tasks_status_idx ON tasks(status);
