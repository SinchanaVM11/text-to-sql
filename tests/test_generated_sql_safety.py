from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.sql_generator import SQLGenerationError


def test_generated_safe_sql_executes():
    with patch(
        "app.main.generate_sql",
        return_value={"sql": "SELECT name FROM employees"},
    ) as mock_generate:
        with TestClient(app) as client:
            response = client.post(
                "/v1/query",
                json={"question": "List employee names"},
            )

    assert response.status_code == 200
    body = response.json()
    assert body["columns"] == ["name"]
    assert body["row_count"] > 0
    mock_generate.assert_called_once()


def test_generated_delete_sql_is_rejected():
    with patch(
        "app.main.generate_sql",
        return_value={"sql": "DROP TABLE employees"},
    ):
        with TestClient(app) as client:
            response = client.post(
                "/v1/query",
                json={"question": "Remove all employees"},
            )

    assert response.status_code == 400


def test_generated_unknown_table_is_rejected():
    with patch(
        "app.main.generate_sql",
        return_value={"sql": "SELECT * FROM secret_data"},
    ):
        with TestClient(app) as client:
            response = client.post(
                "/v1/query",
                json={"question": "Show secret data"},
            )

    assert response.status_code == 400


def test_ollama_generation_failure_returns_502():
    with patch(
        "app.main.generate_sql",
        side_effect=SQLGenerationError("Ollama timed out"),
    ):
        with TestClient(app) as client:
            response = client.post(
                "/v1/query",
                json={"question": "List employee names"},
            )

    assert response.status_code == 502
    assert response.json()["detail"] == "Ollama timed out"


def test_planner_schema_is_passed_to_sql_generator():
    focused_schema = {
        "tables": [
            {
                "name": "employees",
                "columns": [{"name": "name", "type": "TEXT"}],
                "primary_key": ["id"],
                "foreign_keys": [],
            }
        ]
    }
    planning_result = {
        "schema": focused_schema,
        "selected_tables": ["employees"],
        "matched_terms": ["employees"],
        "strategy": "keyword_match",
    }

    with (
        patch("app.main.plan_schema", return_value=planning_result) as planner,
        patch(
            "app.main.generate_sql",
            return_value={"sql": "SELECT name FROM employees"},
        ) as generator,
    ):
        with TestClient(app) as client:
            response = client.post(
                "/v1/query",
                json={"question": "List employee names"},
            )

    assert response.status_code == 200
    planner.assert_called_once()
    generator.assert_called_once_with(
        "List employee names",
        focused_schema,
    )
    assert response.json()["planning"] == {
        "selected_tables": ["employees"],
        "matched_terms": ["employees"],
        "strategy": "keyword_match",
    }


def test_caller_supplied_sql_does_not_invoke_planner():
    with patch("app.main.plan_schema") as planner:
        with TestClient(app) as client:
            response = client.post(
                "/v1/query",
                json={
                    "question": "List employee names",
                    "sql": "SELECT name FROM employees",
                },
            )

    assert response.status_code == 200
    planner.assert_not_called()
    assert response.json()["planning"] is None
