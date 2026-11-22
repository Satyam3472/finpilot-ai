import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from finance_agent import database
from finance_agent.budget import set_budget
from finance_agent.import_service import import_statement
from finance_agent.tools import (
    compare_monthly_expenses,
    get_monthly_spending_trend,
    get_savings_opportunities,
)

SAMPLE = Path(__file__).resolve().parents[1] / "sample_data" / "analytics_statement.csv"


class HistoricalAnalyticsTest(unittest.TestCase):
    def setUp(self):
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(patch.object(database, "DB_PATH", self.folder / "analytics.sqlite3"))
        import_statement(SAMPLE)

    def test_trend_anchors_to_latest_and_preserves_missing_month(self):
        trend = get_monthly_spending_trend(4)
        self.assertEqual(trend["anchor"], "latest_imported_month")
        self.assertEqual(trend["end_month"], "2026-10")
        months = trend["months"]
        self.assertEqual([row["month"] for row in months], [
            "2026-07", "2026-08", "2026-09", "2026-10",
        ])
        self.assertEqual([row["total_expenses"] for row in months], [2220, None, 2520, 5312])
        self.assertEqual(months[1]["status"], "no_records")
        self.assertIsNone(months[1]["total_income"])
        self.assertEqual(months[-1]["total_income"], 60000)
        self.assertEqual(months[-1]["net_cash_flow"], 54688)

    def test_comparison_amount_percentage_and_directions(self):
        result = compare_monthly_expenses("2026-09", "2026-10")
        self.assertEqual(result["month1_expenses"], 2520)
        self.assertEqual(result["month2_expenses"], 5312)
        self.assertEqual(result["absolute_difference"], 2792)
        self.assertEqual(result["change_percent"], 110.79)
        self.assertEqual(result["status"], "increase")
        reverse = compare_monthly_expenses("2026-10", "2026-09")
        self.assertEqual(reverse["status"], "decrease")
        self.assertEqual(reverse["absolute_difference"], 2792)
        self.assertEqual(reverse["change_percent"], -52.56)
        self.assertEqual(compare_monthly_expenses("2026-09", "2026-09")["status"], "unchanged")

    def test_missing_months_are_not_zero(self):
        result = compare_monthly_expenses("2026-08", "2026-10")
        self.assertEqual(result["status"], "insufficient_data")
        self.assertEqual(result["missing_months"], ["2026-08"])
        self.assertIsNone(result["month1_expenses"])
        self.assertIsNone(result["change_percent"])

    def test_income_only_baseline_has_undefined_percentage(self):
        path = self.folder / "credit.csv"
        path.write_text("date,description,debit,credit\n2026-08-01,SALARY,,60\n")
        import_statement(path)
        result = compare_monthly_expenses("2026-08", "2026-09")
        self.assertEqual(result["month1_expenses"], 0)
        self.assertTrue(result["zero_baseline"])
        self.assertEqual(result["status"], "increase")
        self.assertIsNone(result["change_percent"])

    def test_invalid_inputs_and_empty_database(self):
        self.assertIn("error", compare_monthly_expenses("2026-09", "2026-13"))
        for value in (0, 25, True, 2.0, "6"):
            with self.subTest(value=value):
                self.assertIn("error", get_monthly_spending_trend(value))
        with patch.object(database, "DB_PATH", self.folder / "missing.sqlite3"):
            result = get_monthly_spending_trend()
            self.assertEqual(result["status"], "insufficient_data")
            self.assertEqual(result["months"], [])
            self.assertFalse(database.DB_PATH.exists())

    def test_savings_opportunities_use_budget_and_history(self):
        set_budget("2026-10", "food", "2000")
        set_budget("2026-10", "shopping", "1700")
        set_budget("2026-10", "travel", "0")
        result = get_savings_opportunities("2026-10")
        evidence = {(item["category"], item["type"]): item["evidence"]
                    for item in result["observations"]}
        self.assertEqual(result["comparison_status"], "available")
        self.assertEqual(evidence["food", "over_budget"]["spent"], 2112)
        self.assertEqual(evidence["shopping", "near_or_at_budget"]["budget"], 1700)
        self.assertEqual(evidence["shopping", "rising_discretionary_spending"], {
            "spent": 1500, "previous_spent": 1200, "increase": 300, "change_percent": 25,
        })
        self.assertIsNone(evidence["travel", "over_budget"]["utilization_percent"])

    def test_savings_opportunities_report_missing_evidence(self):
        self.assertEqual(get_savings_opportunities("2026-08")["status"], "insufficient_data")
        result = get_savings_opportunities("2026-09")
        self.assertEqual(result["comparison_status"], "insufficient_data")
        self.assertEqual(result["budget_status"], "not_configured")
        self.assertEqual(result["observations"], [])
