import re

import sqlglot
from sqlglot import exp


AGGREGATE_PATTERN = re.compile(
    r"\b(count|sum|avg|min|max)\s*\(",
    re.IGNORECASE,
)


def check_result_sanity(
    question: str,
    sql: str,
    rows: list[dict],
    columns: list[str],
) -> dict:
    """
    Apply lightweight result sanity checks.

    These heuristics are not a semantic proof that the answer is correct.
    """
    warnings = []

    if not columns:
        warnings.append("The query returned no columns.")

    has_aggregate = bool(AGGREGATE_PATTERN.search(sql))
    has_group_by = False

    try:
        parsed = sqlglot.parse_one(sql, read="sqlite")
        has_group_by = parsed.find(exp.Group) is not None
    except sqlglot.errors.ParseError:
        # Do not make a structural assumption if parsing fails.
        pass

    if has_aggregate and not has_group_by and len(rows) != 1:
        warnings.append(
            "A scalar aggregate query returned a number of rows other than one."
        )

    if not rows:
        warnings.append("The query returned no matching rows.")

    return {
        "passed": len(warnings) == 0,
        "warnings": warnings,
        "method": "basic_result_heuristics",
    }
