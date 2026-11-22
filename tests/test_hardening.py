"""Startup, backup and authorization checks with disposable data."""

import asyncio
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from google.adk.sessions.sqlite_session_service import SqliteSessionService

from backend.config import Settings
from backend.main import create_app
from finance_agent import database
from finance_agent.import_service import import_statement
from scripts.backup_data import backup
from scripts.restore_data import restore

PASSWORD = "synthetic hardening test password"
KEY = "47" * 32
HASH = PasswordHasher().hash(PASSWORD)
SAMPLE = Path(__file__).resolve().parents[1] / "sample_data" / "sample_statement.csv"


class HardeningTest(unittest.TestCase):
    def setUp(self):
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.data = self.folder / "data"
        self.enterContext(patch.object(database, "DB_PATH", self.data / "transactions.sqlite3"))

    def test_configuration_rejects_missing_auth_and_required_provider_key(self):
        for name, value in (("password_hash", HASH), ("session_secret", KEY), ("proxy_secret", KEY),
                            ("gemini_key", "")):
            (self.folder / name).write_text(value)
        config = {
            "FINPILOT_MODE": "container",
            "FINPILOT_PASSWORD_HASH_FILE": str(self.folder / "does-not-exist"),
            "FINPILOT_SESSION_SECRET_FILE": str(self.folder / "session_secret"),
            "FINPILOT_PROXY_SECRET_FILE": str(self.folder / "proxy_secret"),
            "GOOGLE_API_KEY_FILE": str(self.folder / "gemini_key"),
        }
        with patch.dict(os.environ, config, clear=True):
            with self.assertRaisesRegex(ValueError, "(?i)password"):
                Settings.load()
            os.environ["FINPILOT_PASSWORD_HASH_FILE"] = str(self.folder / "password_hash")
            with self.assertRaisesRegex(ValueError, "Gemini"):
                Settings.load()
            os.environ["FINPILOT_REQUIRE_GEMINI"] = "0"
            self.assertTrue(Settings.load().container)

    def test_private_proxy_enforces_origin_auth_and_secure_cookie(self):
        origin = "https://localhost:3000"
        config = Settings("finpilot-local", frozenset({origin}), True, True, HASH, bytes.fromhex(KEY), KEY)
        with TestClient(create_app(config), base_url=origin, client=("172.21.0.10", 5000)) as client:
            self.assertEqual(client.get("/api/health/live").status_code, 403)
            client.headers["X-FinPilot-Proxy"] = KEY
            self.assertEqual(client.get("/api/health/live").status_code, 200)
            self.assertEqual(client.get("/api/chat/sessions").status_code, 401)
            self.assertEqual(client.post("/api/auth/login", json={"password": PASSWORD}).status_code, 403)
            client.headers["Origin"] = origin
            login = client.post("/api/auth/login", json={"password": PASSWORD})
            self.assertIn("Secure", login.headers["set-cookie"])
            self.assertEqual(client.get("/api/auth/session").status_code, 200)
            other = replace(config, local_user="other")
            client.headers["X-CSRF-Token"] = login.json()["csrf_token"]
            result = client.post("/api/chat/sessions")
            self.assertEqual(result.status_code, 201)
            self.assertEqual(client.post("/api/chat/sessions", json={"user_id": "intruder"},
                                         headers={"Origin": "https://malicious.example"}).status_code, 403)
            with TestClient(create_app(other), base_url=origin, client=("172.21.0.10", 5000)) as isolated:
                isolated.headers.update(client.headers)
                isolated.cookies.update(client.cookies)
                self.assertEqual(isolated.get(f"/api/chat/sessions/{result.json()['id']}").status_code, 404)

    def test_backup_restores_finances_and_adk_sessions_without_auth(self):
        import_statement(SAMPLE)

        async def initialize_chat():
            service = SqliteSessionService(str(self.data / "chat_sessions.sqlite3"))
            await service.create_session(app_name="finance_agent", user_id="finpilot-local", session_id="demo")
            await service.close()

        asyncio.run(initialize_chat())
        (self.data / "auth.sqlite3").write_text("must not back up login state")
        snapshot, restored = self.folder / "snapshot", self.folder / "restored"
        with self.assertRaisesRegex(ValueError, "outside"):
            backup(self.data, self.data / "nested")
        backup(self.data, snapshot)
        self.assertEqual({path.name for path in snapshot.iterdir()},
                         {"transactions.sqlite3", "chat_sessions.sqlite3"})
        with self.assertRaisesRegex(ValueError, "confirm"):
            restore(snapshot, restored)
        restore(snapshot, restored, confirm=True)
        with closing(sqlite3.connect(restored / "transactions.sqlite3")) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0], 6)
        with closing(sqlite3.connect(restored / "chat_sessions.sqlite3")) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0], 1)
        with self.assertRaisesRegex(ValueError, "empty"):
            restore(snapshot, restored, confirm=True)

    def test_corrupt_backup_does_not_restore_half_a_pair(self):
        import_statement(SAMPLE)
        (self.data / "chat_sessions.sqlite3").write_text("not SQLite")
        target = self.folder / "restore"
        with self.assertRaises(sqlite3.Error):
            restore(self.data, target, confirm=True)
        self.assertEqual(list(target.iterdir()), [])
