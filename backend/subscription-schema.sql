CREATE TABLE IF NOT EXISTS subscription_bridges (
    provider text PRIMARY KEY,
    connected boolean NOT NULL DEFAULT false,
    note text NOT NULL DEFAULT '',
    seen_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS portal_maintenance (
    name text PRIMARY KEY,
    last_slot timestamptz NOT NULL,
    last_run_at timestamptz,
    deleted_tasks integer NOT NULL DEFAULT 0
);
ALTER TABLE answers ADD COLUMN IF NOT EXISTS source_url text;
CREATE TABLE IF NOT EXISTS subscription_claims (
    task_id uuid PRIMARY KEY REFERENCES tasks(id) ON DELETE CASCADE,
    runner_id uuid NOT NULL,
    claimed_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS answer_claims (
    task_id uuid NOT NULL,
    provider text NOT NULL,
    runner_id uuid NOT NULL,
    claimed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(task_id,provider),
    FOREIGN KEY(task_id,provider) REFERENCES answers(task_id,provider) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS browser_dispatches (
    task_id uuid PRIMARY KEY REFERENCES tasks(id) ON DELETE CASCADE,
    dispatch_id uuid UNIQUE NOT NULL,
    runner_id uuid NOT NULL,
    status text NOT NULL DEFAULT 'pending',
    submitted jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now()
);
