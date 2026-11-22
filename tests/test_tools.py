import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from finance_agent import database
from finance_agent.budget import seed_legacy_budgets, set_budget
from finance_agent.import_service import import_statement
from finance_agent.tools import (
    calculate_remaining_budget,
    get_expenses_by_category,
    get_largest_transactions,
    get_total_expenses,
    get_transaction_summary,
)

SAMPLE = Path(__file__).resolve().parents[1] / "sample_data" / "sample_statement.csv"
CATEGORIES = {"entertainment": 649, "food": 800, "shopping": 2499, "travel": 280}


class FinanceToolsTest(unittest.TestCase):
    def setUp(self):
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(patch.object(database, "DB_PATH", self.folder / "transactions.sqlite3"))
        import_statement(SAMPLE)
        seed_legacy_budgets()

    def test_total_expenses_excludes_income(self):
        self.assertEqual(get_total_expenses("2026-10"), {
            "month": "2026-10", "total_expenses": 4228,
            "transaction_count": 5, "currency": "INR",
        })

    def test_category_expenses(self):
        self.assertEqual(get_expenses_by_category("2026-10"), {
            "month": "2026-10", "category_totals": CATEGORIES, "currency": "INR",
        })

    def test_largest_transactions_order_limit_and_privacy(self):
        self.assertEqual(get_largest_transactions(3), {
            "transactions": [
                {"date": "2026-10-07", "category": "shopping", "amount": 2499},
                {"date": "2026-10-12", "category": "entertainment", "amount": 649},
                {"date": "2026-10-02", "category": "food", "amount": 450},
            ],
            "currency": "INR",
        })
        self.assertEqual(len(get_largest_transactions()["transactions"]), 5)
        self.assertEqual(len(get_largest_transactions(20)["transactions"]), 5)

    def test_remaining_food_budget_normalizes_category(self):
        self.assertEqual(calculate_remaining_budget("  FoOd  "), {
            "month": "2026-10", "category": "food", "budget": 8000,
            "spent": 800, "remaining": 7200, "status": "within_budget",
            "currency": "INR",
        })

    def test_budget_status_at_and_above_allocation(self):
        for budget, status in ((800, "within_budget"), (799, "over_budget")):
            with self.subTest(budget=budget):
                set_budget("2026-10", "food", str(budget))
                result = calculate_remaining_budget("food")
                self.assertEqual(result["remaining"], budget - 800)
                self.assertEqual(result["status"], status)

    def test_monthly_cash_flow_summary(self):
        self.assertEqual(get_transaction_summary("2026-10"), {
            "month": "2026-10", "total_income": 60000, "total_expenses": 4228,
            "net_cash_flow": 55772, "expense_category_breakdown": CATEGORIES,
            "transaction_count": 6, "currency": "INR",
        })

    def test_income_only_month_and_fractional_rupees(self):
        source = self.folder / "additional.csv"
        source.write_text(
            "date,description,debit,credit\n2026-11-01,Transfer,,1.15\n"
            "2026-12-01,Uber,0.37,\n"
        )
        import_statement(source)
        self.assertEqual(get_total_expenses("2026-11")["total_expenses"], 0)
        self.assertEqual(get_expenses_by_category("2026-11")["category_totals"], {})
        self.assertEqual(get_transaction_summary("2026-11")["net_cash_flow"], 1.15)
        self.assertEqual(get_total_expenses("2026-12")["total_expenses"], 0.37)
        self.assertEqual(get_transaction_summary("2026-12")["net_cash_flow"], -0.37)

    def test_invalid_month(self):
        for tool in (get_total_expenses, get_expenses_by_category, get_transaction_summary):
            for month in ("2026-1", "2026-00", "2026-13", "0000-01", "October", None):
                with self.subTest(tool=tool.__name__, month=month):
                    self.assertIn("YYYY-MM", tool(month)["error"])

    def test_invalid_limit_and_unknown_category(self):
        for limit in (0, 21, True, 3.0, "3", None):
            with self.subTest(limit=limit):
                self.assertIn("integer from 1 to 20", get_largest_transactions(limit)["error"])
        self.assertIn("Unknown category", calculate_remaining_budget("fuel")["error"])
        self.assertIn("Category must be text", calculate_remaining_budget(None)["error"])

    def test_unimported_month_or_database(self):
        expected = {"month": "2026-09", "error": "No imported records for this month."}
        self.assertEqual(get_total_expenses("2026-09"), expected)
        self.assertEqual(get_expenses_by_category("2026-09"), expected)
        self.assertEqual(get_transaction_summary("2026-09"), expected)

        missing = self.folder / "missing.sqlite3"
        with patch.object(database, "DB_PATH", missing):
            self.assertIn("error", calculate_remaining_budget("food"))
            self.assertEqual(get_largest_transactions()["transactions"], [])
            self.assertFalse(missing.exists())
