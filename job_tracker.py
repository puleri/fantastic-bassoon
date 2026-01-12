#!/usr/bin/env python3
import argparse
import datetime as dt
import sqlite3
from pathlib import Path

def db_path(path_override: str | None) -> Path:
    if path_override:
        return Path(path_override).expanduser()
    return Path.home() / ".job_tracker.db"


def connect_db(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def ensure_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company TEXT NOT NULL,
            role TEXT NOT NULL,
            source TEXT,
            link TEXT,
            status TEXT NOT NULL,
            applied_date TEXT NOT NULL,
            last_action TEXT NOT NULL,
            notes TEXT
        )
        """
    )
    connection.commit()


def today_iso() -> str:
    return dt.date.today().isoformat()


def add_application(args: argparse.Namespace) -> None:
    connection = connect_db(db_path(args.db))
    ensure_schema(connection)
    applied_date = args.applied_date or today_iso()
    last_action = args.last_action or applied_date
    connection.execute(
        """
        INSERT INTO applications (
            company, role, source, link, status, applied_date, last_action, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            args.company,
            args.role,
            args.source,
            args.link,
            args.status,
            applied_date,
            last_action,
            args.notes,
        ),
    )
    connection.commit()
    print("Added application.")


def list_applications(args: argparse.Namespace) -> None:
    connection = connect_db(db_path(args.db))
    ensure_schema(connection)
    query = "SELECT * FROM applications"
    filters = []
    params: list[str] = []
    if args.status:
        filters.append("status = ?")
        params.append(args.status)
    if args.search:
        filters.append("(company LIKE ? OR role LIKE ? OR source LIKE ?)")
        params.extend([f"%{args.search}%"] * 3)
    if filters:
        query += " WHERE " + " AND ".join(filters)
    query += " ORDER BY applied_date DESC, id DESC"
    rows = connection.execute(query, params).fetchall()
    if not rows:
        print("No applications found.")
        return
    for row in rows:
        print(
            f"#{row['id']} | {row['company']} | {row['role']} | {row['status']} "
            f"| applied {row['applied_date']} | last action {row['last_action']}"
        )
        if row["source"] or row["link"]:
            print(f"  source: {row['source'] or '-'} | link: {row['link'] or '-'}")
        if row["notes"]:
            print(f"  notes: {row['notes']}")


def update_application(args: argparse.Namespace) -> None:
    connection = connect_db(db_path(args.db))
    ensure_schema(connection)
    updates = []
    params: list[str] = []
    if args.status:
        updates.append("status = ?")
        params.append(args.status)
    if args.last_action:
        updates.append("last_action = ?")
        params.append(args.last_action)
    if args.notes:
        updates.append("notes = ?")
        params.append(args.notes)
    if not updates:
        print("Nothing to update.")
        return
    params.append(str(args.application_id))
    connection.execute(
        f"UPDATE applications SET {', '.join(updates)} WHERE id = ?",
        params,
    )
    connection.commit()
    print("Updated application.")


def stats(args: argparse.Namespace) -> None:
    connection = connect_db(db_path(args.db))
    ensure_schema(connection)
    total = connection.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
    by_status = connection.execute(
        "SELECT status, COUNT(*) AS count FROM applications GROUP BY status"
    ).fetchall()
    print(f"Total applications: {total}")
    if by_status:
        print("By status:")
        for row in by_status:
            print(f"  {row['status']}: {row['count']}")


def followups(args: argparse.Namespace) -> None:
    connection = connect_db(db_path(args.db))
    ensure_schema(connection)
    cutoff = (dt.date.today() - dt.timedelta(days=args.days)).isoformat()
    rows = connection.execute(
        """
        SELECT * FROM applications
        WHERE last_action <= ? AND status NOT IN ('Rejected', 'Offer')
        ORDER BY last_action ASC
        """,
        (cutoff,),
    ).fetchall()
    if not rows:
        print("No follow-ups needed.")
        return
    print(f"Follow-ups (last action <= {cutoff}):")
    for row in rows:
        print(
            f"#{row['id']} | {row['company']} | {row['role']} | {row['status']} "
            f"| last action {row['last_action']}"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Track job applications with simple commands."
    )
    parser.add_argument("--db", help="Path to database file.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add", help="Add a new application")
    add_parser.add_argument("company")
    add_parser.add_argument("role")
    add_parser.add_argument("--source")
    add_parser.add_argument("--link")
    add_parser.add_argument("--status", default="Applied")
    add_parser.add_argument("--applied-date", dest="applied_date")
    add_parser.add_argument("--last-action", dest="last_action")
    add_parser.add_argument("--notes")
    add_parser.set_defaults(func=add_application)

    list_parser = subparsers.add_parser("list", help="List applications")
    list_parser.add_argument("--status")
    list_parser.add_argument("--search")
    list_parser.set_defaults(func=list_applications)

    update_parser = subparsers.add_parser("update", help="Update an application")
    update_parser.add_argument("application_id", type=int)
    update_parser.add_argument("--status")
    update_parser.add_argument("--last-action", dest="last_action")
    update_parser.add_argument("--notes")
    update_parser.set_defaults(func=update_application)

    stats_parser = subparsers.add_parser("stats", help="Show summary stats")
    stats_parser.set_defaults(func=stats)

    followups_parser = subparsers.add_parser(
        "followups", help="List applications needing follow-up"
    )
    followups_parser.add_argument("--days", type=int, default=7)
    followups_parser.set_defaults(func=followups)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
