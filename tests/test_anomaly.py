import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from finance_agent import database
from finance_agent.import_service import import_statement
from finance_agent.tools import detect_unusual_transactions

SAMPLE = Path(__file__).resolve().parents[1] / "sample_data" / "analytics_statement.csv"


class AnomalyTest(unittest.TestCase):
    def setUp(self):
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(patch.object(database, "DB_PATH", self.folder / "anomaly.sqlite3"))
        import_statement(SAMPLE)

    def test_known_outlier_and_category_specific_limitations(self):
        result = detect_unusual_transactions("2026-10")
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["flagged_count"], 1)
        flag = result["unusual_transactions"][0]
        self.assertEqual((flag["date"], flag["category"], flag["amount"]), ("2026-10-03", "food", 2000))
        self.assertEqual(flag["method"], "modified_z_score")
        self.assertGreater(flag["score"], 3.5)
        self.assertNotIn("description", flag)
        self.assertIn("not evidence of fraud", result["note"])

        # Only the large food expense was flagged; the other food expense was evaluated.
        categories = result["categories"]
        self.assertEqual(categories["food"]["evaluated_count"], 2)
        self.assertEqual(categories["food"]["history_count"], 6)
        self.assertEqual(categories["food"]["median"], 107.5)
        self.assertEqual(categories["food"]["median_absolute_deviation"], 7.5)
        self.assertEqual(categories["travel"]["status"], "zero_mad")
        self.assertEqual(categories["healthcare"]["status"], "insufficient_data")
        self.assertNotIn("income", categories)

    def test_future_data_does_not_change_baseline_or_results(self):
        before = detect_unusual_transactions("2026-10")
        source = self.folder / "future.csv"
        source.write_text("date,description,debit,credit\n2026-11-01,SWIGGY,50000,\n")
        import_statement(source)
        self.assertEqual(detect_unusual_transactions("2026-10"), before)

    def test_missing_month_and_invalid_month(self):
        self.assertIn("error", detect_unusual_transactions("2026-13"))
        result = detect_unusual_transactions("2026-08")
        self.assertEqual(result["status"], "insufficient_data")
        self.assertEqual(result["unusual_transactions"], [])
        self.assertEqual(result["reason"], "No imported records.")

    def test_returned_flags_are_limited(self):
        source = self.folder / "many.csv"
        source.write_text(
            "date,description,debit,credit\n"
            + "".join(f"2026-10-15,ZOMATO ORDER,{3000 + i},\n" for i in range(22))
        )
        import_statement(source)
        result = detect_unusual_transactions("2026-10")
        self.assertEqual(result["flagged_count"], 23)
        self.assertEqual(len(result["unusual_transactions"]), 20)
        self.assertEqual(result["unusual_transactions"][0]["amount"], 3021)
