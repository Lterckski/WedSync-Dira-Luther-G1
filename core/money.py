from decimal import Decimal


def format_money(amount, currency):
    """Format an amount with the wedding's currency code: format_money(Decimal("12500"), "PHP") → "PHP 12,500.00"."""
    amount = Decimal(amount or 0)
    sign = "-" if amount < 0 else ""
    return f"{sign}{currency} {abs(amount):,.2f}"
