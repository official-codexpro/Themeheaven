import json
from urllib.parse import urlparse

from .models import PageSEO
from .page_registry import get_managed_page_by_path
from .page_seo_cache import get_cached_page_seo
from .seo import (
    SAFE_DESCRIPTION,
    SAFE_TITLE,
    absolute_url,
    build_canonical_url,
    robots_directive,
    site_origin,
)
from .seo_settings import get_seo_settings
from .validators import (
    is_valid_canonical_url,
    sanitize_jsonld,
    sanitize_text,
)

MIN_TITLE_LENGTH = 30
MAX_TITLE_LENGTH = 60
MIN_DESCRIPTION_LENGTH = 120
MAX_DESCRIPTION_LENGTH = 320


def get_page_instance(page_key):
    return get_cached_page_seo(page_key)


def robots_override(instance):
    override = {}
    if instance and instance.index_mode == 'index':
        override['index'] = True
    elif instance and instance.index_mode == 'noindex':
        override['index'] = False
    if instance and instance.follow_mode == 'follow':
        override['follow'] = True
    elif instance and instance.follow_mode == 'nofollow':
        override['follow'] = False
    return override


def effective_canonical(page, request, instance, global_instance):
    if instance and instance.canonical_override and is_valid_canonical_url(instance.canonical_override):
        return instance.canonical_override.strip()
    return build_canonical_url(request, page.path, global_instance)


def effective_index_enabled(instance, global_instance):
    override = robots_override(instance)
    return bool(override.get('index', global_instance.index_enabled))


def _first_custom(value, max_length):
    return sanitize_text(value, max_length)


def _schema_payload(page, canonical_url, image_url, instance, resolved_title):
    schema_type = instance.schema_type if instance else 'webpage'
    if not page.is_product_page and schema_type == 'product':
        schema_type = 'webpage'
    payload = {
        '@context': 'https://schema.org',
        '@type': 'Product' if schema_type == 'product' else 'WebPage',
        '@id': canonical_url,
        'name': resolved_title,
        'url': canonical_url,
    }
    if image_url and schema_type == 'product':
        payload['image'] = image_url
    return payload


def build_page_seo_context(request, base_context, global_instance=None, page=None):
    if page is None:
        if request is None:
            return {}
        page = get_managed_page_by_path(request.path_info)
    if not page:
        return {}

    global_instance = global_instance or get_seo_settings()
    instance = get_page_instance(page.key)

    custom_title = _first_custom(instance.seo_title if instance else '', 120)
    custom_description = _first_custom(instance.meta_description if instance else '', 320)

    if custom_title:
        title, title_source = custom_title, 'custom'
    elif page.default_title:
        title, title_source = page.default_title, 'page'
    elif base_context.get('title'):
        title, title_source = base_context['title'], 'global'
    else:
        title, title_source = SAFE_TITLE, 'safe'

    if custom_description:
        description, description_source = custom_description, 'custom'
    elif page.default_description:
        description, description_source = page.default_description, 'page'
    elif base_context.get('description'):
        description, description_source = base_context['description'], 'global'
    else:
        description, description_source = SAFE_DESCRIPTION, 'safe'

    canonical = effective_canonical(page, request, instance, global_instance)
    robots = robots_directive(instance=global_instance, override=robots_override(instance))

    page_image = absolute_url(page.default_image, request, global_instance) if page.default_image else ''
    custom_image = absolute_url(instance.og_image.url, request, global_instance) if instance and instance.og_image else ''
    if custom_image:
        og_image, image_source = custom_image, 'custom'
    elif page_image:
        og_image, image_source = page_image, 'page'
    elif base_context.get('image'):
        og_image, image_source = base_context['image'], 'global'
    else:
        og_image, image_source = '', 'missing'

    og_title = (
        _first_custom(instance.og_title if instance else '', 120)
        or custom_title
        or title
    )
    og_description = (
        _first_custom(instance.og_description if instance else '', 320)
        or custom_description
        or description
    )
    og_image_alt = (
        _first_custom(instance.og_image_alt if instance else '', 160)
        or title
    )

    schema_json = ''
    if instance and instance.schema_mode == 'custom':
        schema_json = sanitize_jsonld(instance.schema_json)
    elif instance and instance.schema_mode == 'generated':
        payload = _schema_payload(page, canonical, og_image, instance, title)
        schema_json = sanitize_jsonld(json.dumps(payload, ensure_ascii=False))

    return {
        'page_key': page.key,
        'page_title': page.title,
        'title': title,
        'description': description,
        'keywords': base_context.get('keywords', ''),
        'site_name': base_context.get('site_name', 'ThemeHaven'),
        'canonical_url': canonical,
        'robots': robots,
        'google_verification_token': base_context.get('google_verification_token', ''),
        'index_enabled': 'noindex' not in robots,
        'image': og_image,
        'og_title': og_title,
        'og_description': og_description,
        'og_image': og_image,
        'og_image_alt': og_image_alt,
        'og_url': canonical,
        'schema_json': schema_json,
        'title_source': title_source,
        'description_source': description_source,
        'image_source': image_source,
        'canonical_source': 'custom' if instance and instance.canonical_override else 'auto',
        'index_source': instance.index_mode if instance else 'inherit',
        'follow_source': instance.follow_mode if instance else 'inherit',
    }


