from django import template

from core.money import format_money

register = template.Library()


@register.filter
def money(amount, currency):
    """{{ category.allocated_amount|money:wedding.base_currency }} → PHP 12,500.00"""
    return format_money(amount, currency)
