#!/usr/bin/env python3
"""
Create the first owner account for a fresh Helix Codex App installation.

A fresh app has zero accounts and no way to create one through the UI,
because the admin routes require an existing owner. This script seeds the
domain and the first owner so the operator can log in and invite the rest
of the team.

Usage:
    python helix_codex_app/scripts/bootstrap_owner.py \\
        --domain mycompany --username admin --password mypassword

Exit 0 = owner created. Exit 1 = bootstrap failed.
"""
from __future__ import annotations

import argparse
import pathlib
import sys
import uuid

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

MIN_PASSWORD_LENGTH = 8


def bootstrap_owner(
    *,
    db_path: str,
    domain_name: str,
    username: str,
    password_secret: str,
    display_name: str | None = None,
) -> dict:
    """Create a domain and its first owner account, and record the event.

    Returns a dict with the domain name, tenant id, account id, username,
    and the governed node id so the caller can log the outcome.
    """
    from helix_codex_app import db
    from helix_codex_app.security.accounts import AccountRepository
    from helix_codex_app.security.passwords import hash_password

    conn = db.connect(db_path=db_path)
    db._init_schema(conn)
    try:
        repo = AccountRepository(conn)

        tenant_id = domain_name
        domain = repo.create_domain(domain_name, tenant_id)
        account = repo.create_account(
            domain.domain_id,
            username,
            password_hash=hash_password(password_secret),
            display_name=display_name or username,
            role_id="owner",
        )

        node_id = db.record_node(
            conn,
            tenant_id=tenant_id,
            client_id=domain.client_id,
            domain_id=domain.domain_id,
            correlation_id=f"bootstrap-{uuid.uuid4().hex}",
            classification="internal",
            nature="historical_event",
            created_by=account.account_id,
            provenance_source="helix_codex_app.bootstrap",
            provenance_data_mode="app_runtime",
            kind="admin",
            body={
                "action": "bootstrap_owner",
                "account_id": account.account_id,
                "username": account.username,
                "domain": domain_name,
            },
        )

        return {
            "domain": domain_name,
            "tenant_id": tenant_id,
            "account_id": account.account_id,
            "username": account.username,
            "role_id": "owner",
            "node_id": node_id,
        }
    finally:
        db.close(conn)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default="helix_codex_app/app.db")
    parser.add_argument(
        "--domain",
        required=True,
        help="domain name, e.g. mycompany (used as tenant id and login suffix)",
    )
    parser.add_argument("--username", required=True, help="owner username")
    parser.add_argument("--password", required=True, help="owner password (min 8 chars)")
    parser.add_argument("--display-name", default=None, help="owner display name")
    args = parser.parse_args(argv)

    if len(args.password) < MIN_PASSWORD_LENGTH:
        print(
            f"error: password must be at least {MIN_PASSWORD_LENGTH} characters",
            file=sys.stderr,
        )
        return 1

    try:
        result = bootstrap_owner(
            db_path=args.db_path,
            domain_name=args.domain,
            username=args.username,
            password_secret=args.password,
            display_name=args.display_name,
        )
    except Exception as exc:
        print(f"bootstrap failed: {exc}", file=sys.stderr)
        return 1

    print(
        f"owner created: {result['username']}@{result['domain']} "
        f"(account={result['account_id']}, node={result['node_id']})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
