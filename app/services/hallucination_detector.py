import re


def check_result_sanity(
    question: str,
    sql: str,
    rows: list[dict],
    columns: list[str],
) -> dict:
    """
    Apply simple sanity checks.

    These are heuristics, not a semantic proof that the answer is correct.
    """
    warnings = []

    if not columns:
        warnings.append("The query returned no columns.")

    if re.search(r"\b(count|sum|avg|min|max)\s*\(", sql, re.IGNORECASE):
        if len(rows) != 1:
            warnings.append(
                "An aggregate query returned a number of rows other than one."
            )

    if not rows:
        warnings.append("The query returned no matching rows.")

    return {
        "passed": len(warnings) == 0,
        "warnings": warnings,
        "method": "basic_result_heuristics",
    }
