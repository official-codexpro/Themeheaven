import re
from urllib.parse import urlsplit

EVENT_NAME_PATTERN = re.compile(r'^[a-z0-9][a-z0-9_.-]{0,79}$')
SELECTOR_PATTERN = re.compile(
    r'^(?:a|button|form)?'
    r'(?:(?:#|\.)[A-Za-z][A-Za-z0-9_-]*'
    r'|\[data-[a-z-]+=[\'"]?[A-Za-z0-9_.:-]+[\'"]?\])$'
)


def clean_event_name(value):
    text = ' '.join(str(value or '').split()).lower()
    return text[:80]


def is_safe_event_name(value):
    return bool(EVENT_NAME_PATTERN.match(clean_event_name(value)))


def clean_path(value):
    text = ' '.join(str(value or '').split())
    if not text:
        return ''
    parsed = urlsplit(text)
    path = parsed.path if parsed.scheme in {'http', 'https'} else text
    if not path.startswith('/'):
        return ''
    return path[:500]


def validate_tracking_selector(value):
    selector = ' '.join(str(value or '').split())
    if not selector:
        raise ValueError('Enter a CSS selector.')
    if len(selector) > 200 or not SELECTOR_PATTERN.match(selector):
        raise ValueError('Use a simple #id, .class, or data-attribute selector.')
    return selector
