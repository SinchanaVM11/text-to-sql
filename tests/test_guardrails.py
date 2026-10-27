import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.sql_guardrails import SQLGuardrailError, validate_sql


ALLOWED_TABLES = {"employees", "departments"}


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM employees",
        "UPDATE employees SET salary = 0",
        "INSERT INTO employees (name) VALUES ('Bad')",
        "DROP TABLE employees",
        "ALTER TABLE employees ADD COLUMN bad TEXT",
        "CREATE TABLE bad (id INT)",
    ],
)
def test_rejects_write_and_ddl_statements(sql):
    with pytest.raises(SQLGuardrailError):
        validate_sql(sql, ALLOWED_TABLES)


def test_rejects_multiple_statements():
    with pytest.raises(SQLGuardrailError):
        validate_sql(
            "SELECT * FROM employees; DROP TABLE employees",
            ALLOWED_TABLES,
        )


def test_rejects_empty_sql():
    with pytest.raises(SQLGuardrailError):
        validate_sql("   ", ALLOWED_TABLES)


def test_adds_default_limit():
    sql = validate_sql(
        "SELECT name FROM employees",
        ALLOWED_TABLES,
    )
    assert "LIMIT 1000" in sql.upper()


def test_caps_excessive_limit():
    sql = validate_sql(
        "SELECT name FROM employees LIMIT 999999",
        ALLOWED_TABLES,
    )
    assert "LIMIT 1000" in sql.upper()


def test_preserves_smaller_limit():
    sql = validate_sql(
        "SELECT name FROM employees LIMIT 5",
        ALLOWED_TABLES,
    )
    assert "LIMIT 5" in sql.upper()


def test_allows_select_with_filter():
    sql = validate_sql(
        "SELECT name FROM employees WHERE city = 'Bengaluru'",
        ALLOWED_TABLES,
    )
    assert "SELECT" in sql.upper()
    assert "Bengaluru" in sql


def test_rejects_unknown_table():
    with pytest.raises(SQLGuardrailError):
        validate_sql(
            "SELECT * FROM secret_data",
            ALLOWED_TABLES,
        )


def test_rejects_sqlite_internal_table():
    with pytest.raises(SQLGuardrailError):
        validate_sql(
            "SELECT * FROM sqlite_master",
            ALLOWED_TABLES,
        )


def test_rejects_schema_qualified_table():
    with pytest.raises(SQLGuardrailError):
        validate_sql(
            "SELECT * FROM main.employees",
            ALLOWED_TABLES,
        )


def test_allows_join_between_permitted_tables():
    sql = validate_sql(
        """
        SELECT employees.name, departments.name AS department
        FROM employees
        JOIN departments
          ON employees.department_id = departments.id
        """,
        ALLOWED_TABLES,
    )
    assert "JOIN" in sql.upper()


def test_allows_cte_using_permitted_table():
    sql = validate_sql(
        """
        WITH high_earners AS (
            SELECT name, salary
            FROM employees
            WHERE salary > 70000
        )
        SELECT name, salary
        FROM high_earners
        """,
        ALLOWED_TABLES,
    )
    assert "high_earners" in sql


def test_rejects_blocked_file_function():
    with pytest.raises(SQLGuardrailError):
        validate_sql(
            "SELECT readfile('/etc/passwd')",
            ALLOWED_TABLES,
        )


def test_rejects_empty_allowlist():
    with pytest.raises(SQLGuardrailError):
        validate_sql(
            "SELECT name FROM employees",
            set(),
        )


def test_health_endpoint():
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_schema_endpoint():
    with TestClient(app) as client:
        response = client.get("/v1/schema")

    assert response.status_code == 200
    table_names = {
        table["name"]
        for table in response.json()["tables"]
    }
    assert {"employees", "departments"}.issubset(table_names)


def test_query_endpoint_executes_safe_sql():
    with TestClient(app) as client:
        response = client.post(
            "/v1/query",
            json={
                "question": "List employees in Bengaluru",
                "sql": (
                    "SELECT name, city FROM employees "
                    "WHERE city = 'Bengaluru'"
                ),
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["row_count"] == 2
    assert all(
        row["city"] == "Bengaluru"
        for row in body["rows"]
    )


def test_query_endpoint_blocks_delete():
    with TestClient(app) as client:
        response = client.post(
            "/v1/query",
            json={
                "question": "Delete every employee",
                "sql": "DELETE FROM employees",
            },
        )

    assert response.status_code == 400


def test_query_endpoint_blocks_unknown_table():
    with TestClient(app) as client:
        response = client.post(
            "/v1/query",
            json={
                "question": "Show secret data",
                "sql": "SELECT * FROM secret_data",
            },
        )

    assert response.status_code == 400


@pytest.mark.parametrize(
    "function_call",
    [
        "readfile('/etc/passwd')",
        "writefile('/tmp/guardrail-test.txt', 'test')",
        "load_extension('malicious_extension')",
        "fts3_tokenizer('simple')",
        "READFILE('/etc/passwd')",
        "WRITEFILE('/tmp/test.txt', 'test')",
        "LOAD_EXTENSION('malicious_extension')",
    ],
)
def test_rejects_blocked_functions_case_insensitively(function_call):
    with pytest.raises(SQLGuardrailError):
        validate_sql(
            f"SELECT {function_call}",
            ALLOWED_TABLES,
        )


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT name FROM employees LIMIT 0",
        "SELECT name FROM employees LIMIT -1",
        "SELECT name FROM employees LIMIT 1.5",
        "SELECT name FROM employees LIMIT '10'",
        "SELECT name FROM employees LIMIT 1 + 2",
    ],
)
def test_rejects_invalid_limit_values(sql):
    with pytest.raises(SQLGuardrailError):
        validate_sql(sql, ALLOWED_TABLES)
