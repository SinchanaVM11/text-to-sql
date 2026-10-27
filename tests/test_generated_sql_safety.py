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
