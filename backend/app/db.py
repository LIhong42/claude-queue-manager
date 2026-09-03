import sqlite3
import shutil
from datetime import datetime, timezone
from pathlib import Path
from .config import settings

def now():
    return datetime.now(timezone.utc).isoformat()

def connect():
    c = sqlite3.connect(settings.db_path, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=30000")
    return c

def init_db():
    with connect() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            prompt TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            workspace TEXT NOT NULL,
            log_file TEXT NOT NULL,
            pid INTEGER,
            retry_count INTEGER NOT NULL DEFAULT 0,
            max_retries INTEGER NOT NULL DEFAULT 2,
            exit_code INTEGER,
            created_at TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT,
            error TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_tasks_status_created ON tasks(status, created_at);
        """)
        c.execute("UPDATE tasks SET status='PENDING', pid=NULL, started_at=NULL WHERE status='RUNNING'")

def insert_task(task):
    with connect() as c:
        c.execute(
            "INSERT INTO tasks(id,prompt,status,workspace,log_file,max_retries,created_at) VALUES(?,?,?,?,?,?,?)",
            (task["id"], task["prompt"], "PENDING", task["workspace"], task["log_file"], task["max_retries"], now())
        )

def get_task(task_id):
    with connect() as c:
        row = c.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        return dict(row) if row else None

def list_tasks():
    with connect() as c:
        return [dict(r) for r in c.execute("SELECT * FROM tasks ORDER BY created_at DESC").fetchall()]

def claim_task():
    with connect() as c:
        c.execute("BEGIN IMMEDIATE")
        row = c.execute("SELECT * FROM tasks WHERE status='PENDING' ORDER BY created_at ASC LIMIT 1").fetchone()
        if not row:
            c.commit()
            return None
        task_id = row["id"]
        c.execute(
            "UPDATE tasks SET status='RUNNING', started_at=?, pid=NULL WHERE id=? AND status='PENDING'",
            (now(), task_id)
        )
        c.commit()
        row = c.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        return dict(row)

def set_pid(task_id, pid):
    with connect() as c:
        c.execute("UPDATE tasks SET pid=? WHERE id=?", (pid, task_id))

def finish_task(task_id, status, exit_code=None, error=None):
    with connect() as c:
        c.execute(
            "UPDATE tasks SET status=?,exit_code=?,error=?,finished_at=?,pid=NULL WHERE id=?",
            (status, exit_code, error, now(), task_id)
        )

def retry_task(task_id):
    with connect() as c:
        cur = c.execute(
            "UPDATE tasks SET status='PENDING',retry_count=retry_count+1,pid=NULL,exit_code=NULL,error=NULL,started_at=NULL,finished_at=NULL WHERE id=? AND status='FAILED'",
            (task_id,)
        )
        return cur.rowcount > 0

def cancel_task(task_id):
    with connect() as c:
        cur = c.execute(
            "UPDATE tasks SET status='CANCELLED',finished_at=?,error='Cancelled by user' WHERE id=? AND status='PENDING'",
            (now(), task_id)
        )
        return cur.rowcount > 0

def mark_retry_or_failed(task):
    with connect() as c:
        if task["retry_count"] < task["max_retries"]:
            c.execute(
                "UPDATE tasks SET status='PENDING',retry_count=retry_count+1,pid=NULL,error=?,started_at=NULL WHERE id=?",
                ("Automatic retry", task["id"])
            )
            return "PENDING"
        c.execute("UPDATE tasks SET status='FAILED',pid=NULL,finished_at=? WHERE id=?", (now(), task["id"]))
        return "FAILED"

def delete_task(task_id):
    task = get_task(task_id)
    if not task:
        return False

    # Cleanup workspace directory
    workspace = Path(task["workspace"])
    if workspace.exists():
        shutil.rmtree(workspace, ignore_errors=True)

    # Cleanup log file
    log_file = Path(task["log_file"])
    if log_file.exists():
        log_file.unlink()

    with connect() as c:
        cur = c.execute("DELETE FROM tasks WHERE id=?", (task_id,))
        return cur.rowcount > 0
