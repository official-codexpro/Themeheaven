import re
from dataclasses import dataclass
from datetime import datetime

from django.urls import URLPattern, URLResolver, get_resolver

from .seo import is_public_canonical_path, normalize_path


@dataclass(frozen=True)
class ManagedPage:
    key: str
    title: str
    path: str
    source: str
    source_label: str
    default_title: str = ''
    default_description: str = ''
    default_image: str = ''
    changefreq: str = 'monthly'
    priority: str = '0.5'
    suggested_schema_type: str = 'webpage'
    lastmod: datetime | None = None

    @property
    def is_product_page(self):
        return self.source == 'model'


STATIC_PAGES = (
    (
        'home',
        'Home',
        '/',
        '',
        '',
        'daily',
        '1.0',
    ),
    (
        'support',
        'Support',
        '/support/',
        'Support — ThemeHaven',
        'Browse the available themes and templates from the homepage. Support contact details have not been configured for this project yet.',
        'monthly',
        '0.6',
    ),
)

POLICY_PAGES = (
    ('privacy-policy', 'yearly', '0.3'),
    ('terms-conditions', 'yearly', '0.3'),
    ('refund-cancellation-policy', 'yearly', '0.3'),
    ('shipping-delivery-policy', 'yearly', '0.3'),
)


DISCOVERY_EXCLUDED_PATHS = {
    '/robots.txt',
    '/sitemap.xml',
    '/products/wordpress/',
    '/products/excel/',
}

DYNAMIC_ROUTE_SEGMENT = re.compile(r'<[^>]+>')


def _normalized_lookup_path(path):
    return normalize_path(path).rstrip('/') or '/'


def _iter_url_patterns(patterns, prefix=''):
    for pattern in patterns:
        route = f'{prefix}{pattern.pattern}'
        if isinstance(pattern, URLResolver):
            yield from _iter_url_patterns(pattern.url_patterns, route)
        elif isinstance(pattern, URLPattern):
            yield pattern, route


def _title_from_url_pattern(pattern, path):
    name = pattern.name or ''
    words = [word for word in re.split(r'[-_]+', name) if word]
    if not words:
        words = [segment for segment in path.strip('/').split('/') if segment]
    return ' '.join(words).replace('-', ' ').title() or 'Website page'


def discover_url_pages():
    pages = []
    for pattern, route in _iter_url_patterns(get_resolver().url_patterns):
        if DYNAMIC_ROUTE_SEGMENT.search(route):
            continue
        path = normalize_path(route)
        if path in DISCOVERY_EXCLUDED_PATHS or not is_public_canonical_path(path):
            continue
        pages.append(ManagedPage(
            key=f'url:{_normalized_lookup_path(path)}',
            title=_title_from_url_pattern(pattern, path),
            path=path,
            source='route',
            source_label='Discovered page',
            changefreq='monthly',
            priority='0.5',
        ))
    return pages


def discover_pages():
    from core.views import POLICIES
    from products.models import ExcelDashboard, WordPressTheme

    pages = [
        ManagedPage(
            key=key,
            title=title,
            path=path,
            source='static',
            source_label='Website page',
            default_title=default_title,
            default_description=default_description,
            changefreq=changefreq,
            priority=priority,
        )
        for key, title, path, default_title, default_description, changefreq, priority in STATIC_PAGES
    ]

    for slug, changefreq, priority in POLICY_PAGES:
        policy = POLICIES.get(slug)
        if not policy:
            continue
        pages.append(ManagedPage(
            key=f'policy:{slug}',
            title=policy['title'],
            path=f'/{slug}/',
            source='static',
            source_label='Website page',
            default_title=f"{policy['title']} — ThemeHaven",
            default_description=policy.get('intro', ''),
            changefreq=changefreq,
            priority=priority,
        ))

    for model, prefix, label, changefreq, priority in (
        (WordPressTheme, '/products/wordpress/', 'WordPress Theme', 'weekly', '0.7'),
        (ExcelDashboard, '/products/excel/', 'Excel Dashboard', 'weekly', '0.7'),
    ):
        for product in model.objects.filter(is_active=True).order_by('display_order', '-created_at'):
            pages.append(ManagedPage(
                key=f'products.{model.__name__}:{product.pk}',
                title=product.title,
                path=f'{prefix}{product.slug}/',
                source='model',
                source_label=label,
                default_title=f'{product.title} — ThemeHaven',
                default_description=product.short_description,
                default_image=product.thumbnail.url if product.thumbnail else '',
                changefreq=changefreq,
                priority=priority,
                suggested_schema_type='product',
                lastmod=product.updated_at,
            ))

    pages.extend(discover_url_pages())

    unique = {}
    seen_paths = set()
    for page in pages:
        path_key = _normalized_lookup_path(page.path)
        if page.key in unique or path_key in seen_paths:
            continue
        unique[page.key] = page
        seen_paths.add(path_key)
    return list(unique.values())


def get_managed_page(key):
    for page in discover_pages():
        if page.key == key:
            return page
    return None


def get_managed_page_by_path(path):
    target = _normalized_lookup_path(path)
    for page in discover_pages():
        if _normalized_lookup_path(page.path) == target:
            return page
    return None
