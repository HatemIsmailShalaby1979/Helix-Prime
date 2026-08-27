"""
Cognitive Memory Log — append-only JSON + SQLite log of all agent interactions.

Every agent interaction (timestamp, agent, input, output, reasoning, inter-agent calls)
is recorded here. Provides search/query for the Memory tab.
"""

import json
import queue
import sqlite3
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

LOG_DIR = Path(__file__).resolve().parent
JSON_LOG = LOG_DIR / "cognitive_log.jsonl"
SQLITE_DB = LOG_DIR / "cognitive_log.sqlite"
DB_LOCK = threading.Lock()
LOG_QUEUE: "queue.Queue[LogEntry]" = queue.Queue()
_LOG_WORKER_THREAD: threading.Thread | None = None


@dataclass
class LogEntry:
    timestamp: str
    agent: str
    user_input: str
    agent_output: str
    reasoning_trace: str | None = None
    inter_agent_calls: list[dict[str, Any]] | None = None
    session_id: str | None = None
    client_context: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _init_sqlite() -> None:
    with DB_LOCK:
        conn = sqlite3.connect(SQLITE_DB)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS interactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    agent TEXT NOT NULL,
                    user_input TEXT NOT NULL,
                    agent_output TEXT NOT NULL,
                    reasoning_trace TEXT,
                    inter_agent_calls TEXT,
                    session_id TEXT,
                    client_context TEXT
                )
            """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_agent ON interactions(agent)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_timestamp ON interactions(timestamp)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_session ON interactions(session_id)"
            )
            conn.commit()
        finally:
            conn.close()


def _write_log_entry(entry: LogEntry) -> None:
    with DB_LOCK:
        conn = sqlite3.connect(SQLITE_DB)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            with JSON_LOG.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
            conn.execute(
                """
                INSERT INTO interactions (timestamp, agent, user_input, agent_output,
                                          reasoning_trace, inter_agent_calls, session_id, client_context)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.timestamp,
                    entry.agent,
                    entry.user_input,
                    entry.agent_output,
                    entry.reasoning_trace,
                    json.dumps(entry.inter_agent_calls)
                    if entry.inter_agent_calls
                    else None,
                    entry.session_id,
                    entry.client_context,
                ),
            )
            conn.commit()
        finally:
            conn.close()


def _log_writer_loop() -> None:
    while True:
        entry = LOG_QUEUE.get()
        if entry is None:
            LOG_QUEUE.task_done()
            break
        try:
            _write_log_entry(entry)
        except Exception as e:
            print(f"[CognitiveLog] Failed to write log entry: {e}")
        finally:
            LOG_QUEUE.task_done()


def _start_log_writer() -> None:
    global _LOG_WORKER_THREAD
    if _LOG_WORKER_THREAD is None:
        _LOG_WORKER_THREAD = threading.Thread(
            target=_log_writer_loop,
            name="cognitive-log-writer",
            daemon=True,
        )
        _LOG_WORKER_THREAD.start()


def log_interaction(entry: LogEntry) -> None:
    """Queue the interaction for asynchronous persistence."""
    _start_log_writer()
    LOG_QUEUE.put(entry)


def query_interactions(
    agent: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    session_id: str | None = None,
    search_text: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Query interactions with optional filters."""
    _init_sqlite()
    conditions = []
    params = []

    if agent:
        conditions.append("agent = ?")
        params.append(agent)
    if start_date:
        conditions.append("timestamp >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("timestamp <= ?")
        params.append(end_date)
    if session_id:
        conditions.append("session_id = ?")
        params.append(session_id)
    if search_text:
        conditions.append(
            "(user_input LIKE ? OR agent_output LIKE ? OR reasoning_trace LIKE ?)"
        )
        params.extend([f"%{search_text}%"] * 3)

    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    sql = f"SELECT * FROM interactions {where} ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)

    with DB_LOCK:
        conn = sqlite3.connect(SQLITE_DB)
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.execute(sql, params)
            rows = [dict(row) for row in cur.fetchall()]
            # Parse JSON fields from SQLite TEXT columns
            for row in rows:
                if isinstance(row.get("inter_agent_calls"), str):
                    try:
                        row["inter_agent_calls"] = json.loads(row["inter_agent_calls"])
                    except (json.JSONDecodeError, TypeError):
                        pass
            return rows
        finally:
            conn.close()


def get_all_agents() -> list[str]:
    _init_sqlite()
    with DB_LOCK:
        conn = sqlite3.connect(SQLITE_DB)
        try:
            cur = conn.execute("SELECT DISTINCT agent FROM interactions ORDER BY agent")
            return [row[0] for row in cur.fetchall()]
        finally:
            conn.close()


def get_session_ids() -> list[str]:
    _init_sqlite()
    with DB_LOCK:
        conn = sqlite3.connect(SQLITE_DB)
        try:
            cur = conn.execute(
                "SELECT DISTINCT session_id FROM interactions WHERE session_id IS NOT NULL ORDER BY session_id DESC"
            )
            return [row[0] for row in cur.fetchall()]
        finally:
            conn.close()


# Initialize on import
_init_sqlite()
