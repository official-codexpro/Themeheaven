from django.urls import reverse

from .seo import absolute_url
from .seo_settings import get_seo_settings
from .validators import SAFE_ROBOTS_TXT, sanitize_robots_txt, robots_txt_warnings


def sitemap_absolute_url(instance=None):
    return absolute_url(reverse('sitemap'), instance=instance)


def robots_absolute_url(instance=None):
    return absolute_url(reverse('robots_txt'), instance=instance)


def render_robots_txt(instance=None):
    instance = instance or get_seo_settings()
    if instance.robots_txt_enabled:
        content = sanitize_robots_txt(instance.robots_txt_content) or SAFE_ROBOTS_TXT
    else:
        content = SAFE_ROBOTS_TXT

    if instance.sitemap_enabled:
        sitemap_line = f'Sitemap: {sitemap_absolute_url(instance)}'
        lines = content.splitlines()
        if not any(line.strip().lower().startswith('sitemap:') for line in lines):
            content = f'{content.strip()}\n\n{sitemap_line}'

    return f'{content.strip()}\n'


def robots_configuration_warnings(instance=None):
    instance = instance or get_seo_settings()
    if not instance.robots_txt_enabled:
        return []
    return robots_txt_warnings(instance.robots_txt_content)
