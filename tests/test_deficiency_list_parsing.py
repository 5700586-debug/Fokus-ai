import pytest

from services.deficiency_list_ai import parse_line_deterministic


@pytest.mark.parametrize(
    "line, expected",
    [
        ("Cola 2L 10 blok", {"product_name": "Cola 2L", "quantity": 10.0, "unit": "blok"}),
        ("Flesh 1 karobka", {"product_name": "Flesh", "quantity": 1.0, "unit": "karobka"}),
        ("Pomidor 10 kg", {"product_name": "Pomidor", "quantity": 10.0, "unit": "kg"}),
        ("Cola 2 litr 10 blok", {"product_name": "Cola 2 litr", "quantity": 10.0, "unit": "blok"}),
    ],
)
def test_line_is_parsed_with_product_size_kept_in_name(line, expected):
    assert parse_line_deterministic(line) == expected


@pytest.mark.parametrize("line", ["Cola 2L", "Cola 2L 10", "Flesh karobka", "Cola 2L blok"])
def test_missing_quantity_or_unit_is_not_invented(line):
    assert parse_line_deterministic(line) is None
