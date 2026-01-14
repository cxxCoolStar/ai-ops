import os
import sqlite3
import time
import uuid


class TraceStore:
    def __init__(self, db_path):
        self.db_path = os.path.abspath(db_path)
        self._init_db()

    def new_trace_id(self):
        return str(uuid.uuid4())

    def create_trace(self, trace_id, repo_url, code_host, error_signature, error_excerpt):
        now = int(time.time())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO traces(trace_id, created_at, repo_url, code_host, error_signature, error_excerpt, status)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trace_id,
                    now,
                    repo_url,
                    code_host,
                    error_signature,
                    error_excerpt,
                    "RUNNING",
                ),
            )

    def finish_trace_ok(self, trace_id, mr_url, commit_sha):
        now = int(time.time())
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE traces
                SET finished_at=?, status=?, mr_url=?, commit_sha=?
                WHERE trace_id=?
                """,
                (now, "DONE", mr_url, commit_sha, trace_id),
            )

    def finish_trace_fail(self, trace_id, failure_step, failure_message):
        now = int(time.time())
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE traces
                SET finished_at=?, status=?, failure_step=?, failure_message=?
                WHERE trace_id=?
                """,
                (now, "FAILED", failure_step, failure_message, trace_id),
            )

    def start_step(self, trace_id, step_name, message=""):
        now = int(time.time())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO steps(trace_id, step_name, started_at, status, message)
                VALUES(?, ?, ?, ?, ?)
                """,
                (trace_id, step_name, now, "RUNNING", message[:2000]),
            )

    def finish_step_ok(self, trace_id, step_name, message=""):
        now = int(time.time())
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE steps
                SET finished_at=?, status=?, message=?
                WHERE trace_id=? AND step_name=? AND status='RUNNING'
                """,
                (now, "OK", message[:2000], trace_id, step_name),
            )

    def finish_step_fail(self, trace_id, step_name, message):
        now = int(time.time())
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE steps
                SET finished_at=?, status=?, message=?
                WHERE trace_id=? AND step_name=? AND status='RUNNING'
                """,
                (now, "FAIL", (message or "")[:2000], trace_id, step_name),
            )

    def get_trace(self, trace_id):
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT trace_id, created_at, finished_at, repo_url, code_host,
                       error_signature, status, failure_step, failure_message, mr_url, commit_sha
                FROM traces WHERE trace_id=?
                """,
                (trace_id,),
            ).fetchone()
        if not row:
            return None
        keys = [
            "trace_id",
            "created_at",
            "finished_at",
            "repo_url",
            "code_host",
            "error_signature",
            "status",
            "failure_step",
            "failure_message",
            "mr_url",
            "commit_sha",
        ]
        return dict(zip(keys, row))

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _init_db(self):
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS traces(
                    trace_id TEXT PRIMARY KEY,
                    created_at INTEGER NOT NULL,
                    finished_at INTEGER,
                    repo_url TEXT NOT NULL,
                    code_host TEXT NOT NULL,
                    error_signature TEXT,
                    error_excerpt TEXT,
                    status TEXT NOT NULL,
                    failure_step TEXT,
                    failure_message TEXT,
                    mr_url TEXT,
                    commit_sha TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS steps(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trace_id TEXT NOT NULL,
                    step_name TEXT NOT NULL,
                    started_at INTEGER NOT NULL,
                    finished_at INTEGER,
                    status TEXT NOT NULL,
                    message TEXT,
                    FOREIGN KEY(trace_id) REFERENCES traces(trace_id)
                )
                """
            )


class StepScope:
    def __init__(self, store, trace_id, step_name, message=""):
        self.store = store
        self.trace_id = trace_id
        self.step_name = step_name
        self.message = message

    def __enter__(self):
        self.store.start_step(self.trace_id, self.step_name, self.message)
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc is None:
            self.store.finish_step_ok(self.trace_id, self.step_name, self.message)
            return False
        self.store.finish_step_fail(self.trace_id, self.step_name, str(exc))
        return False

