"""SQLite schema and connection management for the local transaction store."""

import os
import sqlite3
from contextlib import closing
from pathlib import Path

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1] / ".finpilot"
DB_PATH = Path(os.getenv("FINPILOT_DATA_DIR", str(DEFAULT_DATA_DIR))).expanduser().resolve() / "transactions.sqlite3"

SCHEMA = """
CREATE TABLE IF NOT EXISTS import_batches (
    id INTEGER PRIMARY KEY,
    file_hash TEXT NOT NULL CHECK (length(file_hash) = 64),
    file_name TEXT NOT NULL,
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    total_rows INTEGER NOT NULL CHECK (total_rows >= 0),
    imported_rows INTEGER NOT NULL CHECK (imported_rows >= 0),
    rejected_rows INTEGER NOT NULL CHECK (rejected_rows >= 0),
    status TEXT NOT NULL CHECK (status IN ('imported', 'partial', 'rejected')),
    CHECK (total_rows = imported_rows + rejected_rows)
);
CREATE UNIQUE INDEX IF NOT EXISTS imported_file_hash
    ON import_batches(file_hash) WHERE imported_rows > 0;

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY,
    import_id INTEGER NOT NULL REFERENCES import_batches(id),
    transaction_date TEXT NOT NULL,
    description TEXT NOT NULL CHECK (length(description) > 0),
    merchant TEXT,
    category TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('expense', 'income')),
    amount_minor INTEGER NOT NULL CHECK (typeof(amount_minor) = 'integer' AND amount_minor > 0),
    currency TEXT NOT NULL CHECK (currency = 'INR'),
    categorization_method TEXT NOT NULL,
    needs_review INTEGER NOT NULL CHECK (needs_review IN (0, 1)),
    potential_duplicate INTEGER NOT NULL CHECK (potential_duplicate IN (0, 1)),
    reference_id TEXT
);
CREATE INDEX IF NOT EXISTS transaction_dates ON transactions(transaction_date);
CREATE INDEX IF NOT EXISTS transaction_categories ON transactions(category);
CREATE INDEX IF NOT EXISTS transaction_types ON transactions(type);
CREATE INDEX IF NOT EXISTS transaction_references ON transactions(reference_id)
    WHERE reference_id IS NOT NULL;
CREATE TABLE IF NOT EXISTS monthly_budgets (
    id INTEGER PRIMARY KEY,
    month TEXT NOT NULL CHECK (
        month GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]'
        AND substr(month, 1, 4) <> '0000'
        AND substr(month, 6, 2) BETWEEN '01' AND '12'
    ),
    category TEXT NOT NULL CHECK (length(category) > 0 AND category = trim(lower(category))),
    budget_minor INTEGER NOT NULL CHECK (typeof(budget_minor) = 'integer' AND budget_minor >= 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (month, category)
);
"""


def connect(path: Path | None = None, *, read_only: bool = False) -> sqlite3.Connection:
    """Open the local database. Callers own the connection and its lifetime."""
    path = DB_PATH if path is None else Path(path)
    if read_only:
        connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
    else:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        connection = sqlite3.connect(path, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize(path: Path | None = None) -> None:
    with closing(connect(path)) as connection:
        connection.executescript(SCHEMA)


def fetch_rows(sql: str, parameters: tuple) -> list[sqlite3.Row]:
    """Run an analytics query without creating or modifying a database."""
    if not DB_PATH.is_file():
        return []
    with closing(connect(read_only=True)) as connection:
        return connection.execute(sql, parameters).fetchall()
