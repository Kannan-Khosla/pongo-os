from decimal import Decimal


def _decimal(value) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def calculate_sellable(in_stock, allocated) -> Decimal:
    return _decimal(in_stock) - _decimal(allocated)


def calculate_under_par(in_stock, par_level) -> bool:
    if par_level is None:
        return False
    return _decimal(in_stock) <= _decimal(par_level)


def calculate_storage_volume(length, width, height) -> Decimal:
    return _decimal(length) * _decimal(width) * _decimal(height)


def calculate_inventory_value(in_stock, unit_cost) -> Decimal:
    return _decimal(in_stock) * _decimal(unit_cost)
