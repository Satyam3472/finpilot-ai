"""Local HTTP and ADK integration tests using isolated SQLite files."""

import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from openpyxl import Workbook

from backend.config import Settings
from backend.main import create_app
from finance_agent import database
from finance_agent.agent import root_agent
from finance_agent.import_service import import_statement
from finance_agent.parser import MAX_FILE_BYTES

PASSWORD = "synthetic test passphrase only"
ORIGIN = "http://localhost:3000"
TEST_SETTINGS = Settings(
    "finpilot-local", frozenset({ORIGIN}), False, False,
    PasswordHasher().hash(PASSWORD), b"a" * 32, "",
)

SAMPLES = Path(__file__).resolve().parents[1] / "sample_data"


class ApiTest(unittest.TestCase):
    def setUp(self):
        folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(patch.object(database, "DB_PATH", folder / "transactions.sqlite3"))
        self.client = self.enterContext(self.open_client())
        self.login(self.client)

    def login(self, client):
        client.headers["Origin"] = ORIGIN
        session = client.post("/api/auth/login", json={"password": PASSWORD})
        self.assertEqual(session.status_code, 200)
        client.headers["X-CSRF-Token"] = session.json()["csrf_token"]
        return session

    def open_client(self):
        return TestClient(create_app(TEST_SETTINGS), base_url="http://localhost", client=("127.0.0.1", 49000))

    def upload(self, data, name="statement.csv"):
        return self.client.post("/api/statements/upload", files={"file": (name, data)})

    def test_health_and_local_boundary(self):
        self.assertEqual(self.client.get("/api/health").json(), {"status": "ok"})
        self.assertEqual(self.client.get("/api/health", headers={"Host": "example.com"}).status_code, 403)
        forbidden = self.client.post("/api/chat/sessions", headers={"Origin": "https://example.com"})
        self.assertEqual(forbidden.status_code, 403)
        allowed = self.client.get("/api/health/live")
        self.assertEqual(allowed.headers["cache-control"], "no-store")
        self.assertEqual(len(allowed.headers["x-request-id"]), 32)
        self.assertEqual(self.client.get("/api/health/ready").json(), {"status": "ready"})
        self.assertEqual(self.client.get("/openapi.json").status_code, 404)
        self.assertEqual(self.client.get("/run").status_code, 404)

    def test_authentication_csrf_expiration_and_logout(self):
        self.client.cookies.clear()
        for path in ("/api/dashboard/summary", "/api/imports", "/api/chat/sessions"):
            self.assertEqual(self.client.get(path).status_code, 401)
        self.assertEqual(self.client.post("/api/chat/sessions").status_code, 401)
        response = self.login(self.client)
        self.assertIn("HttpOnly", response.headers["set-cookie"])
        self.assertIn("SameSite=strict", response.headers["set-cookie"])
        target = "/api/budgets/2026-10/food"
        denied = self.client.put(target, json={"amount_minor": 100}, headers={"X-CSRF-Token": ""})
        self.assertEqual(denied.json()["error"]["code"], "invalid_csrf")
        self.assertEqual(self.client.put(target, json={"amount_minor": 100}).status_code, 200)
        old_cookie = self.client.cookies.get("finpilot_session")
        self.assertEqual(self.client.post("/api/auth/logout").status_code, 204)
        self.client.cookies.set("finpilot_session", old_cookie)
        self.assertEqual(self.client.get("/api/auth/session").status_code, 401)
        self.client.cookies.clear()
        self.login(self.client)
        with patch("backend.auth.time.time", return_value=4_000_000_000):
            self.assertEqual(self.client.get("/api/auth/session").status_code, 401)

    def test_login_rate_limit_persists(self):
        for _ in range(5):
            self.assertEqual(self.client.post("/api/auth/login", json={"password": "wrong"}).status_code, 401)
        with self.open_client() as restarted:
            limited = restarted.post("/api/auth/login", json={"password": PASSWORD}, headers={"Origin": ORIGIN})
            self.assertEqual(limited.status_code, 429)
            self.assertIn("retry-after", limited.headers)

    def test_readiness_reports_storage_failure(self):
        with patch("backend.main.check_sqlite", side_effect=RuntimeError("private detail")):
            response = self.client.get("/api/health/ready")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private detail", response.text)

    def test_dashboard_metrics_and_missing_month(self):
        import_statement(SAMPLES / "sample_statement.csv")
        data = self.client.get("/api/dashboard/summary").json()
        self.assertEqual(data["month"], "2026-10")
        self.assertEqual(data["total_income_minor"], 6_000_000)
        self.assertEqual(data["total_expenses_minor"], 422_800)
        self.assertEqual(data["net_cash_flow_minor"], 5_577_200)
        self.assertEqual(data["transaction_count"], 6)
        self.assertEqual(data["category_totals_minor"]["food"], 80_000)
        missing = self.client.get("/api/dashboard/summary", params={"month": "2026-08"}).json()
        self.assertEqual(missing["availability"], "no_records")
        self.assertIsNone(missing["total_expenses_minor"])

    def test_transactions_filter_and_paginate(self):
        import_statement(SAMPLES / "sample_statement.csv")
        result = self.client.get("/api/transactions", params={
            "month": "2026-10", "category": "food", "type": "expense", "search": "zomato"
        }).json()
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["amount_minor"], 45000)
        self.assertNotIn("reference_id", result["items"][0])
        page = self.client.get("/api/transactions", params={"page": 2, "page_size": 2, "sort": "asc"}).json()
        self.assertEqual(page["total"], 6)
        self.assertEqual([row["date"] for row in page["items"]], ["2026-10-07", "2026-10-10"])

    def test_statement_upload_duplicate_and_history(self):
        data = (SAMPLES / "sample_statement.csv").read_bytes()
        first = self.upload(data, "../../sample.csv")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(first.json()["imported_rows"], 6)
        duplicate = self.upload(data)
        self.assertEqual(duplicate.status_code, 200)
        self.assertTrue(duplicate.json()["already_imported"])
        history = self.client.get("/api/imports").json()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["file_name"], "sample.csv")
        self.assertNotIn("file_hash", history[0])

    def test_statement_upload_xlsx_and_rejected_rows(self):
        book = Workbook()
        sheet = book.active
        sheet.append(["date", "description", "debit", "credit"])
        sheet.append(["2026-10-01", "UBER", 20.25, None])
        sheet.append(["2026-10-01", "SECRET CELL", "invalid", None])
        content = BytesIO()
        book.save(content)
        response = self.upload(content.getvalue(), "test.xlsx")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["imported_rows"], 1)
        self.assertEqual(response.json()["errors"][0]["row"], 3)
        self.assertNotIn("SECRET CELL", response.text)

    def test_invalid_or_oversize_upload(self):
        self.assertEqual(self.upload(b"not a workbook", "test.xlsx").status_code, 422)
        self.assertEqual(self.upload(b"invalid csv").status_code, 422)
        self.assertEqual(self.upload(b"file", "test.pdf").status_code, 415)
        self.assertEqual(self.upload(b"x" * (MAX_FILE_BYTES + 1)).status_code, 413)
        self.assertEqual(self.upload(b"x" * (MAX_FILE_BYTES + 65536)).status_code, 413)
        self.assertEqual(self.client.get("/api/imports").json(), [])

    def test_budget_create_update_and_delete(self):
        import_statement(SAMPLES / "sample_statement.csv")
        target = "/api/budgets/2026-10/food"
        created = self.client.put(target, json={"amount_minor": 80000}).json()
        self.assertEqual(created["budgets"][0]["utilization_percent"], 100)
        updated = self.client.put(target, json={"amount_minor": 70001}).json()
        self.assertEqual(updated["budgets"][0]["remaining_minor"], -9999)
        self.assertEqual(updated["budgets"][0]["status"], "over_budget")
        self.assertEqual(self.client.get("/api/budgets?month=2026-10").json(), updated)
        self.assertEqual(self.client.delete(target).status_code, 204)
        self.assertEqual(self.client.get("/api/budgets?month=2026-10").json()["budgets"], [])
        self.assertEqual(self.client.delete(target).status_code, 404)

    def test_monthly_analytics_have_minor_units_and_missing_data(self):
        import_statement(SAMPLES / "analytics_statement.csv")
        months = self.client.get("/api/analytics/trends?months=4").json()["months"]
        self.assertIsNone(months[1]["total_expenses_minor"])
        self.assertEqual(months[-1]["total_expenses_minor"], 531200)
        comparison = self.client.get("/api/analytics/comparison?month1=2026-09&month2=2026-10").json()
        self.assertEqual(comparison["change_percent"], 110.79)
        self.assertEqual(comparison["absolute_difference_minor"], 279200)
        missing = self.client.get("/api/analytics/comparison?month1=2026-08&month2=2026-10").json()
        self.assertEqual(missing["status"], "insufficient_data")
        flags = self.client.get("/api/analytics/anomalies?month=2026-10").json()
        self.assertEqual(flags["unusual_transactions"][0]["amount_minor"], 200000)
        insights = self.client.get("/api/insights/savings?month=2026-10").json()
        self.assertEqual(insights["observations"][0]["evidence"]["increase_minor"], 30000)

    def test_invalid_query_and_budget_fields(self):
        for url in ("/api/dashboard/summary?month=0000-10", "/api/transactions?page=0",
                    "/api/transactions?sort=drop%20table", "/api/analytics/trends?months=30"):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 422)
                self.assertIn("message", response.json()["error"])
        for body in ({"amount_minor": -1}, {"amount_minor": 3.1}, {"amount_minor": 1, "owner": "other"}):
            self.assertEqual(self.client.put("/api/budgets/2026-10/food", json=body).status_code, 422)

    def test_chat_runs_existing_coordinator_and_persists_safe_history(self):
        import_statement(SAMPLES / "sample_statement.csv")
        create = self.client.post("/api/chat/sessions")
        self.assertEqual(create.status_code, 201)
        path = f"/api/chat/sessions/{create.json()['id']}"
        self.assertEqual(self.client.get(path).json()["messages"], [])
        self.assertEqual(self.client.get(f"/api/chat/sessions/{uuid4()}").status_code, 404)
        self.assertEqual(self.client.get("/api/chat/sessions/not-valid").status_code, 422)

        replies = iter([
            types.Part.from_function_call(name="transaction_analyst", args={"request": "October 2026 expenses"}),
            types.Part.from_function_call(name="get_total_expenses", args={"month": "2026-10"}),
            types.Part.from_text(text="Specialist total ₹4,228."),
            types.Part.from_text(text="October expenses were ₹4,228."),
        ])
        amounts = []

        async def scripted_model(_model, llm_request, stream=False):
            for content in llm_request.contents:
                for part in content.parts or []:
                    if part.function_response and part.function_response.name == "get_total_expenses":
                        amounts.append(part.function_response.response["total_expenses"])
            part = next(replies)
            parts = [types.Part(text="Hidden scratchpad", thought=True), part] if part.text else [part]
            yield LlmResponse(content=types.Content(role="model", parts=parts))

        with patch.object(type(root_agent.canonical_model), "generate_content_async", scripted_model):
            response = self.client.post(f"{path}/messages", json={"message": "October spending?"})
        self.assertIn("event: done", response.text)
        self.assertIn("October expenses were ₹4,228.", response.text)
        self.assertNotIn("get_total_expenses", response.text)
        self.assertNotIn("Hidden scratchpad", response.text)
        self.assertEqual(amounts, [4228])
        with self.open_client() as restarted:
            self.login(restarted)
            history = restarted.get(path).json()
            self.assertEqual(history["title"], "October spending?")
            self.assertEqual(history["messages"], [
                {"role": "user", "text": "October spending?"},
                {"role": "assistant", "text": "October expenses were ₹4,228."},
            ])
            self.assertEqual(restarted.get("/api/chat/sessions").json()[0]["id"], create.json()["id"])

    def test_chat_errors_hide_provider_details(self):
        path = f"/api/chat/sessions/{self.client.post('/api/chat/sessions').json()['id']}"

        async def broken_model(_model, llm_request, stream=False):
            raise RuntimeError("internal credential and financial information")
            yield  # Make the failure originate from an async model stream.

        with patch.object(type(root_agent.canonical_model), "generate_content_async", broken_model):
            response = self.client.post(f"{path}/messages", json={"message": "Test failure"})
        self.assertIn("event: error", response.text)
        self.assertNotIn("internal credential", response.text)
