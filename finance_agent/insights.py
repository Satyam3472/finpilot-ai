"""Evidence and practical review actions for monthly spending."""

from .analytics import expense_categories, in_rupees, monthly_rows, percent, shift_month, validate_month
from .budget import list_budgets

DISCRETIONARY = {"shopping", "entertainment"}


def get_savings_opportunities(month: str) -> dict:
    """Report budget pressure and rising discretionary expenses using imported records."""
    if error := validate_month(month):
        return error
    rows = monthly_rows(month)
    previous_month = shift_month(month, -1)
    result = {
        "month": month, "currency": "INR", "comparison_month": previous_month,
        "comparison_status": "insufficient_data", "status": "insufficient_data",
        "observations": [],
    }
    if not rows:
        result["reason"] = "No imported records for the requested month."
        return result

    spending = expense_categories(rows)
    prior = monthly_rows(previous_month) if previous_month else []
    prior_spending = expense_categories(prior)
    budgets = list_budgets(month)
    result.update(
        status="ok", comparison_status="available" if prior else "insufficient_data",
        budget_status="configured" if budgets else "not_configured",
    )
    for budget in budgets:
        category, allocation = budget["category"], budget["budget_minor"]
        spent = spending.get(category, 0)
        if spent <= allocation and (allocation == 0 or spent * 100 < allocation * 80):
            continue
        result["observations"].append({
            "category": category,
            "type": "over_budget" if spent > allocation else "near_or_at_budget",
            "evidence": {
                "spent": in_rupees(spent), "budget": in_rupees(allocation),
                "utilization_percent": percent(spent, allocation),
            },
            "suggested_action": "Review recent expenses in this category and prioritize essentials.",
        })

    if prior:
        for category in sorted(DISCRETIONARY & spending.keys()):
            spent, previous = spending[category], prior_spending.get(category, 0)
            if spent > previous:
                result["observations"].append({
                    "category": category, "type": "rising_discretionary_spending",
                    "evidence": {
                        "spent": in_rupees(spent), "previous_spent": in_rupees(previous),
                        "increase": in_rupees(spent - previous),
                        "change_percent": percent(spent - previous, previous),
                    },
                    "suggested_action": "Review optional purchases or subscriptions before repeating them.",
                })
    return result
