import json

from django import template

register = template.Library()


@register.filter
def json_attr(value):
    return json.dumps(value, separators=(',', ':'))
