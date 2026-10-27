import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.services.sql_generator import (
    SQLGenerationError,
    generate_sql,
)


SCHEMA = {
    "tables": [
        {
            "name": "employees",
            "columns": [
                {"name": "name", "type": "TEXT"},
                {"name": "salary", "type": "REAL"},
            ],
        }
    ]
}


def mock_ollama_response(model_output):
    response = MagicMock()
    response.json.return_value = {"response": model_output}
    response.raise_for_status.return_value = None
    return response


def test_generates_sql_from_json_response():
    response = mock_ollama_response(
        json.dumps({"sql": "SELECT name FROM employees"})
    )

    with patch(
        "app.services.sql_generator.httpx.Client"
    ) as client_class:
        client_class.return_value.__enter__.return_value.post.return_value = (
            response
        )

        result = generate_sql("List employees", SCHEMA)

    assert result == {"sql": "SELECT name FROM employees"}


def test_accepts_sql_wrapped_in_markdown_fences():
    response = mock_ollama_response(
        "```sql\nSELECT name FROM employees\n```"
    )

    with patch(
        "app.services.sql_generator.httpx.Client"
    ) as client_class:
        client_class.return_value.__enter__.return_value.post.return_value = (
            response
        )

        result = generate_sql("List employees", SCHEMA)

    assert result["sql"] == "SELECT name FROM employees"


@pytest.mark.parametrize(
    "question,schema",
    [
        ("", SCHEMA),
        ("   ", SCHEMA),
        ("List employees", None),
        ("List employees", []),
    ],
)
def test_rejects_invalid_inputs(question, schema):
    with pytest.raises(ValueError):
        generate_sql(question, schema)


def test_rejects_empty_model_response():
    response = mock_ollama_response("   ")

    with patch(
        "app.services.sql_generator.httpx.Client"
    ) as client_class:
        client_class.return_value.__enter__.return_value.post.return_value = (
            response
        )

        with pytest.raises(SQLGenerationError, match="empty response"):
            generate_sql("List employees", SCHEMA)


def test_rejects_json_without_sql():
    response = mock_ollama_response('{"message": "No query available"}')

    with patch(
        "app.services.sql_generator.httpx.Client"
    ) as client_class:
        client_class.return_value.__enter__.return_value.post.return_value = (
            response
        )

        with pytest.raises(SQLGenerationError, match="could not produce"):
            generate_sql("List employees", SCHEMA)


def test_handles_ollama_timeout():
    with patch(
        "app.services.sql_generator.httpx.Client"
    ) as client_class:
        client_class.return_value.__enter__.return_value.post.side_effect = (
            httpx.ReadTimeout("Request timed out")
        )

        with pytest.raises(SQLGenerationError, match="timed out"):
            generate_sql("List employees", SCHEMA)


def test_handles_ollama_connection_failure():
    with patch(
        "app.services.sql_generator.httpx.Client"
    ) as client_class:
        client_class.return_value.__enter__.return_value.post.side_effect = (
            httpx.ConnectError("Connection refused")
        )

        with pytest.raises(SQLGenerationError, match="Cannot connect"):
            generate_sql("List employees", SCHEMA)


def test_handles_ollama_http_error():
    request = httpx.Request(
        "POST", "http://localhost:11434/api/generate"
    )
    response = httpx.Response(500, request=request)

    with patch(
        "app.services.sql_generator.httpx.Client"
    ) as client_class:
        client_class.return_value.__enter__.return_value.post.side_effect = (
            httpx.HTTPStatusError(
                "Server error",
                request=request,
                response=response,
            )
        )

        with pytest.raises(SQLGenerationError, match="HTTP 500"):
            generate_sql("List employees", SCHEMA)


def test_handles_invalid_ollama_json_response():
    response = MagicMock()
    response.json.side_effect = ValueError("Invalid JSON")
    response.raise_for_status.return_value = None

    with patch(
        "app.services.sql_generator.httpx.Client"
    ) as client_class:
        client_class.return_value.__enter__.return_value.post.return_value = (
            response
        )

        with pytest.raises(SQLGenerationError, match="invalid response"):
            generate_sql("List employees", SCHEMA)
