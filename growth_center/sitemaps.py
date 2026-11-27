from django.contrib.sitemaps import Sitemap

from .page_registry import discover_pages
from .page_seo import effective_canonical, get_page_instance, is_page_indexable
from .seo import normalize_path, site_origin
from .seo_settings import get_seo_settings

STATIC_PUBLIC_PATHS = (
    ('/', 'daily', '1.0'),
    ('/support/', 'monthly', '0.6'),
    ('/privacy-policy/', 'yearly', '0.3'),
    ('/terms-conditions/', 'yearly', '0.3'),
    ('/refund-cancellation-policy/', 'yearly', '0.3'),
    ('/shipping-delivery-policy/', 'yearly', '0.3'),
)

PAGE_INDEXABILITY_OVERRIDES = {}


def is_path_indexable(path, instance=None):
    instance = instance or get_seo_settings()
    if not instance.index_enabled:
        return False
    return bool(PAGE_INDEXABILITY_OVERRIDES.get(path, True))


class PublicSitemap(Sitemap):
    def items(self):
        instance = get_seo_settings()
        if not instance.sitemap_enabled:
            return []

        entries = []
        seen_locations = set()
        for page in discover_pages():
            if not is_page_indexable(page, instance):
                continue
            if not is_path_indexable(page.path, instance):
                continue
            canonical = effective_canonical(page, None, get_page_instance(page.key), instance)
            if not canonical or canonical in seen_locations:
                continue
            seen_locations.add(canonical)
            entries.append({
                'path': page.path,
                'location': canonical,
                'lastmod': page.lastmod,
                'changefreq': page.changefreq,
                'priority': page.priority,
            })
        return entries

    def location(self, item):
        if item.get('location'):
            return item['location']
        instance = get_seo_settings()
        origin = site_origin(instance=instance)
        return f'{origin}{normalize_path(item["path"], instance.trailing_slash_behavior)}'

    def lastmod(self, item):
        return item.get('lastmod')

    def changefreq(self, item):
        return item.get('changefreq', 'weekly')

    def priority(self, item):
        return item.get('priority', '0.5')
