from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


class Database:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    topic TEXT NOT NULL,
                    learning_goal TEXT NOT NULL,
                    rounds_per_segment INTEGER NOT NULL DEFAULT 3,
                    sources_only INTEGER NOT NULL DEFAULT 0,
                    periodic_summary INTEGER NOT NULL DEFAULT 0,
                    state TEXT NOT NULL DEFAULT 'HUMAN_FLOOR',
                    active_question TEXT NOT NULL DEFAULT '',
                    topic_digest TEXT NOT NULL DEFAULT '{}',
                    conversation_digest TEXT NOT NULL DEFAULT '{}',
                    completed_rounds INTEGER NOT NULL DEFAULT 0,
                    digested_through_round INTEGER NOT NULL DEFAULT 0,
                    next_speaker TEXT NOT NULL DEFAULT 'Momo',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS rounds (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    round_number INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    UNIQUE(session_id, round_number)
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    round_id TEXT REFERENCES rounds(id) ON DELETE SET NULL,
                    speaker TEXT NOT NULL,
                    content TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'complete',
                    target TEXT NOT NULL DEFAULT 'roundtable',
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    filename TEXT NOT NULL,
                    stored_path TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued',
                    digest TEXT NOT NULL DEFAULT '',
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS passages (
                    id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    page_number INTEGER,
                    section TEXT,
                    content TEXT NOT NULL,
                    ordinal INTEGER NOT NULL
                );

                CREATE VIRTUAL TABLE IF NOT EXISTS passages_fts USING fts5(
                    passage_id UNINDEXED,
                    document_id UNINDEXED,
                    filename UNINDEXED,
                    page_number UNINDEXED,
                    content,
                    tokenize='porter unicode61'
                );

                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued',
                    progress REAL NOT NULL DEFAULT 0,
                    detail TEXT NOT NULL DEFAULT '',
                    payload TEXT NOT NULL DEFAULT '{}',
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS summary_digests (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    kind TEXT NOT NULL,
                    through_round INTEGER NOT NULL DEFAULT 0,
                    digest TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS learning_evaluations (
                    session_id TEXT PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
                    report TEXT NOT NULL DEFAULT '{}',
                    ratings TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS messages_session_created
                    ON messages(session_id, created_at);
                CREATE INDEX IF NOT EXISTS rounds_session_number
                    ON rounds(session_id, round_number);
                CREATE INDEX IF NOT EXISTS documents_session_created
                    ON documents(session_id, created_at);
                CREATE INDEX IF NOT EXISTS summary_digests_session_created
                    ON summary_digests(session_id, created_at);
                """
            )

    def reconcile_abandoned_work(self) -> dict[str, int]:
        """Make persisted in-flight state honest after a process restart."""
        now = utc_now()
        with self.connect() as db:
            counts = {
                "jobs": db.execute(
                    "SELECT COUNT(*) FROM jobs WHERE status IN ('queued', 'running')"
                ).fetchone()[0],
                "documents": db.execute(
                    "SELECT COUNT(*) FROM documents WHERE status IN ('queued', 'processing')"
                ).fetchone()[0],
                "rounds": db.execute(
                    "SELECT COUNT(*) FROM rounds WHERE status = 'active'"
                ).fetchone()[0],
                "sessions": db.execute(
                    "SELECT COUNT(*) FROM sessions WHERE state IN ('AI_SEGMENT_RUNNING', 'INTERRUPTING', 'CLOSING')"
                ).fetchone()[0],
            }
            db.execute(
                """UPDATE jobs SET status = 'interrupted',
                   detail = 'Interrupted by application restart',
                   error = 'This in-process job cannot resume automatically',
                   updated_at = ?
                   WHERE status IN ('queued', 'running')""",
                (now,),
            )
            db.execute(
                """UPDATE documents SET status = 'failed',
                   error = 'Document processing was interrupted by application restart; upload it again to retry',
                   updated_at = ?
                   WHERE status IN ('queued', 'processing')""",
                (now,),
            )
            db.execute(
                """UPDATE rounds SET status = 'interrupted', completed_at = ?
                   WHERE status = 'active'""",
                (now,),
            )
            db.execute(
                """UPDATE sessions SET state = 'HUMAN_FLOOR', updated_at = ?
                   WHERE state IN ('AI_SEGMENT_RUNNING', 'INTERRUPTING')""",
                (now,),
            )
            db.execute(
                """UPDATE sessions SET state = 'CLOSED', updated_at = ?
                   WHERE state = 'CLOSING'""",
                (now,),
            )
        return counts

    @staticmethod
    def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        result = dict(row)
        for field in ("topic_digest", "conversation_digest", "metadata", "payload", "digest", "report", "ratings"):
            if field in result and isinstance(result[field], str):
                try:
                    result[field] = json.loads(result[field])
                except json.JSONDecodeError:
                    pass
        for field in ("sources_only", "periodic_summary"):
            if field in result:
                result[field] = bool(result[field])
        return result

    def create_session(
        self,
        topic: str,
        learning_goal: str,
        rounds_per_segment: int,
        sources_only: bool,
        periodic_summary: bool,
    ) -> dict[str, Any]:
        session_id = new_id("ses")
        now = utc_now()
        provisional_digest = {
            "topic": topic,
            "learning_goal": learning_goal,
            "central_question": topic,
            "scope": [],
            "excluded_topics": [],
            "key_concepts": [],
            "theoretical_perspectives": [],
            "source_boundaries": [],
            "discussion_mode": "exploratory roundtable",
            "promising_questions": [],
            "status": "provisional",
        }
        with self.connect() as db:
            db.execute(
                """INSERT INTO sessions
                (id, topic, learning_goal, rounds_per_segment, sources_only,
                 periodic_summary, active_question, topic_digest, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_id,
                    topic,
                    learning_goal,
                    rounds_per_segment,
                    int(sources_only),
                    int(periodic_summary),
                    topic,
                    json.dumps(provisional_digest),
                    now,
                    now,
                ),
            )
        return self.get_session(session_id)

    def list_sessions(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM sessions ORDER BY updated_at DESC LIMIT 100"
            ).fetchall()
        return [self._row(row) for row in rows if row]

    def purge_all_sessions(self) -> list[str]:
        """Delete every prior session and return managed upload paths for filesystem cleanup."""
        with self.connect() as db:
            upload_paths = [
                row["stored_path"]
                for row in db.execute("SELECT stored_path FROM documents").fetchall()
            ]
            db.execute("DELETE FROM passages_fts")
            db.execute("DELETE FROM sessions")
        return upload_paths

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        return self._row(row)

    def update_session(self, session_id: str, **fields: Any) -> dict[str, Any] | None:
        allowed = {
            "rounds_per_segment",
            "sources_only",
            "periodic_summary",
            "state",
            "active_question",
            "topic_digest",
            "conversation_digest",
            "completed_rounds",
            "digested_through_round",
            "next_speaker",
        }
        updates: list[str] = []
        values: list[Any] = []
        for key, value in fields.items():
            if key not in allowed:
                continue
            if key in {"topic_digest", "conversation_digest"}:
                value = json.dumps(value)
            if key in {"sources_only", "periodic_summary"}:
                value = int(bool(value))
            updates.append(f"{key} = ?")
            values.append(value)
        if not updates:
            return self.get_session(session_id)
        updates.append("updated_at = ?")
        values.append(utc_now())
        values.append(session_id)
        with self.connect() as db:
            db.execute(f"UPDATE sessions SET {', '.join(updates)} WHERE id = ?", values)
        return self.get_session(session_id)

    def create_round(self, session_id: str) -> dict[str, Any]:
        with self.connect() as db:
            number = db.execute(
                "SELECT COALESCE(MAX(round_number), 0) + 1 FROM rounds WHERE session_id = ?",
                (session_id,),
            ).fetchone()[0]
            round_id = new_id("rnd")
            db.execute(
                "INSERT INTO rounds (id, session_id, round_number, started_at) VALUES (?, ?, ?, ?)",
                (round_id, session_id, number, utc_now()),
            )
            row = db.execute("SELECT * FROM rounds WHERE id = ?", (round_id,)).fetchone()
        return dict(row)

    def complete_round(self, round_id: str) -> None:
        with self.connect() as db:
            row = db.execute(
                "SELECT session_id FROM rounds WHERE id = ? AND status = 'active'", (round_id,)
            ).fetchone()
            if not row:
                return
            db.execute(
                "UPDATE rounds SET status = 'complete', completed_at = ? WHERE id = ?",
                (utc_now(), round_id),
            )
            db.execute(
                """UPDATE sessions SET completed_rounds = completed_rounds + 1,
                   updated_at = ? WHERE id = ?""",
                (utc_now(), row["session_id"]),
            )

    def interrupt_round(self, round_id: str) -> None:
        with self.connect() as db:
            db.execute(
                "UPDATE rounds SET status = 'interrupted', completed_at = ? WHERE id = ?",
                (utc_now(), round_id),
            )

    def add_message(
        self,
        session_id: str,
        speaker: str,
        content: str,
        round_id: str | None = None,
        status: str = "complete",
        target: str = "roundtable",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        message_id = new_id("msg")
        with self.connect() as db:
            db.execute(
                """INSERT INTO messages
                (id, session_id, round_id, speaker, content, status, target, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    message_id,
                    session_id,
                    round_id,
                    speaker,
                    content,
                    status,
                    target,
                    json.dumps(metadata or {}),
                    utc_now(),
                ),
            )
            db.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (utc_now(), session_id))
            row = db.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
        return self._row(row)

    def list_messages(self, session_id: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at, rowid",
                (session_id,),
            ).fetchall()
        return [self._row(row) for row in rows if row]

    def recent_round_messages(self, session_id: str, round_count: int) -> list[dict[str, Any]]:
        with self.connect() as db:
            round_rows = db.execute(
                """SELECT id, started_at FROM rounds WHERE session_id = ? AND status = 'complete'
                   ORDER BY round_number DESC LIMIT ?""",
                (session_id, round_count),
            ).fetchall()
            round_ids = [row["id"] for row in reversed(round_rows)]
            if not round_ids:
                rows = db.execute(
                    "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at DESC LIMIT 12",
                    (session_id,),
                ).fetchall()
                messages = [self._row(row) for row in reversed(rows) if row]
                return [
                    item for item in messages
                    if (item.get("metadata") or {}).get("kind") not in {"greeting", "session_opening", "recap", "final_summary", "closing"}
                ]
            placeholders = ",".join("?" for _ in round_ids)
            earliest_started = min(row["started_at"] for row in round_rows)
            rows = db.execute(
                f"""SELECT * FROM messages
                    WHERE session_id = ? AND
                    (round_id IN ({placeholders}) OR (speaker = 'Sam' AND created_at >= ?))
                    ORDER BY created_at, rowid""",
                [session_id, *round_ids, earliest_started],
            ).fetchall()
        return [self._row(row) for row in rows if row]

    def add_summary_digest(
        self,
        session_id: str,
        kind: str,
        through_round: int,
        digest: dict[str, Any],
    ) -> dict[str, Any]:
        digest_id = new_id("sum")
        with self.connect() as db:
            db.execute(
                """INSERT INTO summary_digests
                   (id, session_id, kind, through_round, digest, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (digest_id, session_id, kind, through_round, json.dumps(digest), utc_now()),
            )
            row = db.execute(
                "SELECT * FROM summary_digests WHERE id = ?", (digest_id,)
            ).fetchone()
        return self._row(row)

    def list_summary_digests(self, session_id: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                """SELECT * FROM summary_digests WHERE session_id = ?
                   ORDER BY created_at, rowid""",
                (session_id,),
            ).fetchall()
        return [self._row(row) for row in rows if row]

    def get_learning_evaluation(self, session_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM learning_evaluations WHERE session_id = ?", (session_id,)
            ).fetchone()
        return self._row(row)

    def save_learning_evaluation(
        self,
        session_id: str,
        report: dict[str, Any],
        ratings: dict[str, Any],
    ) -> dict[str, Any]:
        now = utc_now()
        with self.connect() as db:
            db.execute(
                """INSERT INTO learning_evaluations
                   (session_id, report, ratings, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(session_id) DO UPDATE SET
                     report = excluded.report,
                     ratings = excluded.ratings,
                     updated_at = excluded.updated_at""",
                (
                    session_id,
                    json.dumps(report, ensure_ascii=False),
                    json.dumps(ratings, ensure_ascii=False),
                    now,
                    now,
                ),
            )
        return self.get_learning_evaluation(session_id)

    def has_active_job(self, session_id: str, kind: str) -> bool:
        with self.connect() as db:
            row = db.execute(
                """SELECT 1 FROM jobs WHERE session_id = ? AND kind = ?
                   AND status IN ('queued', 'running') LIMIT 1""",
                (session_id, kind),
            ).fetchone()
        return bool(row)

    def add_document(self, session_id: str, filename: str, stored_path: str, media_type: str) -> dict[str, Any]:
        document_id = new_id("doc")
        now = utc_now()
        with self.connect() as db:
            db.execute(
                """INSERT INTO documents
                   (id, session_id, filename, stored_path, media_type, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (document_id, session_id, filename, stored_path, media_type, now, now),
            )
        return self.get_document(document_id)

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        return self._row(row)

    def list_documents(self, session_id: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM documents WHERE session_id = ? ORDER BY created_at", (session_id,)
            ).fetchall()
        return [self._row(row) for row in rows if row]

    def update_document(self, document_id: str, **fields: Any) -> None:
        allowed = {"status", "digest", "error"}
        updates, values = [], []
        for key, value in fields.items():
            if key in allowed:
                updates.append(f"{key} = ?")
                values.append(value)
        if not updates:
            return
        updates.append("updated_at = ?")
        values.extend([utc_now(), document_id])
        with self.connect() as db:
            db.execute(f"UPDATE documents SET {', '.join(updates)} WHERE id = ?", values)

    def replace_passages(self, document_id: str, filename: str, passages: list[dict[str, Any]]) -> None:
        with self.connect() as db:
            old_ids = [row[0] for row in db.execute(
                "SELECT id FROM passages WHERE document_id = ?", (document_id,)
            ).fetchall()]
            for passage_id in old_ids:
                db.execute("DELETE FROM passages_fts WHERE passage_id = ?", (passage_id,))
            db.execute("DELETE FROM passages WHERE document_id = ?", (document_id,))
            for ordinal, passage in enumerate(passages):
                passage_id = new_id("psg")
                page_number = passage.get("page_number")
                content = passage["content"]
                section = passage.get("section", "")
                db.execute(
                    """INSERT INTO passages
                       (id, document_id, page_number, section, content, ordinal)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (passage_id, document_id, page_number, section, content, ordinal),
                )
                db.execute(
                    """INSERT INTO passages_fts
                       (passage_id, document_id, filename, page_number, content)
                       VALUES (?, ?, ?, ?, ?)""",
                    (passage_id, document_id, filename, page_number, content),
                )

    def search_passages(self, session_id: str, query: str, limit: int = 6) -> list[dict[str, Any]]:
        terms = [term for term in query.replace('"', " ").split() if len(term) > 2][:12]
        if not terms:
            return []
        fts_query = " OR ".join(f'"{term}"' for term in terms)
        with self.connect() as db:
            rows = db.execute(
                """SELECT f.passage_id, f.document_id, f.filename, f.page_number,
                          f.content, bm25(passages_fts) AS score
                   FROM passages_fts f
                   JOIN documents d ON d.id = f.document_id
                   WHERE d.session_id = ? AND passages_fts MATCH ?
                   ORDER BY score LIMIT ?""",
                (session_id, fts_query, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_job(self, session_id: str, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        job_id = new_id("job")
        now = utc_now()
        with self.connect() as db:
            db.execute(
                """INSERT INTO jobs
                   (id, session_id, kind, payload, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (job_id, session_id, kind, json.dumps(payload), now, now),
            )
        return self.get_job(job_id)

    def update_job(self, job_id: str, **fields: Any) -> None:
        allowed = {"status", "progress", "detail", "error", "payload"}
        updates, values = [], []
        for key, value in fields.items():
            if key not in allowed:
                continue
            if key == "payload":
                value = json.dumps(value)
            updates.append(f"{key} = ?")
            values.append(value)
        if not updates:
            return
        updates.append("updated_at = ?")
        values.extend([utc_now(), job_id])
        with self.connect() as db:
            db.execute(f"UPDATE jobs SET {', '.join(updates)} WHERE id = ?", values)

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return self._row(row)

    def list_jobs(self, session_id: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM jobs WHERE session_id = ? ORDER BY created_at DESC LIMIT 100",
                (session_id,),
            ).fetchall()
        return [self._row(row) for row in rows if row]
