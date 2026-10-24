import sqlglot
from sqlglot import exp

from app.core.config import settings


class SQLGuardrailError(ValueError):
    """Raised when SQL fails a safety check."""


# These functions can expose files, load extensions, or access
# functionality that should not be available to generated queries.
BLOCKED_FUNCTIONS = {
    "load_extension",
    "readfile",
    "writefile",
    "fts3_tokenizer",
}


def _validate_tables(
    statement: exp.Expression,
    allowed_tables: set[str],
) -> None:
    """Reject references to tables outside the permitted schema."""
    # CTE names are temporary query aliases, not physical tables.
    cte_names = {
        cte.alias_or_name.lower()
        for cte in statement.find_all(exp.CTE)
        if cte.alias_or_name
    }

    for table in statement.find_all(exp.Table):
        table_name = table.name.lower()

        # Schema-qualified names and attached databases are not allowed.
        if table.db or table.catalog:
            raise SQLGuardrailError(
                "Schema-qualified and cross-database access is not allowed."
            )

        # Allow references to declared common table expressions.
        if table_name in cte_names:
            continue

        if table_name not in allowed_tables:
            raise SQLGuardrailError(
                f"Access to table '{table.name}' is not allowed."
            )


def _validate_functions(statement: exp.Expression) -> None:
    """Reject explicitly disallowed function calls."""
    for function in statement.find_all(exp.Func):
        function_name = function.sql_name().lower()

        if isinstance(function, exp.Anonymous):
            function_name = function.name.lower()

        if function_name in BLOCKED_FUNCTIONS:
            raise SQLGuardrailError(
                f"Function '{function_name}' is not allowed."
            )


def validate_sql(
    sql: str,
    allowed_tables: set[str],
) -> str:
    """Validate one read-only SELECT and enforce its result row limit."""
    if not sql or not sql.strip():
        raise SQLGuardrailError("SQL query cannot be empty.")

    if not allowed_tables:
        raise SQLGuardrailError(
            "No tables are configured for query access."
        )

    normalized_allowed_tables = {
        name.lower() for name in allowed_tables
    }

    try:
        statements = sqlglot.parse(sql, read="sqlite")
    except sqlglot.errors.ParseError as exc:
        raise SQLGuardrailError("Invalid SQL syntax.") from exc

    statements = [
        statement
        for statement in statements
        if statement is not None
    ]

    if len(statements) != 1:
        raise SQLGuardrailError(
            "Exactly one SQL statement is allowed."
        )

    statement = statements[0]

    # Intentionally accept only a SELECT root. Other statement types,
    # including write operations and set-operation roots, are rejected.
    if not isinstance(statement, exp.Select):
        raise SQLGuardrailError(
            "Only SELECT queries are allowed."
        )

    if statement.args.get("into"):
        raise SQLGuardrailError("SELECT INTO is not allowed.")

    _validate_tables(statement, normalized_allowed_tables)
    _validate_functions(statement)

    limit = statement.args.get("limit")

    if limit is None:
        statement = statement.limit(settings.max_rows)
    else:
        limit_expression = limit.expression

        if not isinstance(limit_expression, exp.Literal):
            raise SQLGuardrailError(
                "LIMIT must be a numeric literal."
            )

        if limit_expression.is_string:
            raise SQLGuardrailError(
                "LIMIT must be a numeric literal."
            )

        try:
            requested_limit = int(limit_expression.this)
        except (TypeError, ValueError) as exc:
            raise SQLGuardrailError("Invalid LIMIT value.") from exc

        if requested_limit < 1:
            raise SQLGuardrailError(
                "LIMIT must be at least 1."
            )

        if requested_limit > settings.max_rows:
            statement = statement.limit(settings.max_rows)

    return statement.sql(dialect="sqlite")
