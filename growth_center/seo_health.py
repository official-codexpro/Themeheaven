from django.urls import NoReverseMatch, reverse

from .robots import robots_configuration_warnings
from .seo import normalize_domain, robots_directive, sanitized_verification_token
from .seo_settings import get_seo_settings
from .sitemaps import PublicSitemap
from .validators import sanitize_text


def _check(label, status, detail):
    return {'label': label, 'status': status, 'detail': detail}


def seo_health_summary(instance=None):
    instance = instance or get_seo_settings()
    title = sanitize_text(instance.seo_title, 120)
    description = sanitize_text(instance.meta_description, 320)
    token = sanitized_verification_token(instance)
    checks = []

    if not title:
        checks.append(_check('SEO title configured', 'missing', 'No global title is configured.'))
    elif 30 <= len(title) <= 60:
        checks.append(_check('SEO title configured', 'configured', f'{len(title)} characters.'))
    else:
        checks.append(_check('SEO title configured', 'warning', f'{len(title)} characters; recommended 30–60.'))

    if not description:
        checks.append(_check('Meta description configured', 'missing', 'No global description is configured.'))
    elif 120 <= len(description) <= 160:
        checks.append(_check('Meta description configured', 'configured', f'{len(description)} characters.'))
    else:
        checks.append(_check('Meta description configured', 'warning', f'{len(description)} characters; recommended 120–160.'))

    checks.append(_check(
        'Default social image configured',
        'configured' if instance.default_image else 'missing',
        'Fallback share image is available.' if instance.default_image else 'No default Open Graph image uploaded.',
    ))

    if not instance.sitemap_enabled:
        checks.append(_check('Sitemap enabled and accessible', 'disabled', 'Sitemap functionality is disabled.'))
    else:
        try:
            reverse('sitemap')
            count = len(PublicSitemap().items())
            status = 'configured' if count else 'warning'
            detail = f'{count} public URL(s) available.' if count else 'Sitemap is enabled but currently empty.'
        except (NoReverseMatch, Exception):
            status = 'warning'
            detail = 'Sitemap endpoint could not be resolved.'
        checks.append(_check('Sitemap enabled and accessible', status, detail))

    if not instance.robots_txt_enabled:
        checks.append(_check('Robots.txt configured', 'disabled', 'Safe default rules are being served.'))
    else:
        warnings = robots_configuration_warnings(instance)
        if not instance.robots_txt_content.strip():
            checks.append(_check('Robots.txt configured', 'missing', 'No custom rules saved; safe defaults apply.'))
        elif warnings:
            checks.append(_check('Robots.txt configured', 'warning', ' '.join(warnings)))
        else:
            checks.append(_check('Robots.txt configured', 'configured', 'Custom rules are active and safe.'))

    checks.append(_check(
        'Search Console verification configured',
        'configured' if token else 'missing',
        'HTML verification tag is active.' if token else 'No verification token saved.',
    ))

    if instance.primary_domain and normalize_domain(instance.primary_domain) != instance.primary_domain:
        checks.append(_check('Canonical URL configuration valid', 'warning', 'Primary domain should be normalized.'))
    elif instance.primary_domain:
        checks.append(_check('Canonical URL configuration valid', 'configured', instance.primary_domain))
    else:
        checks.append(_check('Canonical URL configuration valid', 'warning', 'Using the request domain automatically.'))

    if instance.index_enabled:
        checks.append(_check('Search engine indexing enabled', 'configured', robots_directive(instance=instance)))
    else:
        checks.append(_check('Search engine indexing enabled', 'disabled', 'Global noindex is active.'))

    configured = sum(1 for check in checks if check['status'] == 'configured')
    return {
        'checks': checks,
        'configured_count': configured,
        'total_count': len(checks),
        'readiness_percent': round((configured / len(checks)) * 100) if checks else 0,
        'readiness_label': f'{configured} of {len(checks)} configuration checks are complete; this is not a ranking score.',
    }
