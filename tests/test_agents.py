import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from google.adk.agents import Agent
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import InMemoryRunner
from google.genai import types

from finance_agent import agent, database, tools
from finance_agent.budget import seed_legacy_budgets
from finance_agent.agents.budget_agent import budget_agent
from finance_agent.agents.insights_agent import insights_agent
from finance_agent.agents.transaction_agent import transaction_agent
from finance_agent.import_service import import_statement

SAMPLE = Path(__file__).resolve().parents[1] / "sample_data" / "sample_statement.csv"


class AgentConfigurationTest(unittest.TestCase):
    def test_coordinator_and_specialists(self):
        root = agent.root_agent
        self.assertIsInstance(root, Agent)
        self.assertEqual(root.name, "finpilot_coordinator")
        self.assertEqual(root.model, "gemini-flash-latest")
        self.assertIsNone(root.mode)
        self.assertEqual(root.sub_agents, [transaction_agent, budget_agent, insights_agent])
        self.assertEqual(
            {child.name for child in root.sub_agents},
            {"transaction_analyst", "budget_planner", "expense_insights"},
        )
        self.assertEqual(
            {tool.name for tool in root.tools},
            {child.name for child in root.sub_agents},
        )
        for child in root.sub_agents:
            with self.subTest(child=child.name):
                self.assertIsInstance(child, Agent)
                self.assertIs(child.parent_agent, root)
                self.assertEqual(child.mode, "single_turn")
                self.assertEqual(child.canonical_model.model, root.model)
                self.assertFalse(child.sub_agents)

    def test_specialist_responsibilities_and_permissions(self):
        cases = [
            (
                transaction_agent, "net cash flow",
                [tools.get_monthly_spending_trend, tools.compare_monthly_expenses,
                 tools.get_total_expenses, tools.get_expenses_by_category,
                 tools.get_largest_transactions, tools.get_transaction_summary],
            ),
            (
                budget_agent, "remaining budgets",
                [tools.get_budget_summary, tools.get_budget_utilization, tools.get_savings_opportunities,
                 tools.calculate_remaining_budget, tools.get_expenses_by_category,
                 tools.get_transaction_summary],
            ),
            (
                insights_agent, "comparisons across imported periods",
                [tools.detect_unusual_transactions, tools.get_monthly_spending_trend,
                 tools.compare_monthly_expenses, tools.get_expenses_by_category, tools.get_largest_transactions,
                 tools.get_transaction_summary],
            ),
        ]
        for child, responsibility, expected_tools in cases:
            with self.subTest(child=child.name):
                self.assertIn(responsibility, child.description)
                self.assertEqual(child.tools, expected_tools)


class DelegationTest(unittest.IsolatedAsyncioTestCase):
    async def test_native_delegation_runs_sqlite_tools_and_returns_to_coordinator(self):
        folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(patch.object(database, "DB_PATH", folder / "transactions.sqlite3"))
        import_statement(SAMPLE)
        seed_legacy_budgets()

        def call(name, **args):
            return types.Part.from_function_call(name=name, args=args)

        def text(value):
            return types.Part.from_text(text=value)

        # Script model decisions only. ADK still runs the sub-agents and their real tools.
        steps = iter([
            call("transaction_analyst", request="Get imported spending for 2026-10."),
            call("get_total_expenses", month="2026-10"),
            text("Imported October expenses were ₹4,228."),
            call("budget_planner", request="Check the fixed October 2026 food budget."),
            call("calculate_remaining_budget", category="food"),
            text("The October food budget has ₹7,200 remaining."),
            call("expense_insights", request="Find the top expense category for 2026-10."),
            call("get_expenses_by_category", month="2026-10"),
            text("Shopping was the top category at ₹2,499."),
            text("October expenses were ₹4,228. Shopping led at ₹2,499, "
                 "and the food budget had ₹7,200 left."),
        ])
        returned = {}

        async def scripted_model(_model, llm_request, stream=False):
            part = next(steps)
            if part.function_call:
                self.assertIn(part.function_call.name, llm_request.tools_dict)
            for content in llm_request.contents:
                for item in content.parts or []:
                    if item.function_response:
                        returned[item.function_response.name] = item.function_response.response
            yield LlmResponse(content=types.Content(role="model", parts=[part]))

        runner = InMemoryRunner(agent=agent.root_agent, app_name="finance_agent")
        async with runner:
            session = await runner.session_service.create_session(
                app_name="finance_agent", user_id="test_user"
            )
            message = types.Content(
                role="user", parts=[text("October spending, top category, and food budget?")]
            )
            with patch.object(
                type(agent.root_agent.canonical_model), "generate_content_async", scripted_model
            ):
                events = [
                    event async for event in runner.run_async(
                        user_id="test_user", session_id=session.id, new_message=message
                    )
                ]

        self.assertEqual(returned["get_total_expenses"]["total_expenses"], 4228)
        self.assertEqual(returned["calculate_remaining_budget"]["remaining"], 7200)
        self.assertEqual(returned["get_expenses_by_category"]["category_totals"]["shopping"], 2499)
        self.assertIn("₹4,228", str(returned["transaction_analyst"]))
        self.assertIn("₹7,200", str(returned["budget_planner"]))
        self.assertIn("₹2,499", str(returned["expense_insights"]))
        self.assertEqual(events[-1].author, agent.root_agent.name)
        self.assertTrue(events[-1].is_final_response())
