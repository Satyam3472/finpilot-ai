"""Validated HTTP adapters for existing financial calculations."""

from datetime import datetime, timezone, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response

from backend.schemas import BudgetSummary, BudgetWrite, Category, Dashboard, Month, minor, minor_fields
from finance_agent import analytics, anomaly, budget, insights, tools

router = APIRouter()
MONTHLY_AMOUNTS = ("total_income", "total_expenses", "net_cash_flow")


def budget_payload(month: str) -> dict:
    result = budget.get_budget_summary(month)
    result["budgets"] = [
        minor_fields(row, "budget", "spent", "remaining") for row in result["budgets"]
    ]
    result["categories"] = budget.CATEGORIES
    return result


@router.get("/dashboard/summary", response_model=Dashboard)
def dashboard(month: Month | None = None) -> dict:
    if month is None:
        latest = analytics.get_monthly_spending_trend(1)["end_month"]
        month = latest or datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m")
    summary = tools.get_transaction_summary(month)
    return {
        "month": month,
        "availability": "no_records" if "error" in summary else "has_records",
        "currency": "INR",
        "transaction_count": summary.get("transaction_count", 0),
        "category_totals_minor": {
            name: minor(amount) for name, amount in summary.get("expense_category_breakdown", {}).items()
        },
        "budget_summary": budget_payload(month),
        **{f"{field}_minor": minor(summary.get(field)) for field in MONTHLY_AMOUNTS},
    }


@router.get("/budgets", response_model=BudgetSummary)
def read_budgets(month: Month) -> dict:
    return budget_payload(month)


@router.put("/budgets/{month}/{category}", response_model=BudgetSummary)
def save_budget(month: Month, category: Category, body: BudgetWrite) -> dict:
    whole, paise = divmod(body.amount_minor, 100)
    try:
        budget.set_budget(month, category, f"{whole}.{paise:02d}")
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    return budget_payload(month)


@router.delete("/budgets/{month}/{category}", status_code=204)
def remove_budget(month: Month, category: Category) -> Response:
    try:
        deleted = budget.delete_budget(month, category)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    if not deleted:
        raise HTTPException(404, "That budget does not exist.")
    return Response(status_code=204)


@router.get("/analytics/trends")
def trends(months: Annotated[int, Query(ge=1, le=24)] = 6) -> dict:
    result = analytics.get_monthly_spending_trend(months)
    result["months"] = [minor_fields(row, *MONTHLY_AMOUNTS) for row in result["months"]]
    return result


@router.get("/analytics/comparison")
def comparison(month1: Month, month2: Month) -> dict:
    return minor_fields(
        analytics.compare_monthly_expenses(month1, month2),
        "month1_expenses", "month2_expenses", "absolute_difference",
    )


@router.get("/analytics/anomalies")
def anomalies(month: Month) -> dict:
    result = anomaly.detect_unusual_transactions(month)
    result["unusual_transactions"] = [
        minor_fields(row, "amount") for row in result["unusual_transactions"]
    ]
    # Statistical medians can fall between two paise values. Display them in INR
    # as reported by the detector, separately from actual transaction amounts.
    return result


@router.get("/insights/savings")
def savings(month: Month) -> dict:
    result = insights.get_savings_opportunities(month)
    amount_fields = {"spent", "budget", "previous_spent", "increase"}
    for item in result["observations"]:
        evidence = item["evidence"]
        item["evidence"] = minor_fields(evidence, *(field for field in evidence if field in amount_fields))
    return result
