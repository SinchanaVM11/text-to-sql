import json
import re

import httpx

from app.core.config import settings


class SQLGenerationError(RuntimeError):
    """Raised when the local model cannot generate SQL."""


def _build_prompt(question: str, schema: dict, correction_context: dict | None = None) -> str:
    schema_json = json.dumps(schema, ensure_ascii=False, indent=2)

    correction_instructions = ""
    if correction_context:
        failed_sql = str(correction_context.get("failed_sql", ""))[:2000]
        error_message = str(correction_context.get("error", ""))[:500]
        correction_instructions = f"""
Previous attempt failed during database execution.

Failed SQL:
{failed_sql}

Database error:
{error_message}

Correct the SQL using only the supplied schema. Return corrected SQL
in the required JSON format.
"""

    return f"""
You are a Text-to-SQL engine.

Convert the user's question into one SQLite SELECT query.

Rules:
1. Use only tables and columns present in the supplied schema.
2. Generate exactly one read-only SELECT query.
3. Never generate INSERT, UPDATE, DELETE, DROP, ALTER, CREATE,
   PRAGMA, ATTACH, DETACH, or other write or administrative statements.
4. Do not invent tables, columns, or relationships.
5. Use SQLite-compatible SQL.
6. Do not include explanations or Markdown code fences.
7. If the question cannot be answered using the schema, return an
   empty SQL string.
8. Return a JSON object with exactly one key: "sql".

Database schema:
{schema_json}

{correction_instructions}

User question:
{question}
""".strip()


def generate_sql(
    question: str,
    schema: dict,
    correction_context: dict | None = None,
) -> dict:
    """Generate SQL using the configured local Ollama model."""
    if not question or not question.strip():
        raise ValueError("Question cannot be empty.")

    if not isinstance(schema, dict):
        raise ValueError("Schema must be a dictionary.")

    url = f"{settings.ollama_base_url.rstrip('/')}/api/generate"

    payload = {
        "model": settings.ollama_model,
        "prompt": _build_prompt(question.strip(), schema, correction_context),
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0,
        },
    }

    try:
        with httpx.Client(
            timeout=settings.ollama_timeout_seconds
        ) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
    except httpx.TimeoutException as exc:
        raise SQLGenerationError(
            "Ollama timed out while generating SQL."
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise SQLGenerationError(
            f"Ollama returned HTTP {exc.response.status_code}."
        ) from exc
    except httpx.RequestError as exc:
        raise SQLGenerationError(
            "Cannot connect to Ollama. Check that Ollama is running."
        ) from exc

    try:
        result = response.json()
        model_output = result.get("response", "")
    except (ValueError, AttributeError) as exc:
        raise SQLGenerationError(
            "Ollama returned an invalid response."
        ) from exc

    if not isinstance(model_output, str) or not model_output.strip():
        raise SQLGenerationError(
            "Ollama returned an empty response."
        )

    try:
        parsed = json.loads(model_output)
        sql = parsed.get("sql", "") if isinstance(parsed, dict) else ""
    except json.JSONDecodeError:
        # Be tolerant of models that return SQL without valid JSON.
        sql = re.sub(
            r"^```(?:sql)?\s*|\s*```$",
            "",
            model_output.strip(),
            flags=re.IGNORECASE,
        ).strip()

    if not isinstance(sql, str) or not sql.strip():
        raise SQLGenerationError(
            "The model could not produce a SQL query for this question."
        )

    return {"sql": sql.strip()}
