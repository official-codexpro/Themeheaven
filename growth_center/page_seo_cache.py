from django.core.cache import cache

from .models import PageSEO

PAGE_SEO_CACHE_PREFIX = 'growth_center:page_seo:'
PAGE_SEO_CACHE_TIMEOUT = 300


def _cache_key(page_key):
    return f'{PAGE_SEO_CACHE_PREFIX}{page_key}'


def get_cached_page_seo(page_key):
    cached = cache.get(_cache_key(page_key))
    if cached == 'missing':
        return None
    if cached:
        return cached
    try:
        instance = PageSEO.objects.get(page_key=page_key)
    except PageSEO.DoesNotExist:
        cache.set(_cache_key(page_key), 'missing', PAGE_SEO_CACHE_TIMEOUT)
        return None
    cache.set(_cache_key(page_key), instance, PAGE_SEO_CACHE_TIMEOUT)
    return instance


def clear_page_seo_cache(page_key):
    cache.delete(_cache_key(page_key))
