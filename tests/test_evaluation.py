
from scripts.run_evaluation import results_match, values_match


def test_numeric_values_match_within_tolerance():
    assert values_match(4.0864, 4.08642062404257)


def test_numeric_values_outside_tolerance_do_not_match():
    assert not values_match(4.0864, 4.2)


def test_exact_values_match():
    assert values_match("delivered", "delivered")
    assert values_match(625, 625)


def test_different_text_values_do_not_match():
    assert not values_match("delivered", "canceled")


def test_none_matches_only_none():
    assert values_match(None, None)
    assert not values_match(None, 0)


def test_rows_match_regardless_of_row_order():
    expected = [
        {"status": "canceled", "count": 625},
        {"status": "delivered", "count": 96478},
    ]
    actual = [
        {"status": "delivered", "count": 96478},
        {"status": "canceled", "count": 625},
    ]

    assert results_match(expected, actual)


def test_column_aliases_are_ignored_but_positions_are_preserved():
    expected = [{"purchase_year": "2018", "count": 54011}]
    actual = [{"year": "2018", "count": 54011}]

    assert results_match(expected, actual)


def test_swapped_column_values_do_not_match():
    expected = [{"status": "canceled", "count": 625}]
    actual = [{"status": 625, "count": "canceled"}]

    assert not results_match(expected, actual)


def test_different_row_counts_do_not_match():
    expected = [{"count": 1}, {"count": 2}]
    actual = [{"count": 1}]

    assert not results_match(expected, actual)


def test_duplicate_rows_are_compared_correctly():
    expected = [{"status": "canceled"}, {"status": "canceled"}]
    actual = [{"status": "canceled"}, {"status": "delivered"}]

    assert not results_match(expected, actual)
