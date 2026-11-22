"""Server-only configuration and file-backed secrets."""

import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from argon2 import extract_parameters
from argon2.low_level import Type
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000"


def read_secret(name: str, default: Path | None = None) -> str:
    configured = os.getenv(f"{name}_FILE")
    path = Path(configured) if configured else default
    if path is None or (not configured and not path.exists()):
        return ""
    try:
        with path.open(encoding="utf-8") as stream:
            value = stream.read(8193)
        if len(value) > 8192:
            raise ValueError
        return value.strip()
    except (OSError, UnicodeError, ValueError):
        raise ValueError(f"Cannot read the {name} secret file.") from None


def random_key(value: str, name: str) -> bytes:
    if not re.fullmatch(r"[a-fA-F0-9]{64}", value):
        raise ValueError(f"Configure {name} using scripts.configure_local.")
    return bytes.fromhex(value)


@dataclass(frozen=True)
class Settings:
    local_user: str
    origins: frozenset[str]
    container: bool
    secure_cookie: bool
    password_hash: str
    session_key: bytes
    proxy_key: str

    @classmethod
    def load(cls) -> "Settings":
        mode = os.getenv("FINPILOT_MODE", "development")
        if mode not in {"development", "container"}:
            raise ValueError("FINPILOT_MODE must be development or container.")
        container = mode == "container"
        if not container:
            load_dotenv(ROOT / "finance_agent" / ".env")
        folder = ROOT / ".secrets"
        password = read_secret("FINPILOT_PASSWORD_HASH", folder / "password_hash")
        try:
            params = extract_parameters(password)
            if params.type != Type.ID or params.memory_cost < 19456 or params.time_cost < 2:
                raise ValueError
        except Exception:
            raise ValueError("Configure the Argon2id password using scripts.configure_local.") from None
        session_key = random_key(read_secret("FINPILOT_SESSION_SECRET", folder / "session_secret"), "the session secret")
        proxy_key = read_secret("FINPILOT_PROXY_SECRET", folder / "proxy_secret") if container else ""
        if container:
            random_key(proxy_key, "the proxy secret")

        local_user = os.getenv("FINPILOT_LOCAL_USER", "finpilot-local")
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", local_user):
            raise ValueError("FINPILOT_LOCAL_USER must be a short local identity.")
        origins = frozenset(value.strip() for value in os.getenv("FINPILOT_ORIGIN", DEFAULT_ORIGINS).split(","))
        try:
            parsed = [urlsplit(origin) for origin in origins]
            if not all(
                item.scheme in {"http", "https"} and item.hostname in {"localhost", "127.0.0.1", "::1"}
                and item.port and not item.username and not item.password and not item.path
                and not item.query and not item.fragment for item in parsed
            ):
                raise ValueError
        except ValueError:
            raise ValueError("FINPILOT_ORIGIN must list exact loopback origins with ports.") from None
        schemes = {item.scheme for item in parsed}
        if len(schemes) != 1:
            raise ValueError("Configure either HTTP or HTTPS origins, not both.")
        key = read_secret("GOOGLE_API_KEY", folder / "gemini_key")
        if key:
            os.environ["GOOGLE_API_KEY"] = key
        require_key = os.getenv("FINPILOT_REQUIRE_GEMINI", "1" if container else "0")
        if require_key not in {"0", "1"}:
            raise ValueError("FINPILOT_REQUIRE_GEMINI must be 0 or 1.")
        if require_key == "1" and not any(
            os.getenv(name) and os.environ[name] != "your_gemini_api_key_here"
            for name in ("GOOGLE_API_KEY", "GEMINI_API_KEY")
        ):
            raise ValueError("Configure the Gemini key file or explicitly disable the startup requirement.")
        return cls(local_user, origins, container, schemes == {"https"}, password, session_key, proxy_key)
