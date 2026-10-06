#!/usr/bin/env python3
"""
Seed development accounts.

Creates one user per role so every screen in the app can be opened without
having to create accounts by hand, plus a second admin. Re-running is safe:
existing usernames are left untouched rather than having their password reset,
so this never silently changes the password of an account you already use.

    ./run.sh seed-dev

Why this is a script and not an INSERT pasted into psql: the role strings are
load-bearing. `is_coordinator()` in app.py matches on the exact lowercase forms
' school iqac coordinator', 'campus iqac coordinator' and
'iqac core team member', and the login redirect at app.py:807 switches on
`session["role"].lower()` against the same list. A typo like 'Coordinator'
creates an account that lands on /dashboard instead of /iqac_dashboard and
looks like a routing bug rather than bad data.

Development only. Every account gets the same throwaway password and none are
flagged must_change_password, which is exactly what you must not do on a real
deployment — a seeded admin with a known password and no forced reset is a
credential-stuffing target. This script is not called by app.py on startup, so
it can only ever run when someone runs it on purpose.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from werkzeug.security import generate_password_hash

from db import get_cursor, get_db_connection

# One password for all of them. Never shared with a real deployment.
DEV_PASSWORD = "DevPass123!"

# (username, role, full_name, designation, department, emp_id)
#
# 'role' is matched verbatim by is_coordinator() and by the login redirect, so
# these strings must stay exactly as written.
DEV_USERS = [
    (
        "devadmin",
        "Admin",
        "Dev Admin",
        "Director, IQAC",
        "IQAC",
        "CU9001",
    ),
    (
        "devfaculty",
        "Faculty",
        "Dev Faculty",
        "Assistant Professor",
        "Computer Applications",
        "CU9101",
    ),
    (
        "devcoordinator",
        "School IQAC Coordinator",
        "Dev Coordinator",
        "Professor",
        "Computer Applications",
        "CU9201",
    ),
    (
        "devsecretary",
        "Secretary",
        "Dev Secretary",
        "Administrative Officer",
        "Mathematics",
        "CU9301",
    ),
]


def seed():
    conn = get_db_connection()
    cursor = get_cursor(conn)

    created = 0
    skipped = []

    for username, role, full_name, designation, department, emp_id in DEV_USERS:
        cursor.execute("SELECT 1 FROM users WHERE username=%s", (username,))
        if cursor.fetchone():
            skipped.append(username)
            continue

        cursor.execute(
            """
            INSERT INTO users
                (username, password, emp_id, email, gender, designation,
                 department, role, full_name, must_change_password)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, FALSE)
            """,
            (
                username,
                generate_password_hash(DEV_PASSWORD),
                emp_id,
                f"{username}@example.edu",
                "Female",
                designation,
                department,
                role,
                full_name,
            ),
        )
        created += 1

    conn.commit()

    print(f"created {created} development account(s)")
    for username, role, *_ in DEV_USERS:
        if username in skipped:
            print(f"  {username:<16} already exists, left unchanged")

    if created:
        print(f"\nall of them use the password: {DEV_PASSWORD}")
        print("admin / devadmin land on /admin; the rest land on their role home.")

    conn.close()


if __name__ == "__main__":
    seed()