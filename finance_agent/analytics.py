"""Read-only historical analytics with calculations in integer paise."""

import re
from decimal import Decimal

from .database import fetch_rows


def validate_month(month: str) -> dict | None:
    if (
        not isinstance(month, str)
        or not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", month)
        or month.startswith("0000-")
    ):
        return {"error": "Enter a valid month in YYYY-MM format, e.g. 2026-10."}
    return None


def in_rupees(amount_minor: int) -> int | float:
    if amount_minor % 100 == 0:
        return amount_minor // 100
    return amount_minor / 100


def percent(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return float(round(Decimal(numerator) * 100 / denominator, 2))


def shift_month(month: str, offset: int) -> str | None:
    year, number = map(int, month.split("-"))
    year, zero_based = divmod(year * 12 + number - 1 + offset, 12)
    if 1 <= year <= 9999:
        return f"{year:04d}-{zero_based + 1:02d}"
    return None


def monthly_rows(month: str) -> list:
    return fetch_rows(
        """
        SELECT type, category, SUM(amount_minor) AS amount, COUNT(*) AS row_count
        FROM transactions
        WHERE transaction_date BETWEEN ? AND ?
        GROUP BY type, category
        ORDER BY category
        """,
        (f"{month}-01", f"{month}-31"),
    )


def expense_categories(rows: list) -> dict[str, int]:
    return {row["category"]: row["amount"] for row in rows if row["type"] == "expense"}


def get_monthly_spending_trend(months: int = 6) -> dict:
    """Return monthly expenses, income, and cash flow ending at the latest imported month."""
    if type(months) is not int or not 1 <= months <= 24:
        return {"error": "Months must be an integer from 1 to 24."}
    result = {
        "anchor": "latest_imported_month", "end_month": None, "status": "insufficient_data",
        "months": [], "currency": "INR",
    }
    latest = fetch_rows("SELECT MAX(transaction_date) AS latest FROM transactions", ())
    if not latest or latest[0]["latest"] is None:
        return result
    end = latest[0]["latest"][:7]
    periods = [
        period for offset in range(1 - months, 1)
        if (period := shift_month(end, offset)) is not None
    ]
    rows = fetch_rows(
        """
        SELECT substr(transaction_date, 1, 7) AS month, type, SUM(amount_minor) AS amount
        FROM transactions WHERE transaction_date BETWEEN ? AND ?
        GROUP BY month, type
        """,
        (f"{periods[0]}-01", f"{end}-31"),
    )
    totals = {}
    for row in rows:
        totals.setdefault(row["month"], {})[row["type"]] = row["amount"]

    for period in periods:
        amounts = totals.get(period)
        if amounts is None:
            result["months"].append({
                "month": period, "status": "no_records", "total_expenses": None,
                "total_income": None, "net_cash_flow": None,
            })
            continue
        expenses = amounts.get("expense", 0)
        income = amounts.get("income", 0)
        result["months"].append({
            "month": period, "status": "has_records", "total_expenses": in_rupees(expenses),
            "total_income": in_rupees(income), "net_cash_flow": in_rupees(income - expenses),
        })
    result.update(end_month=end, status="ok")
    return result


def compare_monthly_expenses(month1: str, month2: str) -> dict:
    """Compare imported expenses for two YYYY-MM months; month1 is the baseline."""
    for month in (month1, month2):
        if error := validate_month(month):
            return error
    first = monthly_rows(month1)
    second = first if month1 == month2 else monthly_rows(month2)
    before = sum(expense_categories(first).values()) if first else None
    after = sum(expense_categories(second).values()) if second else None
    result = {
        "month1": month1, "month2": month2, "currency": "INR",
        "month1_expenses": in_rupees(before) if before is not None else None,
        "month2_expenses": in_rupees(after) if after is not None else None,
        "absolute_difference": None, "change_percent": None,
        "status": "insufficient_data",
        "missing_months": sorted({month for month, rows in ((month1, first), (month2, second))
                                  if not rows}),
    }
    if before is None or after is None:
        return result
    change = after - before
    result.update(
        absolute_difference=in_rupees(abs(change)),
        change_percent=percent(change, before),
        status="increase" if change > 0 else "decrease" if change < 0 else "unchanged",
        zero_baseline=before == 0,
    )
    return result
