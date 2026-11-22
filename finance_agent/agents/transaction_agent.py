"""Specialist for factual summaries of imported transactions."""

from google.adk.agents import Agent

from ..tools import (
    compare_monthly_expenses,
    get_monthly_spending_trend,
    get_expenses_by_category,
    get_largest_transactions,
    get_total_expenses,
    get_transaction_summary,
)

transaction_agent = Agent(
    name="transaction_analyst",
    mode="single_turn",
    description=(
        "Reports imported transaction history, monthly income, expenses, "
        "category totals, largest expenses, net cash flow, trends, and monthly comparisons."
    ),
    instruction="""Return concise findings to the coordinator.
Use the provided tools for all recorded figures. Preserve returned INR
amounts, transaction counts, and covered periods. Distinguish income from
expenses. The largest-expenses tool covers all imports, so don't present
its ranking as month-specific. Flag missing periods and explain that
imported records may cover only part of a month. If scope is unclear,
tell the coordinator what needs clarification. Do not invent records.
Use get_monthly_spending_trend for historical windows ending at the latest
imported month and compare_monthly_expenses for two-month changes.
Report an undefined percentage when the baseline is zero. Distinguish
missing records from zero imported expenses and avoid forecasts.
Return only the details relevant to the task.
""",
    tools=[
        get_monthly_spending_trend,
        compare_monthly_expenses,
        get_total_expenses,
        get_expenses_by_category,
        get_largest_transactions,
        get_transaction_summary,
    ],
)
