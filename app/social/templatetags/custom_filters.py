from django import template

register = template.Library()

@register.filter
def split(value, arg):
    """
    Splits a string on the given delimiter.
    Returns a list of strings.
    """
    return value.split(arg)