def _check(label, status, detail):
    return {'label': label, 'status': status, 'detail': detail}


def page_seo_status(page, global_instance=None):
    global_instance = global_instance or get_seo_settings()
    instance = get_page_instance(page.key)

    canonical = effective_canonical(page, None, instance, global_instance)
    robots = robots_directive(instance=global_instance, override=robots_override(instance))
    title = (
        _first_custom(instance.seo_title if instance else '', 120)
        or page.default_title
        or global_instance.seo_title
        or SAFE_TITLE
    )
    description = (
        _first_custom(instance.meta_description if instance else '', 320)
        or page.default_description
        or global_instance.meta_description
        or SAFE_DESCRIPTION
    )
    image = bool(
        (instance and instance.og_image)
        or page.default_image
        or global_instance.default_image
    )

    title_status = 'custom' if instance and instance.seo_title else 'inherited'
    if not title:
        title_status = 'missing'
    description_status = 'custom' if instance and instance.meta_description else 'inherited'
    if not description:
        description_status = 'missing'
    image_status = 'custom' if instance and instance.og_image else 'inherited'
    if not image:
        image_status = 'missing'

    if instance and instance.index_mode == 'noindex':
        index_status = 'noindex'
    elif instance and instance.index_mode == 'index':
        index_status = 'good'
    elif global_instance.index_enabled:
        index_status = 'inherited'
    else:
        index_status = 'noindex'

    schema_status = instance.schema_mode if instance else 'inherit'
    if instance and instance.schema_mode == 'custom' and not sanitize_jsonld(instance.schema_json):
        schema_status = 'warning'

    checks = [
        _check('SEO title', title_status, 'Custom page title' if title_status == 'custom' else 'Resolved from inherited or page metadata'),
        _check('Meta description', description_status, 'Custom description' if description_status == 'custom' else 'Resolved from inherited or page metadata'),
        _check('Title length', 'good' if MIN_TITLE_LENGTH <= len(title) <= MAX_TITLE_LENGTH else 'warning', f'{len(title)} characters'),
        _check('Description length', 'good' if MIN_DESCRIPTION_LENGTH <= len(description) <= MAX_DESCRIPTION_LENGTH else 'warning', f'{len(description)} characters'),
        _check('Social image', image_status, 'Custom page image' if image_status == 'custom' else 'Resolved from page or global default'),
        _check('Canonical URL', 'good' if is_valid_canonical_url(canonical) else 'warning', 'Custom override' if instance and instance.canonical_override else 'Generated automatically'),
        _check('Indexing', index_status, robots),
        _check('Structured data', schema_status, 'Page-level schema configuration'),
    ]
    positive = {'good', 'custom', 'inherited'}
    good_count = sum(1 for check in checks if check['status'] in positive)
    completeness = round(good_count / len(checks) * 100)

    return {
        'page': page,
        'instance': instance,
        'configured': bool(instance and instance.is_configured),
        'title_status': title_status,
        'description_status': description_status,
        'image_status': image_status,
        'canonical_status': 'custom' if instance and instance.canonical_override else 'auto',
        'index_status': index_status,
        'schema_status': schema_status,
        'robots': robots,
        'canonical_url': canonical,
        'checks': checks,
        'completeness': completeness,
    }


def page_matches_filter(status, filter_key):
    if filter_key == 'all':
        return True
    if filter_key == 'configured':
        return status['configured']
    if filter_key == 'missing':
        return not status['configured']
    if filter_key == 'indexed':
        return status['index_status'] != 'noindex'
    if filter_key == 'noindex':
        return status['index_status'] == 'noindex'
    if filter_key == 'missing_description':
        return not status['instance'] or not status['instance'].meta_description
    if filter_key == 'missing_image':
        return not status['instance'] or not status['instance'].og_image
    return True


def is_page_indexable(page, global_instance=None):
    global_instance = global_instance or get_seo_settings()
    if not global_instance.index_enabled:
        return False
    return effective_index_enabled(get_page_instance(page.key), global_instance)


def canonical_host(canonical):
    try:
        return urlparse(canonical).netloc
    except (TypeError, ValueError):
        return site_origin()


__all__ = [
    'MAX_DESCRIPTION_LENGTH',
    'MAX_TITLE_LENGTH',
    'MIN_DESCRIPTION_LENGTH',
    'MIN_TITLE_LENGTH',
    'build_page_seo_context',
    'canonical_host',
    'get_page_instance',
    'is_page_indexable',
    'page_matches_filter',
    'page_seo_status',
    'robots_override',
]
