"""Create protected local FinPilot secrets without overwriting existing files."""

import argparse
import getpass
import os
import secrets
from pathlib import Path

from argon2 import PasswordHasher


def create_secret(directory: Path, name: str, value: str) -> None:
    # The private parent directory protects the host file; Docker can mount the
    # individual file for its non-root runtime user without UID remapping.
    try:
        descriptor = os.open(directory / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    except FileExistsError:
        return
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(value + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path(".secrets"))
    parser.add_argument("--without-gemini", action="store_true")
    args = parser.parse_args()
    folder = args.directory
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    if folder.is_symlink() or folder.stat().st_mode & 0o077:
        parser.error("Choose a private secrets directory with permissions 0700.")
    if not (folder / "password_hash").exists():
        password = getpass.getpass("FinPilot password (at least 12 characters): ")
        if not 12 <= len(password) <= 256 or password != getpass.getpass("Repeat password: "):
            parser.error("Passwords must match and contain 12–256 characters.")
        create_secret(folder, "password_hash", PasswordHasher().hash(password))
    create_secret(folder, "session_secret", secrets.token_hex(32))
    create_secret(folder, "proxy_secret", secrets.token_hex(32))
    if not (folder / "gemini_key").exists():
        key = "" if args.without_gemini else getpass.getpass("Gemini API key: ").strip()
        if not args.without_gemini and not key:
            parser.error("Provide a key or pass --without-gemini.")
        create_secret(folder, "gemini_key", key)
    print("Local secret files are ready. Existing files were preserved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
