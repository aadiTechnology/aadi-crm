"""Apply CRM PostgreSQL migrations.

Run from the backend directory:

    python -m app.migrate

The command reads CRM_DATABASE_URL. It does not open SQLite and does not copy rows.
CRM_DATABASE_SSLMODE selects verify-full unless disable is set explicitly for a
loopback host.
"""

from app.db import apply_postgres_migrations, database_url


def main() -> None:
    if not database_url():
        raise SystemExit(
            "CRM_DATABASE_URL is not set. PostgreSQL migrations were not applied and SQLite was not opened."
        )
    database_name = apply_postgres_migrations()
    print(f"PostgreSQL migrations are current for database {database_name}.")


if __name__ == "__main__":
    main()
