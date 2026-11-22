"""Import a local statement as one SQLite transaction."""

from contextlib import closing
from hashlib import sha256
from pathlib import Path

from . import database
from .categorizer import categorize
from .parser import parse_statement, read_statement

FIND_IMPORT = "SELECT 1 FROM import_batches WHERE file_hash = ? AND imported_rows > 0"

FIND_OVERLAP = """
SELECT 1 FROM transactions
WHERE import_id <> :import_id AND (
    reference_id = :reference_id
    OR (transaction_date = :transaction_date AND type = :type
        AND amount_minor = :amount_minor AND description = :description COLLATE NOCASE)
)
LIMIT 1
"""

INSERT_TRANSACTION = """
INSERT INTO transactions (
    import_id, transaction_date, description, merchant, category, type, amount_minor, currency,
    categorization_method, needs_review, potential_duplicate, reference_id
) VALUES (
    :import_id, :transaction_date, :description, :merchant, :category, :type, :amount_minor,
    :currency, :categorization_method, :needs_review, :potential_duplicate, :reference_id
)
"""


def import_statement(path: Path, db_path: Path | None = None) -> dict:
    """Store valid records and return counts and sanitized row errors."""
    path = Path(path)
    content = read_statement(path)
    file_hash = sha256(content).hexdigest()
    result = parse_statement(path, content)
    records = result["records"]
    for record in records:
        record.update(categorize(record["description"], record["type"]))

    summary = {
        "total_rows": result["total_rows"],
        "imported_rows": 0,
        "rejected_rows": 0,
        "uncategorized_transactions": 0,
        "potential_duplicates": 0,
        "already_imported": False,
        "errors": [],
    }
    database.initialize(db_path)
    with closing(database.connect(db_path)) as connection, connection:
        # Acquire the write lock before checking the hash or looking for overlaps.
        connection.execute("BEGIN IMMEDIATE")
        if connection.execute(FIND_IMPORT, (file_hash,)).fetchone():
            summary["already_imported"] = True
            return summary

        summary["rejected_rows"] = len(result["errors"])
        summary["errors"] = result["errors"]
        summary["imported_rows"] = len(records)
        status = "rejected"
        if records:
            status = "partial" if result["errors"] else "imported"
        batch = connection.execute(
            """
            INSERT INTO import_batches
                (file_hash, file_name, total_rows, imported_rows, rejected_rows, status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (file_hash, path.name, result["total_rows"], len(records), len(result["errors"]), status),
        )
        for record in records:
            record["import_id"] = batch.lastrowid
            overlap = connection.execute(FIND_OVERLAP, record).fetchone() is not None
            record["potential_duplicate"] = overlap
            record["needs_review"] = record["needs_review"] or overlap
            connection.execute(INSERT_TRANSACTION, record)
            summary["potential_duplicates"] += overlap
            summary["uncategorized_transactions"] += record["category"] == "uncategorized"
    return summary
