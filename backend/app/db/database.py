"""
SQLite 数据库访问层 — 讨论、嘉宾、发言、共识、分歧的 CRUD。
"""

import json
import sqlite3
from pathlib import Path
from typing import Optional
from contextlib import contextmanager

from app.core.models import (
    Discussion, DiscussionStatus,
    Panelist, PanelistRole,
    Utterance, UtteranceType,
    Consensus, Divergence,
    new_id, now_iso,
)

DB_PATH = Path("C:/Users/大反派/AppData/Roaming/TRAE SOLO CN/ModularData/ai-agent/work-mode-projects/6a4b27824bf5329b06acb20a/ai_panel_studio.db")


def get_db_path() -> Path:
    return DB_PATH


def init_db(db_path: Optional[Path] = None):
    """初始化数据库并建表"""
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(str(path)) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = DELETE")
        conn.executescript(SCHEMA_SQL)


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS discussions (
    id            TEXT NOT NULL PRIMARY KEY,
    topic         TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'draft',
    max_rounds    INTEGER NOT NULL DEFAULT 12,
    current_round INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS panelists (
    id            TEXT NOT NULL PRIMARY KEY,
    discussion_id TEXT NOT NULL,
    role          TEXT NOT NULL,
    name          TEXT NOT NULL,
    occupation    TEXT NOT NULL,
    title         TEXT NOT NULL,
    stance        TEXT NOT NULL,
    color         TEXT NOT NULL,
    sort_order    INTEGER NOT NULL,
    created_at    TEXT NOT NULL,
    FOREIGN KEY (discussion_id) REFERENCES discussions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS utterances (
    id            TEXT NOT NULL PRIMARY KEY,
    discussion_id TEXT NOT NULL,
    panelist_id   TEXT NOT NULL,
    type          TEXT NOT NULL,
    content       TEXT NOT NULL,
    round         INTEGER NOT NULL,
    seq           INTEGER NOT NULL,
    created_at    TEXT NOT NULL,
    FOREIGN KEY (discussion_id) REFERENCES discussions(id) ON DELETE CASCADE,
    FOREIGN KEY (panelist_id) REFERENCES panelists(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS consensus (
    id                   TEXT NOT NULL PRIMARY KEY,
    discussion_id        TEXT NOT NULL,
    content              TEXT NOT NULL,
    source_utterance_ids TEXT NOT NULL DEFAULT '[]',
    version              INTEGER NOT NULL DEFAULT 1,
    created_at           TEXT NOT NULL,
    updated_at           TEXT NOT NULL,
    FOREIGN KEY (discussion_id) REFERENCES discussions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS divergences (
    id                   TEXT NOT NULL PRIMARY KEY,
    discussion_id        TEXT NOT NULL,
    content              TEXT NOT NULL,
    opposing_sides       TEXT NOT NULL DEFAULT '[]',
    source_utterance_ids TEXT NOT NULL DEFAULT '[]',
    version              INTEGER NOT NULL DEFAULT 1,
    created_at           TEXT NOT NULL,
    updated_at           TEXT NOT NULL,
    FOREIGN KEY (discussion_id) REFERENCES discussions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS panelist_states (
    panelist_id   TEXT NOT NULL PRIMARY KEY,
    discussion_id TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'idle',
    focus         TEXT,
    updated_at    TEXT NOT NULL,
    FOREIGN KEY (panelist_id) REFERENCES panelists(id) ON DELETE CASCADE,
    FOREIGN KEY (discussion_id) REFERENCES discussions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_panelists_discussion ON panelists(discussion_id);
CREATE INDEX IF NOT EXISTS idx_utterances_discussion ON utterances(discussion_id);
CREATE INDEX IF NOT EXISTS idx_utterances_seq ON utterances(discussion_id, seq);
CREATE INDEX IF NOT EXISTS idx_consensus_discussion ON consensus(discussion_id);
CREATE INDEX IF NOT EXISTS idx_divergences_discussion ON divergences(discussion_id);
"""


class Database:
    """异步 SQLite 访问层（同步操作，由调用方保证在 executor 中运行）"""

    def __init__(self, db_path: Optional[Path] = None):
        self.path = str(db_path or DB_PATH)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = sqlite3.Row
        return conn

    # ── 讨论 ──────────────────────────────────────────

    def create_discussion(self, topic: str, expert_count: int, max_rounds: int) -> Discussion:
        d = Discussion(
            id=new_id(),
            topic=topic,
            status=DiscussionStatus.DRAFT,
            max_rounds=max_rounds,
            current_round=0,
        )
        now = now_iso()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO discussions (id, topic, status, max_rounds, current_round, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (d.id, d.topic, d.status, d.max_rounds, d.current_round, now, now),
            )
        return d

    def get_discussion(self, discussion_id: str) -> Optional[Discussion]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM discussions WHERE id = ?", (discussion_id,)).fetchone()
        if row is None:
            return None
        return Discussion(
            id=row["id"], topic=row["topic"],
            status=DiscussionStatus(row["status"]),
            max_rounds=row["max_rounds"], current_round=row["current_round"],
        )

    def list_discussions(self, status: Optional[str] = None, limit: int = 20, offset: int = 0):
        query = "SELECT * FROM discussions"
        params = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            Discussion(id=r["id"], topic=r["topic"], status=DiscussionStatus(r["status"]),
                       max_rounds=r["max_rounds"], current_round=r["current_round"])
            for r in rows
        ]

    def update_discussion(self, discussion: Discussion):
        now = now_iso()
        with self._connect() as conn:
            conn.execute(
                "UPDATE discussions SET status=?, current_round=?, updated_at=? WHERE id=?",
                (discussion.status, discussion.current_round, now, discussion.id),
            )

    def delete_discussion(self, discussion_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM discussions WHERE id = ? AND status = 'ended'", (discussion_id,))
            return cursor.rowcount > 0

    # ── 嘉宾 ──────────────────────────────────────────

    def create_panelist(self, panelist: Panelist):
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO panelists (id, discussion_id, role, name, occupation, title, stance, color, sort_order, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (panelist.id, panelist.discussion_id, panelist.role, panelist.name,
                 panelist.occupation, panelist.title, panelist.stance, panelist.color,
                 panelist.sort_order, now_iso()),
            )

    def list_panelists(self, discussion_id: str) -> list[Panelist]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM panelists WHERE discussion_id = ? ORDER BY sort_order",
                (discussion_id,),
            ).fetchall()
        return [Panelist.from_dict(dict(r)) for r in rows]

    def get_panelist(self, panelist_id: str) -> Optional[Panelist]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM panelists WHERE id = ?", (panelist_id,)).fetchone()
        return Panelist.from_dict(dict(row)) if row else None

    def update_panelist(self, panelist_id: str, updates: dict):
        allowed = {"name", "occupation", "title", "stance", "color"}
        fields = {k: v for k, v in updates.items() if k in allowed and v is not None}
        if not fields:
            return
        set_clause = ", ".join(f"{k}=?" for k in fields)
        values = list(fields.values()) + [panelist_id]
        with self._connect() as conn:
            conn.execute(f"UPDATE panelists SET {set_clause} WHERE id=?", values)

    def delete_panelist(self, panelist_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM panelists WHERE id = ? AND role != 'moderator'", (panelist_id,))
            return cursor.rowcount > 0

    def clear_panelists(self, discussion_id: str):
        with self._connect() as conn:
            conn.execute("DELETE FROM panelists WHERE discussion_id = ? AND role != 'moderator'", (discussion_id,))

    def get_panelist_count(self, discussion_id: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM panelists WHERE discussion_id = ?",
                (discussion_id,),
            ).fetchone()
        return row["cnt"]

    # ── 发言 ──────────────────────────────────────────

    def save_utterance(self, utterance: Utterance):
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO utterances (id, discussion_id, panelist_id, type, content, round, seq, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (utterance.id, utterance.discussion_id, utterance.panelist_id,
                 utterance.type, utterance.content, utterance.round, utterance.seq, utterance.created_at),
            )

    def list_utterances(self, discussion_id: str, after_seq: int = 0, limit: int = 100) -> list[Utterance]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM utterances WHERE discussion_id = ? AND seq > ? ORDER BY seq LIMIT ?",
                (discussion_id, after_seq, limit),
            ).fetchall()
        return [
            Utterance(id=r["id"], discussion_id=r["discussion_id"], panelist_id=r["panelist_id"],
                      type=UtteranceType(r["type"]), content=r["content"],
                      round=r["round"], seq=r["seq"], created_at=r["created_at"])
            for r in rows
        ]

    def get_utterance_count(self, discussion_id: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM utterances WHERE discussion_id = ?",
                (discussion_id,),
            ).fetchone()
        return row["cnt"]

    # ── 共识/分歧 ─────────────────────────────────────

    def save_consensus(self, c: Consensus):
        now = now_iso()
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO consensus (id, discussion_id, content, source_utterance_ids, version, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM consensus WHERE id=?), ?), ?)",
                (c.id, c.discussion_id, c.content, json.dumps(c.source_utterance_ids), c.version,
                 c.id, now, now),
            )

    def list_consensus(self, discussion_id: str) -> list[Consensus]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM consensus WHERE discussion_id = ? ORDER BY version",
                (discussion_id,),
            ).fetchall()
        return [
            Consensus(id=r["id"], discussion_id=r["discussion_id"], content=r["content"],
                      source_utterance_ids=json.loads(r["source_utterance_ids"]),
                      version=r["version"])
            for r in rows
        ]

    def save_divergence(self, d: Divergence):
        now = now_iso()
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO divergences (id, discussion_id, content, opposing_sides, source_utterance_ids, version, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM divergences WHERE id=?), ?), ?)",
                (d.id, d.discussion_id, d.content, json.dumps(d.opposing_sides),
                 json.dumps(d.source_utterance_ids), d.version, d.id, now, now),
            )

    def list_divergences(self, discussion_id: str) -> list[Divergence]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM divergences WHERE discussion_id = ? ORDER BY version",
                (discussion_id,),
            ).fetchall()
        return [
            Divergence(id=r["id"], discussion_id=r["discussion_id"], content=r["content"],
                       opposing_sides=json.loads(r["opposing_sides"]),
                       source_utterance_ids=json.loads(r["source_utterance_ids"]),
                       version=r["version"])
            for r in rows
        ]
