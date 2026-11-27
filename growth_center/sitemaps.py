from django.contrib.sitemaps import Sitemap

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

        entries = [
            {'path': path, 'changefreq': changefreq, 'priority': priority}
            for path, changefreq, priority in STATIC_PUBLIC_PATHS
        ]

        from products.models import ExcelDashboard, WordPressTheme

        for model, prefix in (
            (WordPressTheme, '/products/wordpress/'),
            (ExcelDashboard, '/products/excel/'),
        ):
            for slug, updated_at in model.objects.filter(is_active=True).values_list('slug', 'updated_at'):
                entries.append({
                    'path': f'{prefix}{slug}/',
                    'lastmod': updated_at,
                    'changefreq': 'weekly',
                    'priority': '0.7',
                })

        unique = {}
        for entry in entries:
            unique.setdefault(entry['path'], entry)
        return [entry for entry in unique.values() if is_path_indexable(entry['path'], instance)]

    def location(self, item):
        instance = get_seo_settings()
        origin = site_origin(instance=instance)
        return f'{origin}{normalize_path(item["path"], instance.trailing_slash_behavior)}'

    def lastmod(self, item):
        return item.get('lastmod')

    def changefreq(self, item):
        return item.get('changefreq', 'weekly')

    def priority(self, item):
        return item.get('priority', '0.5')
