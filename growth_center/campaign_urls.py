from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .validators import sanitize_text

UTM_KEYS = ('utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content')


def strip_utm_params(value):
    text = sanitize_text(value, 500)
    if not text:
        return ''
    parsed = urlsplit(text)
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
        return text
    query = [(key, item) for key, item in parse_qsl(parsed.query, keep_blank_values=True) if key.lower() not in UTM_KEYS]
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query, doseq=True), parsed.fragment))


def build_campaign_url(destination, source, medium, campaign, term='', content=''):
    destination = strip_utm_params(destination)
    parsed = urlsplit(destination)
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
        return '', 'Enter a full http(s) destination URL.'

    values = {
        'utm_source': sanitize_text(source, 120),
        'utm_medium': sanitize_text(medium, 120),
        'utm_campaign': sanitize_text(campaign, 120),
        'utm_term': sanitize_text(term, 120),
        'utm_content': sanitize_text(content, 120),
    }
    if not values['utm_source']:
        return '', 'UTM Source is required.'
    if not values['utm_medium']:
        return '', 'UTM Medium is required.'
    if not values['utm_campaign']:
        return '', 'UTM Campaign is required.'

    query = [(key, item) for key, item in parse_qsl(parsed.query, keep_blank_values=True) if key.lower() not in UTM_KEYS]
    query.extend((key, value) for key, value in values.items() if value)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query, doseq=True), parsed.fragment)), ''
