"""Create a private SQLite backup of financial data and ADK conversations."""

import argparse
import os
import sqlite3
from contextlib import closing
from pathlib import Path

from finance_agent.database import DB_PATH

FILES = {
    "transactions.sqlite3": {"transactions", "import_batches"},
    "chat_sessions.sqlite3": {"sessions"},
}


def snapshot(source: Path, destination: Path, tables: set[str]) -> None:
    if source.is_symlink() or not source.is_file():
        raise ValueError("A required SQLite database is missing or is a symlink.")
    descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    try:
        with (
            closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as reader,
            closing(sqlite3.connect(destination)) as writer,
        ):
            reader.backup(writer, pages=128)
            present = {row[0] for row in writer.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            if not tables <= present or writer.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                raise ValueError("A database failed validation.")
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def backup(source: Path, output: Path) -> None:
    source, output = source.resolve(), output.resolve()
    if output.is_relative_to(source):
        raise ValueError("Choose a backup directory outside the primary data directory.")
    output.mkdir(mode=0o700)
    try:
        for name, tables in FILES.items():
            snapshot(source / name, output / name, tables)
    except Exception:
        for name in FILES:
            (output / name).unlink(missing_ok=True)
        output.rmdir()
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DB_PATH.parent)
    parser.add_argument("--output", type=Path, required=True, help="A new directory outside the data directory.")
    args = parser.parse_args()
    try:
        backup(args.source, args.output)
    except (OSError, sqlite3.Error, ValueError) as error:
        parser.exit(1, f"Backup failed: {error if isinstance(error, ValueError) else 'check SQLite files and directory permissions.'}\n")
    print("Verified database snapshots written. Store them in a private location.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
