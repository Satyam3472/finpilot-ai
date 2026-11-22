"""Local budget configuration and read-only monthly budget analytics."""

from contextlib import closing

from . import database
from .analytics import expense_categories, in_rupees, monthly_rows, percent, validate_month
from .categorizer import KEYWORDS, MERCHANTS
from .data import MONTHLY_BUDGETS, SAMPLE_MONTH
from .parser import parse_amount_minor

CATEGORIES = sorted(MERCHANTS.keys() | KEYWORDS.keys() | {"uncategorized"})
UPSERT = """
INSERT INTO monthly_budgets (month, category, budget_minor) VALUES (?, ?, ?)
ON CONFLICT (month, category) DO UPDATE SET
    budget_minor = excluded.budget_minor, updated_at = CURRENT_TIMESTAMP
"""


def _normalize_category(category: str) -> str:
    if not isinstance(category, str):
        raise ValueError("Category must be text.")
    category = category.strip().lower()
    if category not in CATEGORIES:
        raise ValueError(f"Unknown category. Choose from: {', '.join(CATEGORIES)}.")
    return category


def _require_month(month: str) -> None:
    if error := validate_month(month):
        raise ValueError(error["error"])


def set_budget(month: str, category: str, amount: str) -> dict:
    """Create or update a budget through the local CLI."""
    _require_month(month)
    category = _normalize_category(category)
    if not isinstance(amount, str) or not amount.strip():
        raise ValueError("Provide a nonnegative INR amount.")
    budget_minor = parse_amount_minor(amount, "Budget")
    database.initialize()
    with closing(database.connect()) as connection, connection:
        connection.execute(UPSERT, (month, category, budget_minor))
    return {"month": month, "category": category, "budget_minor": budget_minor}


def seed_legacy_budgets() -> int:
    """Explicitly copy the old October allocations, preserving existing entries."""
    database.initialize()
    with closing(database.connect()) as connection, connection:
        cursor = connection.executemany(
            """
            INSERT INTO monthly_budgets (month, category, budget_minor) VALUES (?, ?, ?)
            ON CONFLICT (month, category) DO NOTHING
            """,
            [(SAMPLE_MONTH, category, amount * 100) for category, amount in MONTHLY_BUDGETS.items()],
        )
        return cursor.rowcount


def list_budgets(month: str | None = None) -> list[dict]:
    if month is not None:
        _require_month(month)
    # Phase 4 databases can be read before any command has applied the migration.
    if not database.fetch_rows(
        "SELECT 1 FROM sqlite_master WHERE type = ? AND name = ?", ("table", "monthly_budgets")
    ):
        return []
    if month is None:
        rows = database.fetch_rows(
            "SELECT month, category, budget_minor FROM monthly_budgets ORDER BY month, category", ()
        )
    else:
        rows = database.fetch_rows(
            "SELECT month, category, budget_minor FROM monthly_budgets WHERE month = ? ORDER BY category",
            (month,),
        )
    return [dict(row) for row in rows]


def delete_budget(month: str, category: str) -> bool:
    _require_month(month)
    category = _normalize_category(category)
    database.initialize()
    with closing(database.connect()) as connection, connection:
        cursor = connection.execute(
            "DELETE FROM monthly_budgets WHERE month = ? AND category = ?", (month, category)
        )
        return cursor.rowcount == 1


def _utilization(month: str, category: str, budget: int | None, spent: int | None) -> dict:
    if budget is None:
        status = "not_configured"
    elif spent is None:
        status = "insufficient_data"
    elif spent > budget:
        status = "over_budget"
    else:
        status = "within_budget"
    return {
        "month": month, "category": category, "currency": "INR",
        "budget": in_rupees(budget) if budget is not None else None,
        "spent": in_rupees(spent) if spent is not None else None,
        "remaining": in_rupees(budget - spent) if budget is not None and spent is not None else None,
        "utilization_percent": percent(spent, budget) if budget is not None and spent is not None else None,
        "status": status,
    }


def get_budget_summary(month: str) -> dict:
    """Return all configured category budgets and their utilization for a YYYY-MM month."""
    if error := validate_month(month):
        return error
    rows = monthly_rows(month)
    spent = expense_categories(rows)
    budgets = list_budgets(month)
    total = sum(item["budget_minor"] for item in budgets)
    allocated_spend = sum(spent.get(item["category"], 0) for item in budgets)
    return {
        "overall_utilization_percent": percent(allocated_spend, total) if rows else None,
        "month": month, "currency": "INR", "has_imported_records": bool(rows),
        "status": ("insufficient_data" if not rows else "ok") if budgets else "not_configured",
        "budgets": [
            _utilization(month, item["category"], item["budget_minor"],
                         spent.get(item["category"], 0) if rows else None)
            for item in budgets
        ],
    }


def get_budget_utilization(month: str, category: str) -> dict:
    """Return the saved allocation, imported spending, remainder, and utilization for a category."""
    if error := validate_month(month):
        return error
    try:
        category = _normalize_category(category)
    except ValueError as error:
        return {"error": str(error)}
    budgets = {item["category"]: item["budget_minor"] for item in list_budgets(month)}
    rows = monthly_rows(month)
    spent = expense_categories(rows).get(category, 0) if rows else None
    return _utilization(month, category, budgets.get(category), spent)


def calculate_remaining_budget(category: str) -> dict:
    """Compatibility tool for saved October 2026 budgets; use utilization for other months."""
    result = get_budget_utilization(SAMPLE_MONTH, category)
    if "spent" in result and result["spent"] is None:
        return {"month": SAMPLE_MONTH, "error": "No imported records for this month."}
    result.pop("utilization_percent", None)
    return result
