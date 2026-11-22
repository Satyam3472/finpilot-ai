"""Command-line entry point for local CSV and XLSX imports."""

import argparse
import sqlite3
from pathlib import Path

from finance_agent.import_service import import_statement
from finance_agent.parser import StatementError


def main() -> int:
    parser = argparse.ArgumentParser(description="Import a local CSV or XLSX bank statement.")
    parser.add_argument("statement", type=Path)
    args = parser.parse_args()
    try:
        summary = import_statement(args.statement)
    except StatementError as error:
        parser.exit(1, f"Import failed: {error}\n")
    except (OSError, sqlite3.Error):
        parser.exit(1, "Import failed: unable to write to the local transaction database.\n")

    if summary["already_imported"]:
        print("Identical statement already imported. No transactions added.")
        return 0

    print(
        f"Rows: {summary['total_rows']} | Imported: {summary['imported_rows']} | "
        f"Rejected: {summary['rejected_rows']} | "
        f"Uncategorized: {summary['uncategorized_transactions']} | "
        f"Potential overlaps: {summary['potential_duplicates']}"
    )
    for error in summary["errors"]:
        print(f"Row {error['row']}: {error['error']}")
    return 0 if summary["imported_rows"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
