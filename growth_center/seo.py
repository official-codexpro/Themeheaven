from urllib.parse import urlparse

from django.conf import settings

from core.system_settings import get_system_settings

from .seo_settings import get_seo_settings
from .validators import is_valid_google_token, sanitize_google_token, sanitize_text

SAFE_TITLE = 'ThemeHaven — Premium Digital Products'
SAFE_DESCRIPTION = 'Discover premium WordPress themes and professional Excel dashboards at ThemeHaven.'


def normalize_domain(value):
    text = str(value or '').strip()
    if not text:
        return ''
    parsed = urlparse(text if '://' in text else f'//{text}')
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        return ''
    if parsed.path not in ('', '/'):
        return ''
    host = (parsed.hostname or '').lower().strip('.')
    if not host or any(character.isspace() for character in host):
        return ''
    return host


def apply_www_preference(host, preference):
    host = (host or '').lower()
    if preference == 'with' and host and not host.startswith('www.'):
        return f'www.{host}'
    if preference == 'without' and host.startswith('www.'):
        return host[4:]
    return host


def fallback_host():
    site_settings = get_system_settings()
    host = normalize_domain(site_settings.site_base_url)
    if host:
        return host
    for candidate in settings.ALLOWED_HOSTS:
        if candidate not in {'*', '.localhost', 'localhost', '127.0.0.1', '[::1]'}:
            return candidate
    return 'localhost'


def site_origin(instance=None, request=None):
    instance = instance or get_seo_settings()
    if instance.primary_domain:
        host = normalize_domain(instance.primary_domain)
    elif request is not None:
        host = request.get_host()
    else:
        host = fallback_host()
    host = apply_www_preference(host, instance.preferred_www)
    secure = instance.prefer_https or bool(request and request.is_secure())
    return f"{'https' if secure else 'http'}://{host}"


def normalize_path(path, behavior='preserve'):
    text = str(path or '/').split('?', 1)[0].split('#', 1)[0]
    if not text.startswith('/'):
        text = f'/{text}'
    if text == '/':
        return '/'
    if behavior == 'force_slash' and not text.endswith('/'):
        return f'{text}/'
    if behavior == 'strip_slash' and text.endswith('/'):
        return text.rstrip('/')
    return text


def is_public_canonical_path(path):
    text = str(path or '').lower()
    excluded = (
        '/admin/',
        '/api/',
        '/static/',
        '/media/',
        '/private-media/',
        '/__debug__/',
        '/products/preview/',
        '/products/download/',
        '/analytics/',
    )
    if text in {'/robots.txt', '/sitemap.xml', '/favicon.ico'}:
        return False
    return not text.startswith(excluded)


def build_canonical_url(request, path=None, instance=None):
    instance = instance or get_seo_settings()
    target_path = normalize_path(path if path is not None else getattr(request, 'path_info', '/'))
    if not is_public_canonical_path(target_path):
        return ''
    target_path = normalize_path(target_path, instance.trailing_slash_behavior)
    return f'{site_origin(instance, request)}{target_path}'


def absolute_url(path, request=None, instance=None):
    text = str(path or '')
    if not text:
        return ''
    if text.startswith(('http://', 'https://')):
        return text
    if not text.startswith('/'):
        text = f'/{text}'
    return f'{site_origin(instance, request)}{text}'


def robots_directive(instance=None, override=None):
    instance = instance or get_seo_settings()
    index = instance.index_enabled if not override or 'index' not in override else override['index']
    follow = instance.follow_enabled if not override or 'follow' not in override else override['follow']
    parts = ['index' if index else 'noindex', 'follow' if follow else 'nofollow']
    return ', '.join(parts)


def sanitized_verification_token(instance=None):
    instance = instance or get_seo_settings()
    token = sanitize_google_token(instance.google_verification_token)
    return token if is_valid_google_token(token) else ''


def build_seo_context(request):
    instance = get_seo_settings()
    title = sanitize_text(instance.seo_title, 120)
    description = sanitize_text(instance.meta_description, 320)
    site_name = sanitize_text(instance.site_name, 120) or 'ThemeHaven'
    token = sanitized_verification_token(instance)
    image = absolute_url(instance.default_image.url, request, instance) if instance.default_image else ''

    context = {
        'title': title,
        'description': description,
        'keywords': sanitize_text(instance.meta_keywords, 500),
        'site_name': site_name,
        'image': image,
        'canonical_url': build_canonical_url(request, instance=instance),
        'robots': robots_directive(instance=instance),
        'google_verification_token': token,
        'index_enabled': instance.index_enabled,
    }

    from .page_seo import build_page_seo_context

    context.update(build_page_seo_context(request, context, instance))
    return context
