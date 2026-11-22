"""FinPilot HTTP API with a local, authenticated boundary."""

import hmac
import ipaddress
import json
import logging
import re
import sqlite3
from contextlib import asynccontextmanager, closing
from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from google.adk.runners import Runner
from google.adk.sessions.sqlite_session_service import SqliteSessionService
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers, MutableHeaders
from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Receive, Scope, Send

from backend import auth
from backend.config import Settings
from backend.routers import chat, finance, records
from finance_agent import database
from finance_agent.agent import root_agent
from finance_agent.parser import MAX_FILE_BYTES

HEALTH = {"/api/health", "/api/health/live", "/api/health/ready"}
LOGIN = "/api/auth/login"
READ_METHODS = {"GET", "HEAD", "OPTIONS"}
LOOPBACK_HOST = re.compile(r"(?:localhost|127\.0\.0\.1|\[::1\])(?::[0-9]{1,5})?", re.I)


def error_response(status: int, message: str, code: str = "request_failed", headers=None) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status, headers=headers)


def loopback(client: tuple[str, int] | None) -> bool:
    try:
        return bool(client and ipaddress.ip_address(client[0]).is_loopback)
    except ValueError:
        return False


def equal_secret(candidate: str, expected: str) -> bool:
    return bool(expected) and hmac.compare_digest(candidate.encode(), expected.encode())


