from app.services.hallucination_detector import check_result_sanity


def test_grouped_aggregate_can_return_multiple_rows():
    result = check_result_sanity(
        "Count orders by status",
        """
        SELECT order_status, COUNT(*) AS order_count
        FROM orders
        GROUP BY order_status
        """,
        [
            {"order_status": "delivered", "order_count": 100},
            {"order_status": "shipped", "order_count": 10},
        ],
        ["order_status", "order_count"],
    )

    assert result["passed"] is True
    assert result["warnings"] == []


def test_grouped_sum_can_return_multiple_rows():
    result = check_result_sanity(
        "Sales by category",
        """
        SELECT category, SUM(price) AS total_sales
        FROM products
        GROUP BY category
        """,
        [
            {"category": "books", "total_sales": 100.0},
            {"category": "clothing", "total_sales": 200.0},
        ],
        ["category", "total_sales"],
    )

    assert result["passed"] is True


def test_scalar_aggregate_with_one_row_passes():
    result = check_result_sanity(
        "Count all orders",
        "SELECT COUNT(*) AS order_count FROM orders",
        [{"order_count": 100}],
        ["order_count"],
    )

    assert result["passed"] is True
    assert result["warnings"] == []


def test_scalar_aggregate_with_no_rows_warns():
    result = check_result_sanity(
        "Count orders",
        "SELECT COUNT(*) AS order_count FROM orders WHERE 1 = 0",
        [],
        ["order_count"],
    )

    assert result["passed"] is False
    assert any("no matching rows" in warning for warning in result["warnings"])


def test_non_aggregate_query_is_not_flagged_for_row_count():
    result = check_result_sanity(
        "List order statuses",
        "SELECT order_status FROM orders LIMIT 3",
        [
            {"order_status": "delivered"},
            {"order_status": "shipped"},
        ],
        ["order_status"],
    )

    assert result["passed"] is True


def test_empty_columns_are_reported():
    result = check_result_sanity(
        "Example",
        "SELECT 1",
        [],
        [],
    )

    assert result["passed"] is False
    assert "The query returned no columns." in result["warnings"]
