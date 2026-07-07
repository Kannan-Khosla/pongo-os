from decimal import Decimal

from app.services.calculations import (
    calculate_inventory_value,
    calculate_sellable,
    calculate_storage_volume,
    calculate_under_par,
)


def test_calculate_sellable():
    assert calculate_sellable(10, 3) == Decimal("7")


def test_calculate_under_par():
    assert calculate_under_par(4, 5) is True
    assert calculate_under_par(6, 5) is False
    assert calculate_under_par(6, None) is False


def test_calculate_storage_volume():
    assert calculate_storage_volume(2, 3, 4) == Decimal("24")


def test_calculate_inventory_value():
    assert calculate_inventory_value(5, "2.50") == Decimal("12.50")
