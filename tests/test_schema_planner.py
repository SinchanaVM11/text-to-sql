import pytest

from app.services.schema_planner import plan_schema


SCHEMA = {
    "tables": [
        {
            "name": "orders",
            "columns": [
                {"name": "order_id", "type": "TEXT"},
                {"name": "customer_id", "type": "TEXT"},
                {"name": "order_status", "type": "TEXT"},
            ],
            "primary_key": ["order_id"],
            "foreign_keys": [
                {
                    "columns": ["customer_id"],
                    "references_table": "customers",
                    "references_columns": ["customer_id"],
                }
            ],
        },
        {
            "name": "customers",
            "columns": [
                {"name": "customer_id", "type": "TEXT"},
                {"name": "customer_city", "type": "TEXT"},
            ],
            "primary_key": ["customer_id"],
            "foreign_keys": [],
        },
        {
            "name": "products",
            "columns": [
                {"name": "product_id", "type": "TEXT"},
                {"name": "product_category", "type": "TEXT"},
            ],
            "primary_key": ["product_id"],
            "foreign_keys": [],
        },
    ]
}


def test_selects_matching_table_and_foreign_key_neighbour():
    result = plan_schema("Show orders by status", SCHEMA)

    assert result["strategy"] == "keyword_match"
    assert "orders" in result["selected_tables"]
    assert "customers" in result["selected_tables"]
    assert "products" not in result["selected_tables"]


def test_selects_table_from_column_match():
    result = plan_schema("Which customer city is recorded?", SCHEMA)

    assert "customers" in result["selected_tables"]
    assert "products" not in result["selected_tables"]


def test_returns_full_schema_when_no_terms_match():
    result = plan_schema("Explain the revenue trend", SCHEMA)

    assert result["strategy"] == "full_schema_fallback"
    assert result["schema"] == SCHEMA
    assert len(result["selected_tables"]) == 3


@pytest.mark.parametrize("question", ["", "   ", None])
def test_rejects_empty_question(question):
    with pytest.raises(ValueError, match="Question"):
        plan_schema(question, SCHEMA)


@pytest.mark.parametrize("schema", [None, {}, {"tables": "orders"}])
def test_rejects_invalid_schema(schema):
    with pytest.raises(ValueError, match="Schema"):
        plan_schema("Show orders", schema)


def test_rejects_schema_without_tables():
    with pytest.raises(ValueError, match="no tables"):
        plan_schema("Show orders", {"tables": []})


def test_does_not_mutate_input_schema():
    original = {
        "tables": [
            {
                "name": "orders",
                "columns": [{"name": "order_status", "type": "TEXT"}],
                "foreign_keys": [],
            }
        ]
    }
    before = {
        "tables": [
            {
                "name": "orders",
                "columns": [{"name": "order_status", "type": "TEXT"}],
                "foreign_keys": [],
            }
        ]
    }

    plan_schema("Show order status", original)

    assert original == before
