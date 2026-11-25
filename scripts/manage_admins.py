#!/usr/bin/env python3
"""
scripts/manage_admins.py - CLI tool for managing administrator accounts.

Commands:
    python scripts/manage_admins.py add --email <email> [--name <name>]
    python scripts/manage_admins.py list
    python scripts/manage_admins.py deactivate --email <email>
    python scripts/manage_admins.py activate --email <email>
    python scripts/manage_admins.py seed [--email1 <email>] [--email2 <email>]
"""
import argparse
import os
import re
import sys
import uuid
from datetime import datetime, timezone

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import psycopg
from psycopg.rows import dict_row
from admin_backend.config import settings

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def get_db_connection():
    dsn = settings.resolve_postgres_dsn()
    if not dsn:
        print("Error: PostgreSQL DSN not configured in environment.", file=sys.stderr)
        sys.exit(1)
    return psycopg.connect(dsn, row_factory=dict_row)


def log_admin_audit(cur, actor_username: str, action: str, resource_id: str, details: dict):
    """Log admin management action to audit_logs table."""
    try:
        cur.execute("""
            INSERT INTO audit_logs (id, timestamp, actor_username, actor_role, action, resource_type, resource_id, status, details, client_ip)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            str(uuid.uuid4()),
            datetime.now(timezone.utc),
            actor_username,
            "admin",
            action,
            "admin_user",
            resource_id,
            "success",
            psycopg.types.json.Jsonb(details),
            "127.0.0.1"
        ))
    except Exception as e:
        print(f"Warning: Failed to record audit log: {e}", file=sys.stderr)


def cmd_add(args):
    email = (args.email or "").strip().lower()
    if not email or not EMAIL_REGEX.match(email):
        print(f"Error: Invalid email format '{args.email}'", file=sys.stderr)
        sys.exit(1)

    name = (args.name or "").strip() or email.split("@")[0]
    created_by = (args.created_by or "cli").strip()

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, email, is_active FROM admin_users WHERE LOWER(email) = %s;", (email,))
            existing = cur.fetchone()
            if existing:
                print(f"Admin with email '{email}' already exists (Active: {existing['is_active']}, ID: {existing['id']}).")
                return

            admin_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc)
            cur.execute("""
                INSERT INTO admin_users (id, username, email, name, role, is_active, created_at, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
            """, (admin_id, email, email, name, "admin", True, now, created_by))

            log_admin_audit(cur, actor_username=created_by, action="ADMIN_CREATED", resource_id=email, details={
                "admin_id": admin_id,
                "email": email,
                "name": name,
                "created_by": created_by
            })
            conn.commit()
            print(f"Successfully added admin '{email}' (ID: {admin_id}, Name: '{name}').")


def cmd_list(args):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, username, email, name, role, is_active, created_at, last_login_at, created_by
                FROM admin_users
                ORDER BY created_at ASC;
            """)
            rows = cur.fetchall()

    if not rows:
        print("No admin users found.")
        return

    print("\n" + "=" * 110)
    print(f"{'Email':<32} {'Name':<20} {'Active':<8} {'Role':<8} {'Last Login':<22} {'Created By':<12}")
    print("-" * 110)
    for r in rows:
        email = r["email"] or r["username"] or "unknown"
        name = r["name"] or "-"
        active = "Yes" if r["is_active"] else "No"
        role = r["role"] or "admin"
        last_login = r["last_login_at"].strftime("%Y-%m-%d %H:%M:%S") if r["last_login_at"] else "Never"
        created_by = r["created_by"] or "system"
        print(f"{email:<32} {name:<20} {active:<8} {role:<8} {last_login:<22} {created_by:<12}")
    print("=" * 110 + f"\nTotal admins: {len(rows)}\n")


def cmd_deactivate(args):
    email = (args.email or "").strip().lower()
    if not email:
        print("Error: --email is required", file=sys.stderr)
        sys.exit(1)

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, email, is_active FROM admin_users WHERE LOWER(email) = %s;", (email,))
            target = cur.fetchone()
            if not target:
                print(f"Error: Admin with email '{email}' not found.", file=sys.stderr)
                sys.exit(1)

            if not target["is_active"]:
                print(f"Admin '{email}' is already deactivated.")
                return

            # Check active count
            cur.execute("SELECT COUNT(*) as count FROM admin_users WHERE is_active = TRUE;")
            active_count = cur.fetchone()["count"]

            if active_count <= 1:
                print("Error: Refusing to deactivate: cannot deactivate the last active admin.", file=sys.stderr)
                sys.exit(1)

            cur.execute("UPDATE admin_users SET is_active = FALSE WHERE id = %s;", (target["id"],))
            log_admin_audit(cur, actor_username="cli", action="ADMIN_DEACTIVATED", resource_id=email, details={
                "admin_id": str(target["id"]),
                "email": email
            })
            conn.commit()
            print(f"Successfully deactivated admin '{email}'.")


def cmd_activate(args):
    email = (args.email or "").strip().lower()
    if not email:
        print("Error: --email is required", file=sys.stderr)
        sys.exit(1)

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, email, is_active FROM admin_users WHERE LOWER(email) = %s;", (email,))
            target = cur.fetchone()
            if not target:
                print(f"Error: Admin with email '{email}' not found.", file=sys.stderr)
                sys.exit(1)

            if target["is_active"]:
                print(f"Admin '{email}' is already active.")
                return

            cur.execute("UPDATE admin_users SET is_active = TRUE WHERE id = %s;", (target["id"],))
            log_admin_audit(cur, actor_username="cli", action="ADMIN_ACTIVATED", resource_id=email, details={
                "admin_id": str(target["id"]),
                "email": email
            })
            conn.commit()
            print(f"Successfully activated admin '{email}'.")


def cmd_seed(args):
    """Seed initial admins from args or environment."""
    email1 = args.email1 or os.getenv("ADMIN_EMAIL_1") or "devaraddi31@gmail.com"
    email2 = args.email2 or os.getenv("ADMIN_EMAIL_2") or "ananyaushetty97@gmail.com"

    for email in [email1, email2]:
        if email:
            cmd_add(argparse.Namespace(email=email, name="", created_by="seed"))


def main():
    parser = argparse.ArgumentParser(description="Manage Admin Users")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # add
    parser_add = subparsers.add_parser("add", help="Add a new admin email")
    parser_add.add_argument("--email", required=True, help="Admin email address")
    parser_add.add_argument("--name", default="", help="Admin display name")
    parser_add.add_argument("--created-by", default="cli", help="Creator username or identifier")
    parser_add.set_defaults(func=cmd_add)

    # list
    parser_list = subparsers.add_parser("list", help="List all admin users")
    parser_list.set_defaults(func=cmd_list)

    # deactivate
    parser_deact = subparsers.add_parser("deactivate", help="Deactivate an admin user")
    parser_deact.add_argument("--email", required=True, help="Admin email address to deactivate")
    parser_deact.set_defaults(func=cmd_deactivate)

    # activate
    parser_act = subparsers.add_parser("activate", help="Activate an admin user")
    parser_act.add_argument("--email", required=True, help="Admin email address to activate")
    parser_act.set_defaults(func=cmd_activate)

    # seed
    parser_seed = subparsers.add_parser("seed", help="Seed initial admin emails")
    parser_seed.add_argument("--email1", default=None, help="First admin email")
    parser_seed.add_argument("--email2", default=None, help="Second admin email")
    parser_seed.set_defaults(func=cmd_seed)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
