"""Single-user authentication with Argon2id and revocable SQLite sessions."""

import hashlib
import hmac
import re
import secrets
import sqlite3
import time
from contextlib import closing
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

COOKIE = "finpilot_session"
SESSION_SECONDS = 12 * 60 * 60
FAILURE_WINDOW = 10 * 60
MAX_FAILURES = 5
HASHER = PasswordHasher()
router = APIRouter(prefix="/auth", tags=["authentication"])


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: str = Field(min_length=1, max_length=256)


class AuthStore:
    def __init__(self, path: Path, key: bytes, password_hash: str):
        self.path = path
        self.key = key
        self.password_hash = password_hash
        with closing(self.connect()) as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS login_sessions (
                digest TEXT PRIMARY KEY, expires INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS login_limit (
                id INTEGER PRIMARY KEY CHECK (id = 1), count INTEGER NOT NULL, until INTEGER NOT NULL
            );
            """)

    def connect(self, *, read_only: bool = False) -> sqlite3.Connection:
        if read_only:
            return sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
        return sqlite3.connect(self.path, timeout=5)

    def digest(self, purpose: str, value: str) -> str:
        return hmac.new(self.key, f"{purpose}:{value}".encode(), hashlib.sha256).hexdigest()

    def session_digest(self, cookie: str) -> str | None:
        if not re.fullmatch(r"[A-Za-z0-9_-]{43}\.[a-f0-9]{64}", cookie):
            return None
        token, signature = cookie.split(".")
        if not hmac.compare_digest(signature, self.digest("sign", token)):
            return None
        return self.digest("store", token)

    def authenticated(self, cookie: str) -> bool:
        digest = self.session_digest(cookie)
        if not digest:
            return False
        with closing(self.connect(read_only=True)) as conn:
            return conn.execute(
                "SELECT 1 FROM login_sessions WHERE digest = ? AND expires > ?",
                (digest, int(time.time())),
            ).fetchone() is not None

    def login(self, password: str, previous: str) -> str:
        now = int(time.time())
        with closing(self.connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            limit = conn.execute("SELECT count, until FROM login_limit WHERE id = 1").fetchone()
            failures, until = limit if limit and limit[1] > now else (0, now + FAILURE_WINDOW)
            if failures >= MAX_FAILURES:
                raise HTTPException(429, "Too many login attempts. Try again later.",
                                    headers={"Retry-After": str(until - now)})
            try:
                valid = HASHER.verify(self.password_hash, password)
            except VerificationError:
                valid = False
            if not valid:
                conn.execute(
                    "INSERT INTO login_limit VALUES (1, ?, ?) ON CONFLICT(id) DO UPDATE SET count=excluded.count, until=excluded.until",
                    (failures + 1, until),
                )
            else:
                conn.execute("DELETE FROM login_limit")
                conn.execute("DELETE FROM login_sessions WHERE expires <= ? OR digest = ?",
                             (now, self.session_digest(previous)))
                token = secrets.token_urlsafe(32)
                conn.execute("INSERT INTO login_sessions VALUES (?, ?)",
                             (self.digest("store", token), now + SESSION_SECONDS))
        if not valid:
            raise HTTPException(401, "Invalid password.")
        return f"{token}.{self.digest('sign', token)}"

    def logout(self, cookie: str) -> None:
        with closing(self.connect()) as conn, conn:
            conn.execute("DELETE FROM login_sessions WHERE digest = ?", (self.session_digest(cookie),))


@router.post("/login")
def login(request: Request, body: Credentials, response: Response) -> dict:
    store = request.app.state.auth
    cookie = store.login(body.password, request.cookies.get(COOKIE, ""))
    response.set_cookie(
        COOKIE, cookie, max_age=SESSION_SECONDS, httponly=True, samesite="strict",
        secure=request.app.state.settings.secure_cookie, path="/",
    )
    return {"csrf_token": store.digest("csrf", cookie)}


@router.get("/session")
def session(request: Request) -> dict:
    return {"csrf_token": request.app.state.auth.digest("csrf", request.cookies[COOKIE])}


@router.post("/logout", status_code=204)
def logout(request: Request) -> Response:
    request.app.state.auth.logout(request.cookies[COOKIE])
    response = Response(status_code=204)
    response.delete_cookie(COOKIE, path="/", httponly=True, samesite="strict",
                           secure=request.app.state.settings.secure_cookie)
    return response
