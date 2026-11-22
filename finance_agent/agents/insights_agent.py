"""Specialist for evidence-backed patterns in imported spending."""

from google.adk.agents import Agent

from ..tools import (
    compare_monthly_expenses,
    detect_unusual_transactions,
    get_monthly_spending_trend,
    get_expenses_by_category,
    get_largest_transactions,
    get_transaction_summary,
)

insights_agent = Agent(
    name="expense_insights",
    mode="single_turn",
    description=(
        "Highlights top spending categories, high-value expenses, "
        "comparisons across imported periods, and unusual expenses."
    ),
    instruction="""Return concise spending insights to the coordinator.
Use the expense and summary tools as evidence for recorded figures in INR.
Use the ranking tool for high-value expenses across all imports and
identify that scope. It cannot produce a complete month-specific ranking.
Use the historical tools for comparisons and trends. Report missing
periods and qualify conclusions when statement coverage is unknown.
For unusually large expenses, use detect_unusual_transactions. Explain
the prior same-category baseline, modified Z-score threshold, and any
insufficient history or zero deviation. A flag is a review prompt;
neither a large expense nor a statistical score establishes fraud.
Treat the results as observations of imported records and avoid forecasts
or unnecessary private details.
""",
    tools=[
        detect_unusual_transactions,
        get_monthly_spending_trend,
        compare_monthly_expenses,
        get_expenses_by_category,
        get_largest_transactions,
        get_transaction_summary,
    ],
)