class LocalBoundary:
    """Enforce proxy trust, authorization, CSRF and request size before parsing."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        path, method = scope["path"], scope["method"]
        state = scope["app"].state
        request_id, start = uuid4().hex, perf_counter()
        status = 500
        response_started = False

        async def send_private(message):
            nonlocal status, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status = message["status"]
                outgoing = MutableHeaders(scope=message)
                outgoing["Cache-Control"] = "no-store"
                outgoing["X-Request-ID"] = request_id
                outgoing["X-Content-Type-Options"] = "nosniff"
                outgoing["X-Frame-Options"] = "DENY"
            await send(message)

        async def reject(code, description, kind="request_failed"):
            await error_response(code, description, kind)(scope, receive, send_private)

        try:
            settings = state.settings
            local = loopback(scope.get("client")) and LOOPBACK_HOST.fullmatch(headers.get("host", ""))
            proxied = settings.container and equal_secret(headers.get("x-finpilot-proxy", ""), settings.proxy_key)
            if not (proxied or local and (not settings.container or path in HEALTH)):
                await reject(403, "This FinPilot connection is not allowed.")
                return

            origin = headers.get("origin")
            if (origin and origin not in settings.origins) or (method not in READ_METHODS and origin not in settings.origins):
                await reject(403, "Request origin is not allowed.", "invalid_origin")
                return

            if path not in HEALTH and not (path == LOGIN and method == "POST"):
                cookie = Request(scope).cookies.get(auth.COOKIE, "")
                try:
                    authenticated = await run_in_threadpool(state.auth.authenticated, cookie)
                except sqlite3.Error:
                    await reject(503, "The local database is temporarily unavailable.", "storage_error")
                    return
                if not authenticated:
                    await reject(401, "Sign in to FinPilot.", "unauthenticated")
                    return
                if method not in READ_METHODS and not equal_secret(
                    headers.get("x-csrf-token", ""), state.auth.digest("csrf", cookie)
                ):
                    await reject(403, "The request could not be verified.", "invalid_csrf")
                    return

            if method not in {"POST", "PUT", "PATCH"}:
                await self.app(scope, receive, send_private)
                return

            limit = MAX_FILE_BYTES + 65_536 if path == "/api/statements/upload" else 32_768
            body = bytearray()
            while True:
                chunk = await receive()
                if chunk["type"] == "http.disconnect":
                    return
                block = chunk.get("body", b"")
                if len(body) + len(block) > limit:
                    await reject(413, "The request exceeds the allowed size.")
                    return
                body.extend(block)
                if not chunk.get("more_body"):
                    break

            delivered = False

            async def replay():
                nonlocal delivered
                if delivered:
                    return await receive()
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}

            await self.app(scope, replay, send_private)
        except Exception:
            scope.setdefault("state", {})["sanitized_error"] = "internal_error"
            if response_started:
                await send({"type": "http.response.body", "body": b"", "more_body": False})
            else:
                await reject(500, "An unexpected server error occurred.", "internal_error")
        finally:
            route = getattr(scope.get("route"), "path", None)
            if not route and path in HEALTH | {LOGIN}:
                route = path
            outcome = scope.get("state", {}).get("sanitized_error")
            print(json.dumps({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": "error" if status >= 500 or outcome == "internal_error" else
                "warning" if status >= 400 or outcome else "info",
                "request_id": request_id, "method": method if method in READ_METHODS |
                {"POST", "PUT", "DELETE", "PATCH"} else "other",
                "route": route or "unmatched_or_denied", "status": status,
                "duration_ms": round((perf_counter() - start) * 1000, 2),
                "outcome": outcome or ("request_failed" if status >= 400 else "complete"),
            }), flush=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = app.state.config_override or Settings.load()
    directory = database.DB_PATH.parent
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    database.initialize()
    app.state.auth = auth.AuthStore(directory / "auth.sqlite3", settings.session_key, settings.password_hash)
    sessions = SqliteSessionService(str(directory / "chat_sessions.sqlite3"))
    model_loggers = [logging.getLogger(name) for name in ("google_adk", "google.adk", "google_genai")]
    previous_levels = [logger.level for logger in model_loggers]
    for logger in model_loggers:
        logger.setLevel(logging.CRITICAL + 1)
    runner = Runner(app_name=chat.APP_NAME, agent=root_agent, session_service=sessions)
    app.state.settings = settings
    app.state.local_user = settings.local_user
    app.state.sessions = sessions
    app.state.runner = runner
    app.state.active_sessions = set()
    try:
        await sessions.list_sessions(app_name=chat.APP_NAME, user_id=settings.local_user)
        yield
    finally:
        try:
            await runner.close()
        finally:
            try:
                await sessions.close()
            finally:
                for logger, level in zip(model_loggers, previous_levels, strict=True):
                    logger.setLevel(level)


def check_sqlite(store: auth.AuthStore) -> None:
    with closing(database.connect(read_only=True)) as connection:
        connection.execute("SELECT id FROM transactions LIMIT 1").fetchone()
    with closing(store.connect(read_only=True)) as connection:
        connection.execute("SELECT digest FROM login_sessions LIMIT 1").fetchone()


def create_app(settings: Settings | None = None) -> FastAPI:
    # Expose only the app's narrow chat adapter, with a server-owned ADK identity.
    app = FastAPI(title="FinPilot API", version="0.7.0", lifespan=lifespan,
                  docs_url=None, openapi_url=None, redoc_url=None)
    app.state.config_override = settings
    app.add_middleware(LocalBoundary)

    @app.exception_handler(HTTPException)
    async def http_error(_request, error):
        detail = error.detail if isinstance(error.detail, str) else "Request failed."
        return error_response(error.status_code, detail, headers=error.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request, error):
        issue = error.errors()[0]
        field = ".".join(str(item) for item in issue["loc"] if isinstance(item, (int, str)))
        return error_response(422, f"{field}: {issue['msg']}", "validation_error")

    @app.exception_handler(sqlite3.Error)
    async def database_error(_request, _error):
        return error_response(503, "The local database is temporarily unavailable.", "storage_error")

    @app.get("/api/health")
    @app.get("/api/health/live")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/health/ready")
    async def readiness(request: Request):
        state = request.app.state
        try:
            await run_in_threadpool(check_sqlite, state.auth)
            await state.sessions.list_sessions(app_name=chat.APP_NAME, user_id=state.local_user)
        except Exception:
            return error_response(503, "FinPilot is not ready.", "not_ready")
        return {"status": "ready"}

    app.include_router(auth.router, prefix="/api")
    app.include_router(finance.router, prefix="/api", tags=["finance"])
    app.include_router(records.router, prefix="/api", tags=["records"])
    app.include_router(chat.router, prefix="/api")
    return app


app = create_app()
