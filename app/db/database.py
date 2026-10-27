from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine

from app.core.config import settings


def _create_engine() -> Engine:
    url = settings.database_url

    if url.startswith("sqlite:///"):
        database_path = Path(url.removeprefix("sqlite:///"))
        database_path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(url, future=True)

    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def enable_foreign_keys(dbapi_connection, _connection_record):
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

    return engine


engine = _create_engine()


def initialize_database() -> None:
    """Create a small demonstration dataset if it doesn't exist."""
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS departments (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE
            )
        """))

        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS employees (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                department_id INTEGER NOT NULL,
                salary REAL NOT NULL,
                city TEXT NOT NULL,
                FOREIGN KEY (department_id) REFERENCES departments(id)
            )
        """))

        department_count = connection.execute(
            text("SELECT COUNT(*) FROM departments")
        ).scalar_one()

        if department_count == 0:
            connection.execute(text("""
                INSERT INTO departments (id, name)
                VALUES (1, 'Engineering'), (2, 'Sales'), (3, 'HR')
            """))

        employee_count = connection.execute(
            text("SELECT COUNT(*) FROM employees")
        ).scalar_one()

        if employee_count == 0:
            connection.execute(text("""
                INSERT INTO employees
                    (id, name, department_id, salary, city)
                VALUES
                    (1, 'Asha', 1, 85000, 'Bengaluru'),
                    (2, 'Ravi', 1, 92000, 'Mysuru'),
                    (3, 'Meera', 2, 68000, 'Bengaluru'),
                    (4, 'Arjun', 2, 72000, 'Hubballi'),
                    (5, 'Nisha', 3, 61000, 'Mysuru')
            """))


def execute_read_only(sql: str) -> tuple[list[str], list[dict]]:
    """Execute validated SQL in SQLite read-only query mode."""
    if not settings.database_url.startswith("sqlite"):
        raise RuntimeError(
            "Read-only execution is currently implemented for SQLite only."
        )

    with engine.connect() as connection:
        # PRAGMA starts SQLAlchemy's implicit transaction, so commit it
        # before executing the query in its own transaction.
        connection.exec_driver_sql("PRAGMA query_only=ON")
        connection.commit()

        try:
            with connection.begin():
                result = connection.execute(text(sql))
                columns = list(result.keys())
                rows = [
                    dict(row)
                    for row in result.mappings().fetchmany(settings.max_rows)
                ]

            return columns, rows
        finally:
            # End any active transaction before changing the connection mode.
            connection.rollback()
            connection.exec_driver_sql("PRAGMA query_only=OFF")
            connection.commit()
