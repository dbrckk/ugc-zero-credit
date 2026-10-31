"""Bounded render admission for a single-user, CPU-only studio.

The caller must hold its jobs_lock when reading/updating jobs. A single
ThreadPoolExecutor worker processes queued jobs sequentially.
"""
MAX_ACTIVE_RENDERS = 2
ACTIVE = frozenset({"queued", "running"})

def is_active(job: dict) -> bool:
    return job.get("status") in ACTIVE

def admission(jobs: dict, project_id: str) -> str:
    """Return ok, already_running or server_busy; no state mutation."""
    if is_active(jobs.get(project_id, {})):
        return "already_running"
    if sum(is_active(job) for job in jobs.values()) >= MAX_ACTIVE_RENDERS:
        return "server_busy"
    return "ok"
