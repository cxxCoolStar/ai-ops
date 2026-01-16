import os
import re
import hashlib
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
                       error_signature, error_excerpt, status, failure_step, failure_message, mr_url, commit_sha
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
            "error_excerpt",
            "status",
            "failure_step",
            "failure_message",
            "mr_url",
            "commit_sha",
        ]
        return dict(zip(keys, row))

    def list_steps(self, trace_id):
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT step_name, started_at, finished_at, status, message
                FROM steps
                WHERE trace_id=?
                ORDER BY started_at ASC, id ASC
                """,
                (trace_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def search_similar_cases(self, repo_url, query_text, limit=5):
        repo_url = (repo_url or "").strip()
        query_text = (query_text or "").strip()
        if not repo_url or not query_text:
            return []

        features = self._extract_query_features(query_text)
        signature = features.get("signature") or ""
        normalized_query = features.get("normalized_query") or ""
        exception_type = features.get("exception_type") or ""

        with self._connect() as conn:
            if signature:
                rows = conn.execute(
                    """
                    SELECT case_id, signature, exception_type, message_key, top_frames, quality_score, status, updated_at
                    FROM bug_cases
                    WHERE repo_url=? AND signature=?
                    ORDER BY quality_score DESC, updated_at DESC
                    LIMIT ?
                    """,
                    (repo_url, signature, int(limit)),
                ).fetchall()
                if rows:
                    return [self._row_to_case(r) for r in rows]

            tokens = self._fts_query_tokens(exception_type, normalized_query)
            if not tokens:
                return []
            match = " ".join(tokens)
            rows = conn.execute(
                """
                SELECT c.case_id, c.signature, c.exception_type, c.message_key, c.top_frames,
                       c.quality_score, c.status, c.updated_at
                FROM bug_cases_fts
                JOIN bug_cases c ON c.case_id=bug_cases_fts.case_id
                WHERE c.repo_url=? AND bug_cases_fts.text MATCH ?
                ORDER BY bm25(bug_cases_fts) ASC, c.quality_score DESC, c.updated_at DESC
                LIMIT ?
                """,
                (repo_url, match, max(int(limit), 1)),
            ).fetchall()
            return [self._row_to_case(r) for r in rows]

    def record_bug_case_revision(
        self,
        trace_id,
        repo_url,
        code_host,
        trigger_type,
        trigger_text,
        pr_url="",
        pr_title="",
        pr_body="",
        commit_sha="",
        changed_files_json="",
        diff_text="",
        preflight_ok=0,
    ):
        repo_url = (repo_url or "").strip()
        code_host = (code_host or "").strip()
        trigger_type = (trigger_type or "").strip().upper()
        trigger_text = trigger_text or ""
        now = int(time.time())

        features = self._extract_query_features(trigger_text)
        signature = features.get("signature") or ""
        exception_type = features.get("exception_type") or ""
        message_key = features.get("message_key") or ""
        top_frames = features.get("top_frames") or ""
        normalized_query = features.get("normalized_query") or ""

        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT case_id FROM bug_cases
                WHERE repo_url=? AND signature=?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (repo_url, signature),
            ).fetchone()
            if row:
                case_id = row[0]
                conn.execute(
                    """
                    UPDATE bug_cases
                    SET updated_at=?, code_host=?, exception_type=?, message_key=?, top_frames=?
                    WHERE case_id=?
                    """,
                    (now, code_host, exception_type, message_key, top_frames, case_id),
                )
            else:
                case_id = str(uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO bug_cases(
                        case_id, repo_url, code_host, signature, exception_type, message_key, top_frames,
                        status, quality_score, created_at, updated_at
                    )
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        case_id,
                        repo_url,
                        code_host,
                        signature,
                        exception_type,
                        message_key,
                        top_frames,
                        "DONE",
                        0.0,
                        now,
                        now,
                    ),
                )

            conn.execute(
                """
                INSERT INTO bug_case_revisions(
                    case_id, trace_id, trigger_type, trigger_text, pr_url, pr_title, pr_body, commit_sha,
                    changed_files_json, diff_text, preflight_ok, created_at
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    case_id,
                    trace_id,
                    trigger_type,
                    trigger_text[:20000],
                    (pr_url or "")[:2000],
                    (pr_title or "")[:500],
                    (pr_body or "")[:20000],
                    (commit_sha or "")[:200],
                    (changed_files_json or "")[:20000],
                    (diff_text or "")[:200000],
                    int(1 if preflight_ok else 0),
                    now,
                ),
            )

            fts_text = self._build_fts_text(exception_type, normalized_query, top_frames)
            conn.execute("DELETE FROM bug_cases_fts WHERE case_id=?", (case_id,))
            conn.execute(
                "INSERT INTO bug_cases_fts(case_id, text) VALUES(?, ?)",
                (case_id, fts_text[:20000]),
            )
        return case_id

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _ensure_column(self, conn, table, column, col_type):
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        existing = {r[1] for r in rows} if rows else set()
        if column in existing:
            return
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")

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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS bug_cases(
                    case_id TEXT PRIMARY KEY,
                    repo_url TEXT NOT NULL,
                    code_host TEXT NOT NULL,
                    signature TEXT NOT NULL,
                    exception_type TEXT,
                    message_key TEXT,
                    top_frames TEXT,
                    status TEXT NOT NULL,
                    quality_score REAL NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_bug_cases_repo_sig
                ON bug_cases(repo_url, signature)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS bug_case_revisions(
                    revision_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id TEXT NOT NULL,
                    trace_id TEXT,
                    trigger_type TEXT NOT NULL,
                    trigger_text TEXT,
                    pr_url TEXT,
                    pr_title TEXT,
                    pr_body TEXT,
                    commit_sha TEXT,
                    changed_files_json TEXT,
                    diff_text TEXT,
                    preflight_ok INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL,
                    FOREIGN KEY(case_id) REFERENCES bug_cases(case_id)
                )
                """
            )
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS bug_cases_fts
                USING fts5(case_id UNINDEXED, text)
                """
            )
            self._ensure_column(conn, "bug_case_revisions", "pr_title", "TEXT")
            self._ensure_column(conn, "bug_case_revisions", "pr_body", "TEXT")

    def _row_to_case(self, row):
        keys = ["case_id", "signature", "exception_type", "message_key", "top_frames", "quality_score", "status", "updated_at"]
        return dict(zip(keys, row))

    def _extract_query_features(self, text):
        raw = text or ""
        normalized = self._normalize_text(raw)
        exception_type, message = self._extract_exception_line(normalized)
        message_key = self._message_key(message)
        frames = self._extract_frames(raw)
        top_frames = " | ".join(frames[:5])
        fingerprint = " ".join(frames[:8])
        signature_base = f"{exception_type}\n{message_key}\n{fingerprint}".strip()
        signature = hashlib.sha256(signature_base.encode("utf-8", errors="ignore")).hexdigest() if signature_base else ""
        normalized_query = self._normalize_query_text(exception_type, message_key, frames)
        if not normalized_query:
            normalized_query = re.sub(r"\s+", " ", normalized).strip()[:500]
        if not signature and normalized_query:
            signature = hashlib.sha256(normalized_query.encode("utf-8", errors="ignore")).hexdigest()
        return {
            "exception_type": exception_type,
            "message_key": message_key,
            "top_frames": top_frames,
            "signature": signature,
            "normalized_query": normalized_query,
        }

    def _exception_simple_name(self, exception_type):
        s = (exception_type or "").strip()
        if not s:
            return ""
        s = s.split(":", 1)[0].strip()
        s = s.split(".")[-1]
        s = s.split("$")[-1]
        return s.strip()

    def _extract_exception_line(self, normalized_text):
        lines = [ln.strip() for ln in (normalized_text or "").splitlines() if ln.strip()]
        if not lines:
            return "", ""
        for ln in reversed(lines[-50:]):
            m = re.match(r"^([A-Za-z_][A-Za-z0-9_.$]*(?:Error|Exception))\s*:\s*(.*)$", ln)
            if m:
                return self._exception_simple_name(m.group(1)), (m.group(2) or "").strip()
        for ln in reversed(lines[-50:]):
            m = re.search(r"([A-Za-z_][A-Za-z0-9_.$]*(?:Error|Exception))\s*:\s*(.*)$", ln)
            if m:
                return self._exception_simple_name(m.group(1)), (m.group(2) or "").strip()
        last = lines[-1]
        m = re.search(r"([A-Za-z_][A-Za-z0-9_.$]*(?:Error|Exception))\b", last)
        if m:
            return self._exception_simple_name(m.group(1)), ""
        return "", ""

    def _extract_frames(self, raw_text):
        frames = []
        raw = raw_text or ""
        pattern = re.compile(r'File\s+"([^"]+)",\s+line\s+(\d+),\s+in\s+([A-Za-z_][A-Za-z0-9_]*)')
        for m in pattern.finditer(raw):
            file_path = m.group(1) or ""
            func = m.group(3) or ""
            file_name = os.path.basename(file_path.replace("\\", "/"))
            if not file_name:
                continue
            frames.append(f"{file_name}:{func}")
        java_pattern = re.compile(r"^\s*at\s+([A-Za-z0-9_.$]+)\(([A-Za-z0-9_.+$-]+):(\d+)\)\s*$", re.MULTILINE)
        for m in java_pattern.finditer(raw):
            full = (m.group(1) or "").strip()
            file_name = (m.group(2) or "").strip()
            if file_name.lower() in ("unknown source", "native method"):
                continue
            func = full.split(".")[-1] if full else ""
            if not file_name or not func:
                continue
            frames.append(f"{file_name}:{func}")
        return frames

    def _normalize_text(self, text):
        s = text or ""
        s = s.replace("\r\n", "\n").replace("\r", "\n")
        s = re.sub(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", "<uuid>", s, flags=re.IGNORECASE)
        s = re.sub(r"\b0x[0-9a-f]+\b", "<hex>", s, flags=re.IGNORECASE)
        s = re.sub(r"\b\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?\b", "<ts>", s)
        s = re.sub(r"[A-Za-z]:\\\\[^\s\"']+", "<path>", s)
        s = re.sub(r"(/[^ \n\t\"']+)+", "<path>", s)
        s = re.sub(r"\b\d{3,}\b", "<num>", s)
        return s

    def _message_key(self, message):
        s = (message or "").strip()
        if not s:
            return ""
        s = self._normalize_text(s)
        s = re.sub(r"['\"].*?['\"]", "<str>", s)
        s = re.sub(r"\s+", " ", s).strip()
        return s[:160]

    def _normalize_query_text(self, exception_type, message_key, frames):
        parts = []
        if exception_type:
            parts.append(exception_type)
        if message_key:
            parts.append(message_key)
        if frames:
            parts.append(" ".join(frames[:3]))
        text = " ".join(parts)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:500]

    def _build_fts_text(self, exception_type, normalized_query, top_frames):
        s = " ".join([exception_type or "", normalized_query or "", top_frames or ""])
        return re.sub(r"\s+", " ", s).strip()

    def _fts_query_tokens(self, exception_type, normalized_query):
        base = f"{exception_type or ''} {normalized_query or ''}".strip()
        base = re.sub(r"[^\w<>\- ]+", " ", base)
        tokens = [t.strip() for t in base.split() if t and t not in ("<ts>", "<uuid>", "<hex>", "<path>", "<num>", "<str>")]
        if len(tokens) > 16:
            tokens = tokens[:16]
        return tokens

    def _is_sha256(self, s):
        if not s or len(s) != 64:
            return False
        return bool(re.fullmatch(r"[0-9a-f]{64}", s.strip(), flags=re.IGNORECASE))

    def _fts_free_text_tokens(self, text):
        base = (text or "").strip()
        base = self._normalize_text(base)
        base = re.sub(r"[^\w<>\- ]+", " ", base)
        tokens = [t.strip() for t in base.split() if t and t not in ("<ts>", "<uuid>", "<hex>", "<path>", "<num>", "<str>")]
        if len(tokens) > 16:
            tokens = tokens[:16]
        return tokens

    def query_bug_cases(self, repo_url=None, q=None, limit=50, offset=0):
        repo_url = (repo_url or "").strip()
        q = (q or "").strip()
        limit = max(int(limit), 1)
        offset = max(int(offset), 0)

        with self._connect() as conn:
            conn.row_factory = sqlite3.Row

            if q and self._is_sha256(q):
                where = ["signature = ?"]
                params = [q]
                if repo_url:
                    where.insert(0, "repo_url = ?")
                    params.insert(0, repo_url)
                where_sql = " AND ".join(where)
                total = conn.execute(f"SELECT COUNT(*) FROM bug_cases WHERE {where_sql}", params).fetchone()[0]
                rows = conn.execute(
                    f"SELECT * FROM bug_cases WHERE {where_sql} ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                    params + [limit, offset],
                ).fetchall()
                return [dict(r) for r in rows], int(total)

            if q:
                tokens = self._fts_free_text_tokens(q)
                if tokens:
                    match = " ".join(tokens)
                    where = ["bug_cases_fts.text MATCH ?"]
                    params = [match]
                    if repo_url:
                        where.insert(0, "c.repo_url = ?")
                        params.insert(0, repo_url)
                    where_sql = " AND ".join(where)
                    total = conn.execute(
                        f"""
                        SELECT COUNT(*) FROM bug_cases_fts
                        JOIN bug_cases c ON c.case_id=bug_cases_fts.case_id
                        WHERE {where_sql}
                        """,
                        params,
                    ).fetchone()[0]
                    rows = conn.execute(
                        f"""
                        SELECT c.* FROM bug_cases_fts
                        JOIN bug_cases c ON c.case_id=bug_cases_fts.case_id
                        WHERE {where_sql}
                        ORDER BY bm25(bug_cases_fts) ASC, c.quality_score DESC, c.updated_at DESC
                        LIMIT ? OFFSET ?
                        """,
                        params + [limit, offset],
                    ).fetchall()
                    return [dict(r) for r in rows], int(total)

                like = f"%{q.lower()}%"
                where = ["(LOWER(exception_type) LIKE ? OR LOWER(message_key) LIKE ? OR signature LIKE ?)"]
                params = [like, like, q]
                if repo_url:
                    where.insert(0, "repo_url = ?")
                    params.insert(0, repo_url)
                where_sql = " AND ".join(where)
                total = conn.execute(f"SELECT COUNT(*) FROM bug_cases WHERE {where_sql}", params).fetchone()[0]
                rows = conn.execute(
                    f"SELECT * FROM bug_cases WHERE {where_sql} ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                    params + [limit, offset],
                ).fetchall()
                return [dict(r) for r in rows], int(total)

            where = []
            params = []
            if repo_url:
                where.append("repo_url = ?")
                params.append(repo_url)
            where_sql = f"WHERE {' AND '.join(where)}" if where else ""
            total = conn.execute(f"SELECT COUNT(*) FROM bug_cases {where_sql}", params).fetchone()[0]
            rows = conn.execute(
                f"SELECT * FROM bug_cases {where_sql} ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                params + [limit, offset],
            ).fetchall()
            return [dict(r) for r in rows], int(total)

    def list_bug_cases(self, repo_url=None, limit=50, offset=0):
        items, _total = self.query_bug_cases(repo_url=repo_url, q=None, limit=limit, offset=offset)
        return items

    def get_bug_case(self, case_id):
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM bug_cases WHERE case_id = ?", (case_id,)).fetchone()
            return dict(row) if row else None

    def get_bug_case_revisions(self, case_id):
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM bug_case_revisions WHERE case_id = ? ORDER BY created_at DESC", (case_id,)).fetchall()
            return [dict(row) for row in rows]

    def query_traces(self, repo_url=None, status=None, limit=50, offset=0):
        repo_url = (repo_url or "").strip()
        status = (status or "").strip().upper()
        limit = max(int(limit), 1)
        offset = max(int(offset), 0)

        where = []
        params = []
        if repo_url:
            where.append("repo_url = ?")
            params.append(repo_url)
        if status:
            where.append("status = ?")
            params.append(status)
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""

        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            total = conn.execute(f"SELECT COUNT(*) FROM traces {where_sql}", params).fetchone()[0]
            rows = conn.execute(
                f"SELECT * FROM traces {where_sql} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                params + [limit, offset],
            ).fetchall()
            return [dict(r) for r in rows], int(total)

    def list_traces(self, limit=50, offset=0):
        items, _total = self.query_traces(limit=limit, offset=offset)
        return items

    def debug_retrieval(self, query_text):
        features = self._extract_query_features(query_text)
        exception_type = features.get("exception_type") or ""
        normalized_query = features.get("normalized_query") or ""
        signature = features.get("signature") or ""

        matches = []
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            if signature:
                rows = conn.execute(
                    "SELECT * FROM bug_cases WHERE signature = ? ORDER BY quality_score DESC LIMIT 5",
                    (signature,)
                ).fetchall()
                matches = [dict(r) for r in rows]

            if not matches:
                tokens = self._fts_query_tokens(exception_type, normalized_query)
                if tokens:
                    match_str = " ".join(tokens)
                    rows = conn.execute(
                        """
                        SELECT c.* FROM bug_cases_fts
                        JOIN bug_cases c ON c.case_id = bug_cases_fts.case_id
                        WHERE bug_cases_fts.text MATCH ?
                        ORDER BY bm25(bug_cases_fts) ASC, c.quality_score DESC
                        LIMIT 5
                        """,
                        (match_str,)
                    ).fetchall()
                    matches = [dict(r) for r in rows]

        return {
            "features": features,
            "matches": matches
        }




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

