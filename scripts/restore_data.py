"""Restore validated backups into a new or empty data directory."""

import argparse
import os
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.backup_data import FILES, snapshot


def restore(source: Path, target: Path, *, confirm: bool = False) -> None:
    if not confirm:
        raise ValueError("Review the destination and pass --confirm to restore.")
    source, target = source.resolve(), target.resolve()
    if source == target or target.is_relative_to(source):
        raise ValueError("Choose a separate destination for restored data.")
    target.mkdir(mode=0o700, parents=True, exist_ok=True)
    if any(target.iterdir()):
        raise ValueError("The target directory must be empty. Existing data was preserved.")
    with TemporaryDirectory(prefix=".restore-", dir=target) as folder:
        stage = Path(folder)
        for name, tables in FILES.items():
            snapshot(source / name, stage / name, tables)
        linked = []
        try:
            for name in FILES:
                destination = target / name
                os.link(stage / name, destination)
                linked.append(destination)
        except OSError:
            for destination in linked:
                destination.unlink()
            raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    try:
        restore(args.source, args.target, confirm=args.confirm)
    except (OSError, sqlite3.Error, ValueError) as error:
        parser.exit(1, f"Restore failed: {error if isinstance(error, ValueError) else 'check the backup and destination permissions.'}\n")
    print("Financial and conversation databases restored and verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
