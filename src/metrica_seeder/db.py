"""Работа с SQLite: подключение и миграции."""
from __future__ import annotations

import sqlite3

from .config import get_db_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    phone       TEXT NOT NULL UNIQUE,
    name        TEXT,
    client_id   TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id       TEXT NOT NULL,
    target          TEXT NOT NULL,
    datetime_unix   INTEGER NOT NULL,
    price           REAL DEFAULT 0,
    currency        TEXT DEFAULT 'RUB',
    status          TEXT DEFAULT 'pending',
    upload_id       INTEGER,
    created_at      TEXT NOT NULL,
    FOREIGN KEY (client_id) REFERENCES clients(client_id)
);

CREATE INDEX IF NOT EXISTS idx_events_status ON events(status);

CREATE TABLE IF NOT EXISTS uploads (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    uploading_id    INTEGER,
    csv_path        TEXT,
    status          TEXT DEFAULT 'pending',
    source_quantity INTEGER DEFAULT 0,
    line_quantity   INTEGER DEFAULT 0,
    created_at      TEXT NOT NULL,
    processed_at    TEXT
);
"""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db() -> None:
    conn = get_connection()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
        print(f"[DB] Инициализирована база: {get_db_path()}")
    finally:
        conn.close()