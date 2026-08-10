CREATE TABLE IF NOT EXISTS workers (
    id VARCHAR(100) PRIMARY KEY,
    worker_type VARCHAR(50) NOT NULL,
    hostname VARCHAR(255),
    endpoint TEXT,
    status VARCHAR(50) NOT NULL DEFAULT 'idle',
    gpu VARCHAR(255),
    vram INTEGER,
    capabilities JSONB NOT NULL DEFAULT '[]'::jsonb,
    models JSONB NOT NULL DEFAULT '[]'::jsonb,
    gpu_info JSONB NOT NULL DEFAULT '{}'::jsonb,
    current_job VARCHAR(100),
    last_heartbeat TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS jobs (
    id VARCHAR(100) PRIMARY KEY,
    project_id VARCHAR(100),
    episode_id VARCHAR(100),
    scene_id VARCHAR(100),
    worker_id VARCHAR(100) REFERENCES workers(id) ON DELETE SET NULL,
    worker_type VARCHAR(50),
    job_type VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'queued',
    priority INTEGER NOT NULL DEFAULT 5,
    attempt INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    payload JSONB NOT NULL,
    progress DOUBLE PRECISION,
    result JSONB,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_workers_last_heartbeat ON workers(last_heartbeat);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_worker_type_status ON jobs(worker_type, status);
CREATE INDEX IF NOT EXISTS idx_jobs_queue_pick ON jobs(worker_type, status, priority, created_at);
