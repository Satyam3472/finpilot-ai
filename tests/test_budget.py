import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from finance_agent import database
from finance_agent.budget import delete_budget, list_budgets, seed_legacy_budgets, set_budget
from finance_agent.import_service import import_statement
from finance_agent.tools import (
    calculate_remaining_budget,
    get_budget_summary,
    get_budget_utilization,
    get_total_expenses,
)

SAMPLE = Path(__file__).resolve().parents[1] / "sample_data" / "analytics_statement.csv"


class BudgetTest(unittest.TestCase):
    def setUp(self):
        folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(patch.object(database, "DB_PATH", folder / "budgets.sqlite3"))
        import_statement(SAMPLE)

    def test_upsert_lists_integer_paise_and_delete(self):
        set_budget("2026-10", " FOOD ", "2,000.25")
        set_budget("2026-10", "Food", "2100.10")
        set_budget("2026-11", "food", "3000")
        self.assertEqual(list_budgets("2026-10"), [
            {"month": "2026-10", "category": "food", "budget_minor": 210010},
        ])
        self.assertEqual(len(list_budgets()), 2)
        self.assertTrue(delete_budget("2026-10", "food"))
        self.assertFalse(delete_budget("2026-10", "food"))
        self.assertEqual(list_budgets("2026-10"), [])
        self.assertEqual(len(list_budgets("2026-11")), 1)

    def test_database_rejects_duplicate_and_negative_values(self):
        set_budget("2026-10", "food", "1")
        with closing(database.connect()) as connection:
            insert = "INSERT INTO monthly_budgets (month, category, budget_minor) VALUES (?, ?, ?)"
            for values in (("2026-10", "food", 100), ("2026-10", "travel", -1),
                           ("2026-10", "shopping", 1.1)):
                with self.subTest(values=values):
                    with self.assertRaises(sqlite3.IntegrityError):
                        connection.execute(insert, values)

    def test_cli_backend_rejects_bad_input(self):
        for amount in ("-1", "  ", "NaN", "1e2", "0.001"):
            with self.subTest(amount=amount):
                with self.assertRaises(ValueError):
                    set_budget("2026-10", "food", amount)
        with self.assertRaises(ValueError):
            set_budget("2026-13", "food", "100")
        with self.assertRaises(ValueError):
            set_budget("2026-10", "income", "100")
        self.assertEqual(list_budgets(), [])

    def test_monthly_utilization_remaining_and_overspending(self):
        set_budget("2026-10", "food", "2000")
        set_budget("2026-10", "shopping", "2000")
        result = get_budget_utilization("2026-10", " Food ")
        self.assertEqual(result["status"], "over_budget")
        self.assertEqual((result["spent"], result["remaining"], result["utilization_percent"]),
                         (2112, -112, 105.6))
        summary = get_budget_summary("2026-10")
        self.assertEqual(summary["budgets"][0], result)
        self.assertEqual(summary["budgets"][1]["remaining"], 500)
        self.assertEqual(summary["budgets"][1]["status"], "within_budget")

    def test_zero_missing_and_unobserved_budgets(self):
        set_budget("2026-10", "travel", "0")
        set_budget("2026-10", "rent", "0")
        set_budget("2026-08", "travel", "500")
        travel = get_budget_utilization("2026-10", "travel")
        self.assertEqual(travel["budget"], 0)
        self.assertEqual(travel["status"], "over_budget")
        self.assertIsNone(travel["utilization_percent"])
        self.assertEqual(get_budget_utilization("2026-10", "rent")["status"], "within_budget")
        missing = get_budget_utilization("2026-09", "travel")
        self.assertEqual(missing["status"], "not_configured")
        self.assertIsNone(missing["budget"])
        self.assertEqual(missing["spent"], 400)
        unobserved = get_budget_utilization("2026-08", "travel")
        self.assertEqual(unobserved["status"], "insufficient_data")
        self.assertIsNone(unobserved["spent"])
        self.assertIsNone(unobserved["remaining"])

    def test_existing_database_read_and_idempotent_upgrade(self):
        # Recreate the exact state of an existing database before the additive migration.
        with closing(database.connect()) as connection, connection:
            connection.execute("DROP TABLE monthly_budgets")
        self.assertEqual(get_budget_utilization("2026-10", "food")["status"], "not_configured")
        with closing(database.connect(read_only=True)) as connection:
            self.assertIsNone(connection.execute(
                "SELECT name FROM sqlite_master WHERE type = ? AND name = ?",
                ("table", "monthly_budgets"),
            ).fetchone())
        set_budget("2026-10", "food", "3000")
        database.initialize()
        self.assertEqual(get_total_expenses("2026-10")["total_expenses"], 5312)
        with closing(database.connect(read_only=True)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM import_batches").fetchone()[0], 1)
        self.assertEqual(calculate_remaining_budget("food")["remaining"], 888)

    def test_legacy_seed_is_explicit_and_preserves_edits(self):
        self.assertEqual(calculate_remaining_budget("food")["status"], "not_configured")
        set_budget("2026-10", "food", "3500")
        self.assertEqual(seed_legacy_budgets(), 5)
        self.assertEqual(seed_legacy_budgets(), 0)
        self.assertEqual(calculate_remaining_budget("food")["budget"], 3500)
        delete_budget("2026-10", "food")
        self.assertEqual(calculate_remaining_budget("food")["status"], "not_configured")
