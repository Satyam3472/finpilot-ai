"""Deterministic SQLite analytics exposed to Google ADK."""

from .analytics import (
    compare_monthly_expenses,
    get_monthly_spending_trend,
    in_rupees,
    monthly_rows,
    validate_month,
)
from .anomaly import detect_unusual_transactions
from .budget import calculate_remaining_budget, get_budget_summary, get_budget_utilization
from .database import fetch_rows
from .insights import get_savings_opportunities


def _missing_month(month: str) -> dict:
    return {"month": month, "error": "No imported records for this month."}


def get_total_expenses(month: str) -> dict:
    """Return the total and count of imported expenses for a YYYY-MM month."""
    if error := validate_month(month):
        return error
    rows = monthly_rows(month)
    if not rows:
        return _missing_month(month)
    expenses = [row for row in rows if row["type"] == "expense"]
    return {
        "month": month,
        "total_expenses": in_rupees(sum(row["amount"] for row in expenses)),
        "transaction_count": sum(row["row_count"] for row in expenses),
        "currency": "INR",
    }


def get_expenses_by_category(month: str) -> dict:
    """Return imported expense totals grouped by category for a YYYY-MM month."""
    if error := validate_month(month):
        return error
    rows = monthly_rows(month)
    if not rows:
        return _missing_month(month)
    return {
        "month": month,
        "category_totals": {
            row["category"]: in_rupees(row["amount"])
            for row in rows
            if row["type"] == "expense"
        },
        "currency": "INR",
    }


def get_largest_transactions(limit: int = 5) -> dict:
    """Return the largest imported expenses across all periods, with a limit of 1–20."""
    if type(limit) is not int or not 1 <= limit <= 20:
        return {"error": "Limit must be an integer from 1 to 20."}
    rows = fetch_rows(
        """
        SELECT transaction_date, category, amount_minor FROM transactions
        WHERE type = ? ORDER BY amount_minor DESC, transaction_date, id LIMIT ?
        """,
        ("expense", limit),
    )
    return {
        "transactions": [
            {
                "date": row["transaction_date"],
                "category": row["category"],
                "amount": in_rupees(row["amount_minor"]),
            }
            for row in rows
        ],
        "currency": "INR",
    }


def get_transaction_summary(month: str) -> dict:
    """Return imported income, expenses, and net cash flow for a YYYY-MM month."""
    if error := validate_month(month):
        return error
    rows = monthly_rows(month)
    if not rows:
        return _missing_month(month)
    income = sum(row["amount"] for row in rows if row["type"] == "income")
    categories = {
        row["category"]: row["amount"] for row in rows if row["type"] == "expense"
    }
    expenses = sum(categories.values())
    return {
        "month": month,
        "total_income": in_rupees(income),
        "total_expenses": in_rupees(expenses),
        "net_cash_flow": in_rupees(income - expenses),
        "expense_category_breakdown": {
            category: in_rupees(amount) for category, amount in categories.items()
        },
        "transaction_count": sum(row["row_count"] for row in rows),
        "currency": "INR",
    }
