"""Manage product image service tokens from a trusted server terminal."""
from __future__ import annotations

import argparse
import json
import sys

from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError

from config import load_settings
from storage.product_image_tokens import issue_token, list_tokens, revoke_token


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    issue = actions.add_parser("issue", help="generate and display a new token once")
    issue.add_argument("--label", required=True)
    issue.add_argument("--days", type=int, choices=range(1, 91), default=30, metavar="1..90")
    actions.add_parser("list", help="list token metadata")
    revoke = actions.add_parser("revoke", help="revoke a token by ID")
    revoke.add_argument("id", type=int)
    args = parser.parse_args()
    if args.action == "issue" and not (sys.stdin.isatty() and sys.stdout.isatty() and sys.stderr.isatty()):
        parser.error("Issue tokens only from a trusted interactive terminal, with output capture disabled.")
    if args.action == "revoke" and args.id <= 0:
        parser.error("Token ID must be positive.")

    try:
        settings = load_settings(require_database=True)
        engine = create_engine(settings.database_url, hide_parameters=True)
        try:
            with engine.begin() as connection:
                if args.action == "issue":
                    item, token = issue_token(connection, label=args.label, days=args.days)
                elif args.action == "list":
                    item = list_tokens(connection)
                else:
                    item = revoke_token(connection, args.id)
        finally:
            engine.dispose()
    except (SQLAlchemyError, ValueError, RuntimeError):
        print("Unable to manage tokens. Check the database configuration, token table and command arguments.", file=sys.stderr)
        return 1

    if item is None:
        print("Token ID not found.", file=sys.stderr)
        return 1
    print(json.dumps(item, ensure_ascii=False, default=str))
    if args.action == "issue":
        print("Store this token in the approved internal secret manager; it cannot be shown again:")
        print(token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
