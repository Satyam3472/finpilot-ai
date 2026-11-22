"""Manage local monthly INR budgets without using an agent."""

import argparse
import sqlite3

from finance_agent.budget import delete_budget, list_budgets, seed_legacy_budgets, set_budget


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage FinPilot's local monthly budgets.")
    commands = parser.add_subparsers(dest="command", required=True)
    set_command = commands.add_parser("set", help="Create or update an allocation in INR.")
    delete_command = commands.add_parser("delete", help="Remove a configured allocation.")
    for command in (set_command, delete_command):
        command.add_argument("--month", required=True)
        command.add_argument("--category", required=True)
    set_command.add_argument("--amount", required=True, help="Nonnegative INR amount.")
    commands.add_parser("list", help="List configured allocations.").add_argument("--month")
    commands.add_parser("seed-legacy", help="Copy the old October 2026 defaults if absent.")
    args = parser.parse_args()

    try:
        if args.command == "set":
            row = set_budget(args.month, args.category, args.amount)
            print(f"Saved {format_budget(row)}")
        elif args.command == "list":
            rows = list_budgets(args.month)
            for row in rows:
                print(format_budget(row))
            if not rows:
                print("No configured budgets." if args.month is None else f"No budgets for {args.month}.")
        elif args.command == "delete":
            deleted = delete_budget(args.month, args.category)
            category = args.category.strip().lower()
            if not deleted:
                print(f"No configured budget for {args.month} {category}.")
                return 1
            print(f"Deleted {args.month} {category} budget.")
        else:
            print(f"Added {seed_legacy_budgets()} legacy allocations for October 2026.")
    except ValueError as error:
        parser.exit(1, f"Budget command failed: {error}\n")
    except (OSError, sqlite3.Error):
        parser.exit(1, "Budget command failed: cannot access the local database.\n")
    return 0


def format_budget(row: dict) -> str:
    rupees, paise = divmod(row["budget_minor"], 100)
    return f"{row['month']} {row['category']} INR {rupees:,}.{paise:02d}"


if __name__ == "__main__":
    raise SystemExit(main())
