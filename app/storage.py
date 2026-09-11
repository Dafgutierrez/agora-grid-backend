import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

DB_PATH = os.environ.get("DATABASE_PATH", "./agora.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_name TEXT NOT NULL,
    buyer_name TEXT NOT NULL,
    service TEXT NOT NULL,
    description TEXT NOT NULL,
    transcript TEXT NOT NULL DEFAULT '',
    amount_usd REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    checkout_url TEXT,
    payment_ref TEXT,
    created_at TEXT NOT NULL,
    decided_at TEXT
);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute(SCHEMA)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def create_proposal(agent_name, buyer_name, service, description, transcript, amount_usd):
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO proposals
               (agent_name, buyer_name, service, description, transcript, amount_usd, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)""",
            (agent_name, buyer_name, service, description, transcript, amount_usd, now_iso()),
        )
        return cur.lastrowid


def get_proposal(proposal_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,)).fetchone()
        return dict(row) if row else None


def list_proposals(status=None):
    with get_conn() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM proposals WHERE status = ? ORDER BY created_at DESC", (status,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM proposals ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


def set_status(proposal_id, status, checkout_url=None, payment_ref=None):
    with get_conn() as conn:
        conn.execute(
            """UPDATE proposals
               SET status = ?, checkout_url = COALESCE(?, checkout_url),
                   payment_ref = COALESCE(?, payment_ref), decided_at = ?
               WHERE id = ?""",
            (status, checkout_url, payment_ref, now_iso(), proposal_id),
        )


def find_by_checkout_metadata(proposal_id):
    return get_proposal(proposal_id)
