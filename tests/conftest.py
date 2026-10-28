
import pytest
from sqlalchemy import create_engine, event, text


@pytest.fixture(autouse=True)
def isolated_test_database(monkeypatch, tmp_path):
    """Give every test a fresh demo database without touching Olist."""
    from app.db import database, schema

    test_db_path = tmp_path / "test.db"
    test_engine = create_engine(
        f"sqlite:///{test_db_path}",
        future=True,
    )

    @event.listens_for(test_engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    with test_engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE departments (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE
            )
        """))
        connection.execute(text("""
            CREATE TABLE employees (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                department_id INTEGER NOT NULL,
                salary REAL NOT NULL,
                city TEXT NOT NULL,
                FOREIGN KEY (department_id) REFERENCES departments(id)
            )
        """))
        connection.execute(text("""
            INSERT INTO departments (id, name)
            VALUES (1, 'Engineering'), (2, 'Sales'), (3, 'HR')
        """))
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

    monkeypatch.setattr(database, "engine", test_engine)
    monkeypatch.setattr(schema, "engine", test_engine)

    yield

    test_engine.dispose()
