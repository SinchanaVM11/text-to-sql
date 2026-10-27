"""Deterministic schema selection for natural-language SQL questions."""

import re
from collections import defaultdict


TOKEN_PATTERN = re.compile(r"[a-zA-Z][a-zA-Z0-9]*")

# Words that usually do not identify a database entity.
STOP_WORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been",
    "to", "of", "in", "on", "at", "by", "for", "from", "with",
    "and", "or", "as", "it", "its", "that", "this", "these",
    "those", "i", "we", "you", "me", "my", "our", "show", "give",
    "get", "find", "tell", "list", "display", "please", "what",
    "which", "who", "how", "many", "much", "all", "total",
    "number", "count", "average", "avg", "sum", "maximum", "minimum",
    "highest", "lowest", "top", "bottom", "most", "least",
    "each", "every", "per", "group", "grouped", "order", "sorted",
    "sort", "descending", "ascending", "than", "where", "whose",
    "have", "has", "had", "do", "does", "did", "can", "could",
}


def _tokens(value: str) -> set[str]:
    """Split identifiers and natural-language text into lowercase tokens."""
    expanded = re.sub(r"([a-z])([A-Z])", r"\1 \2", value)
    return {
        token.lower()
        for token in TOKEN_PATTERN.findall(expanded.replace("_", " "))
        if token.lower() not in STOP_WORDS and len(token) > 1
    }


def plan_schema(question: str, schema: dict) -> dict:
    """Select likely relevant tables and their connected foreign-key tables.

    Returns:
        {
            "schema": {"tables": [...]},
            "selected_tables": [...],
            "matched_terms": [...],
            "strategy": "keyword_match" | "full_schema_fallback"
        }

    This is a heuristic planner, not a semantic correctness guarantee.
    """
    if not isinstance(question, str) or not question.strip():
        raise ValueError("Question cannot be empty.")

    if not isinstance(schema, dict) or not isinstance(schema.get("tables"), list):
        raise ValueError("Schema must contain a tables list.")

    tables = schema["tables"]
    if not tables:
        raise ValueError("Schema contains no tables.")

    question_tokens = _tokens(question)
    table_tokens = {}
    column_tokens = {}
    scores = defaultdict(int)
    matched_terms = set()

    for table in tables:
        name = table.get("name", "")
        current_table_tokens = _tokens(name)
        table_tokens[name] = current_table_tokens

        current_column_tokens = set()
        for column in table.get("columns", []):
            current_column_tokens.update(_tokens(column.get("name", "")))
        column_tokens[name] = current_column_tokens

        table_matches = current_table_tokens & question_tokens
        column_matches = current_column_tokens & question_tokens

        # Table-name matches are stronger than individual column matches.
        scores[name] += 3 * len(table_matches)
        scores[name] += len(column_matches)
        matched_terms.update(table_matches | column_matches)

    best_score = max(scores.values(), default=0)

    if best_score == 0:
        # Never return an empty context just because names do not match.
        return {
            "schema": schema,
            "selected_tables": [table["name"] for table in tables],
            "matched_terms": [],
            "strategy": "full_schema_fallback",
        }

    selected = {
        name for name, score in scores.items()
        if score > 0
    }

    # Include tables directly connected to selected tables through
    # declared foreign keys, so likely joins remain possible.
    table_by_name = {table["name"]: table for table in tables}
    neighbours = defaultdict(set)

    for table in tables:
        source = table["name"]
        for foreign_key in table.get("foreign_keys", []):
            target = foreign_key.get("references_table")
            if target in table_by_name:
                neighbours[source].add(target)
                neighbours[target].add(source)

    related = set()
    for name in selected:
        related.update(neighbours[name])

    selected.update(related)

    focused_tables = [
        table for table in tables
        if table.get("name") in selected
    ]

    return {
        "schema": {"tables": focused_tables},
        "selected_tables": [table["name"] for table in focused_tables],
        "matched_terms": sorted(matched_terms),
        "strategy": "keyword_match",
    }
