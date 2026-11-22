"""Local categorization rules for normalized bank transactions."""

import re

MERCHANTS = {
    "food": ("Zomato", "Swiggy"),
    "travel": ("Uber", "Ola", "Rapido", "IRCTC"),
    "shopping": ("Amazon", "Flipkart", "Myntra"),
    "entertainment": ("Netflix", "Spotify"),
}
KEYWORDS = {
    "bills": ("electricity", "broadband", "recharge"),
    "rent": ("house rent", "flat rent"),
    "healthcare": ("pharmacy", "hospital"),
}


def categorize(description: str, transaction_type: str) -> dict:
    """Return category, known merchant, rule provenance, and review status."""
    words = " ".join(re.findall(r"\w+", description.casefold().replace("_", " ")))
    if transaction_type == "income":
        return _result("income", "transaction_type")

    for category, merchants in MERCHANTS.items():
        for merchant in merchants:
            if f" {merchant.casefold()} " in f" {words} ":
                return _result(category, "merchant_rule", merchant)

    for category, keywords in KEYWORDS.items():
        if any(f" {keyword} " in f" {words} " for keyword in keywords):
            return _result(category, "keyword_rule")

    # A future optional categorizer can handle this review queue.
    return _result("uncategorized", "unmatched", needs_review=True)


def _result(
    category: str, method: str, merchant: str | None = None, needs_review: bool = False
) -> dict:
    return {
        "category": category,
        "merchant": merchant,
        "categorization_method": method,
        "needs_review": needs_review,
    }
