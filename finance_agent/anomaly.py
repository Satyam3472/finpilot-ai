"""Explain unusually large expenses using a prior, category-specific baseline."""

from collections import defaultdict
from statistics import median

from .analytics import in_rupees, shift_month, validate_month
from .database import fetch_rows

MIN_HISTORY = 5
THRESHOLD = 3.5
LOOKBACK_MONTHS = 12
RESULT_LIMIT = 20


def detect_unusual_transactions(month: str) -> dict:
    """Flag large expenses in YYYY-MM using modified Z-scores against prior same-category expenses."""
    if error := validate_month(month):
        return error
    start = shift_month(month, -LOOKBACK_MONTHS) or "0001-01"
    rows = fetch_rows(
        """
        SELECT transaction_date, type, category, amount_minor
        FROM transactions WHERE transaction_date BETWEEN ? AND ?
        ORDER BY transaction_date, id
        """,
        (f"{start}-01", f"{month}-31"),
    )
    history, candidates = defaultdict(list), defaultdict(list)
    has_records = False
    for row in rows:
        selected = row["transaction_date"].startswith(month)
        has_records |= selected
        if row["type"] == "expense":
            if selected:
                candidates[row["category"]].append(row)
            else:
                history[row["category"]].append(row["amount_minor"])

    result = {
        "month": month, "currency": "INR", "method": "modified_z_score",
        "threshold": THRESHOLD, "minimum_history": MIN_HISTORY,
        "baseline_start_month": start, "baseline_end_exclusive": month,
        "categories": {}, "unusual_transactions": [], "flagged_count": 0,
        "result_limit": RESULT_LIMIT,
        "note": "A statistical flag is a prompt for review, not evidence of fraud.",
    }
    if not candidates:
        result["status"] = "no_expenses" if has_records else "insufficient_data"
        result["reason"] = "No imported expenses." if has_records else "No imported records."
        return result

    flags = []
    for category, expenses in sorted(candidates.items()):
        amounts = history[category]
        baseline = {"history_count": len(amounts), "evaluated_count": 0}
        result["categories"][category] = baseline
        if category == "uncategorized":
            baseline.update(
                status="insufficient_data",
                reason="Uncategorized expenses do not have a reliable comparison group.",
            )
            continue
        if len(amounts) < MIN_HISTORY:
            baseline.update(status="insufficient_data", reason="Too few prior same-category expenses.")
            continue
        center = median(amounts)
        mad = median(abs(amount - center) for amount in amounts)
        baseline.update(median=in_rupees(center), median_absolute_deviation=in_rupees(mad))
        if mad == 0:
            baseline.update(status="zero_mad", reason="The baseline has zero median deviation; no score was computed.")
            continue
        baseline.update(status="evaluated", evaluated_count=len(expenses))
        for expense in expenses:
            amount = expense["amount_minor"]
            score = 0.6745 * (amount - center) / mad
            if score > THRESHOLD:
                flags.append((score, {
                    "date": expense["transaction_date"], "category": category,
                    "amount": in_rupees(amount), "method": "modified_z_score",
                    "score": round(score, 4),
                    "reason": "Amount exceeds the positive score threshold for prior same-category expenses.",
                }))
    evaluated = sum(item["evaluated_count"] for item in result["categories"].values())
    total = sum(len(expenses) for expenses in candidates.values())
    result["status"] = "ok" if evaluated == total else "partial" if evaluated else "insufficient_data"
    result["flagged_count"] = len(flags)
    result["unusual_transactions"] = [
        flag for _, flag in sorted(flags, key=lambda item: -item[0])[:RESULT_LIMIT]
    ]
    return result
