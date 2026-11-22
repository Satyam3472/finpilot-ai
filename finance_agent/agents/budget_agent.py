"""Specialist for read-only budget checks and illustrative adjustments."""

from google.adk.agents import Agent

from ..tools import (
    get_budget_summary,
    get_budget_utilization,
    get_savings_opportunities,
    calculate_remaining_budget,
    get_expenses_by_category,
    get_transaction_summary,
)

budget_agent = Agent(
    name="budget_planner",
    mode="single_turn",
    description=(
        "Checks saved category allocations and remaining budgets, and "
        "suggests budget adjustments and savings opportunities."
    ),
    instruction="""Return concise budget findings to the coordinator.
Use get_budget_summary and get_budget_utilization for saved monthly
allocations and utilization. Ask the coordinator to clarify an ambiguous
month. The legacy calculate_remaining_budget tool applies only to October
2026 and requires a saved allocation for that category. A zero budget is
configured but has undefined utilization. Clearly report missing budgets
and missing imported records. Use get_savings_opportunities for budget
pressure and spending changes. Explain the evidence without promising
savings or forecasting future amounts. Distinguish suggested actions from
saved allocations. Budget changes require an explicit action in the app or CLI.
""",
    tools=[
        get_budget_summary,
        get_budget_utilization,
        get_savings_opportunities,
        calculate_remaining_budget,
        get_expenses_by_category,
        get_transaction_summary,
    ],
)
