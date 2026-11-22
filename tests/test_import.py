import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from openpyxl import Workbook

from finance_agent import database
from finance_agent.import_service import import_statement

SAMPLE = Path(__file__).resolve().parents[1] / "sample_data" / "sample_statement.csv"


class StatementImportTest(unittest.TestCase):
    def setUp(self):
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.db = self.folder / "transactions.sqlite3"

    def write_statement(self, name, rows):
        path = self.folder / name
        path.write_text("date,description,debit,credit,reference_id\n" + rows)
        return path

    def test_csv_persists_and_exact_file_hash_skips_renamed_copy(self):
        summary = import_statement(SAMPLE, self.db)
        self.assertEqual(summary["imported_rows"], 6)
        copy = self.folder / "different_name.csv"
        copy.write_bytes(SAMPLE.read_bytes())
        self.assertTrue(import_statement(copy, self.db)["already_imported"])
        with closing(database.connect(self.db, read_only=True)) as connection:
            rows = connection.execute(
                "SELECT amount_minor, type FROM transactions ORDER BY id"
            ).fetchall()
            self.assertEqual(len(rows), 6)
            self.assertEqual(tuple(rows[0]), (45000, "expense"))
            self.assertEqual(tuple(rows[3]), (6000000, "income"))
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM import_batches").fetchone()[0], 1)

    def test_xlsx_persistence(self):
        path = self.folder / "statement.xlsx"
        workbook = Workbook()
        workbook.active.append(("date", "description", "debit", "credit"))
        workbook.active.append(("2026-10-03", "Swiggy", 10.25, None))
        workbook.save(path)
        workbook.close()
        self.assertEqual(import_statement(path, self.db)["imported_rows"], 1)
        with closing(database.connect(self.db, read_only=True)) as connection:
            row = connection.execute("SELECT category, amount_minor FROM transactions").fetchone()
            self.assertEqual(tuple(row), ("food", 1025))

    def test_partial_import_sanitizes_errors_and_skips_identical_retry(self):
        statement = self.write_statement(
            "partial.csv", "2026-10-03,Unknown shop,1.50,,\n"
            "2026-10-04,PRIVATE DESCRIPTION,PRIVATE AMOUNT,,\n",
        )
        result = import_statement(statement, self.db)
        self.assertEqual(result["total_rows"], 2)
        self.assertEqual(result["rejected_rows"], 1)
        self.assertEqual(result["uncategorized_transactions"], 1)
        self.assertEqual(result["errors"][0]["row"], 3)
        self.assertNotIn("PRIVATE", str(result))
        self.assertTrue(import_statement(statement, self.db)["already_imported"])
        with closing(database.connect(self.db, read_only=True)) as connection:
            self.assertEqual(connection.execute("SELECT status FROM import_batches").fetchone()[0], "partial")

    def test_overlap_flags_preserve_legitimate_repeats_and_reference_ids(self):
        first = self.write_statement(
            "first.csv", "2026-10-01,UBER,10,,REF-01\n2026-10-01,UBER,10,,REF-02\n",
        )
        second = self.write_statement(
            "second.csv", "2026-10-01,UBER TRIP,10,,REF-01\n"
            "2026-10-01,Uber,10,,\n2026-10-01,SWIGGY,10,,\n",
        )
        self.assertEqual(import_statement(first, self.db)["potential_duplicates"], 0)
        summary = import_statement(second, self.db)
        self.assertEqual(summary["potential_duplicates"], 2)
        self.assertEqual(summary["imported_rows"], 3)
        with closing(database.connect(self.db, read_only=True)) as connection:
            rows = connection.execute(
                "SELECT reference_id, potential_duplicate, needs_review FROM transactions ORDER BY id"
            ).fetchall()
            self.assertEqual([tuple(row) for row in rows], [
                ("REF-01", 0, 0), ("REF-02", 0, 0), ("REF-01", 1, 1),
                (None, 1, 1), (None, 0, 0),
            ])

    def test_failed_transaction_rolls_back_rows_and_metadata(self):
        from finance_agent.categorizer import categorize

        def invalid_second_row(description, transaction_type):
            result = categorize(description, transaction_type)
            if description == "UBER TRIP":
                result["category"] = None
            return result

        with patch("finance_agent.import_service.categorize", side_effect=invalid_second_row):
            with self.assertRaises(sqlite3.IntegrityError):
                import_statement(SAMPLE, self.db)
        with closing(database.connect(self.db, read_only=True)) as connection:
            self.assertIsNone(connection.execute("SELECT id FROM transactions").fetchone())
            self.assertIsNone(connection.execute("SELECT id FROM import_batches").fetchone())
        self.assertEqual(import_statement(SAMPLE, self.db)["imported_rows"], 6)

    def test_concurrent_identical_import(self):
        with ThreadPoolExecutor(max_workers=2) as executor:
            imports = list(executor.map(lambda _: import_statement(SAMPLE, self.db), range(2)))
        self.assertEqual(sorted(result["imported_rows"] for result in imports), [0, 6])
        self.assertEqual(sum(result["already_imported"] for result in imports), 1)
