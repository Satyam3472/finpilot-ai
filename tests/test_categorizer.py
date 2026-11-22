import unittest

from finance_agent.categorizer import categorize


class CategorizerTest(unittest.TestCase):
    def test_known_merchants(self):
        for description, category, merchant in (
            ("UPI/ZOMATO_ORDER", "food", "Zomato"),
            ("Payment to UBER", "travel", "Uber"),
            ("amazon shopping", "shopping", "Amazon"),
            ("Spotify subscription", "entertainment", "Spotify"),
        ):
            with self.subTest(description=description):
                self.assertEqual(categorize(description, "expense"), {
                    "category": category, "merchant": merchant,
                    "categorization_method": "merchant_rule", "needs_review": False,
                })

    def test_keyword_categories_do_not_invent_merchants(self):
        for description, category in (
            ("Electricity  payment", "bills"),
            ("flat-rent", "rent"),
            ("local pharmacy", "healthcare"),
        ):
            with self.subTest(description=description):
                result = categorize(description, "expense")
                self.assertEqual(result["category"], category)
                self.assertIsNone(result["merchant"])

    def test_credit_takes_precedence(self):
        self.assertEqual(categorize("AMAZON REFUND", "income")["category"], "income")

    def test_unknown_and_partial_matches_flagged(self):
        for description in ("LOCAL STORE", "COLA VENDOR", "UBERLICIOUS"):
            with self.subTest(description=description):
                self.assertEqual(categorize(description, "expense"), {
                    "category": "uncategorized", "merchant": None,
                    "categorization_method": "unmatched", "needs_review": True,
                })
