import hashlib
import os
from datetime import timedelta
from urllib.parse import urlparse

from django.conf import settings
from django.db import DatabaseError, IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from .models import AnalyticsSession, PageView, Visitor

SEARCH_ENGINE_HOSTS = (
    'google.com',
    'bing.com',
    'yahoo.com',
    'duckduckgo.com',
    'brave.com',
    'ecosia.org',
    'search.yahoo.com',
)

SOCIAL_HOSTS = (
    'facebook.com',
    'instagram.com',
    'twitter.com',
    'x.com',
    'linkedin.com',
    'youtube.com',
    'tiktok.com',
    'pinterest.com',
    'reddit.com',
)

EXCLUDED_PREFIXES = (
    '/admin/',
    '/static/',
    '/media/',
    '/private-media/',
    '/__debug__/',
    '/.well-known/',
    '/products/preview/',
    '/products/download/',
    '/api/',
)

EXCLUDED_PATHS = {
    '/favicon.ico',
    '/robots.txt',
    '/sitemap.xml',
    '/manifest.json',
}


def _salt():
    return os.environ.get(
        'DJANGO_GROWTH_ANALYTICS_SALT',
        f'{settings.SECRET_KEY}|growth-center-analytics',
    )


def _digest(value):
    return hashlib.sha256(f'{_salt()}|{value}'.encode('utf-8')).hexdigest()


def _clean_label(value, max_length=120):
    label = ' '.join(str(value or '').split())
    return label[:max_length]


def _host_matches(host, candidates):
    return any(host == candidate or host.endswith(f'.{candidate}') for candidate in candidates)


def get_visitor_key(request):
    ip_address = request.META.get('REMOTE_ADDR') or 'unknown'
    user_agent = request.META.get('HTTP_USER_AGENT', '')[:200]
    return _digest(f'visitor|{ip_address}|{user_agent}')


def get_session_key(request, visitor_key):
    user_agent = request.META.get('HTTP_USER_AGENT', '')[:200]
    day = timezone.localdate().isoformat()
    return _digest(f'session|{visitor_key}|{user_agent}|{day}')


def normalize_host(value):
    if not value:
        return ''
    parsed = urlparse(value if '://' in value else f'https://{value}')
    host = (parsed.hostname or '').lower().strip('.')
    if host.startswith('www.'):
        host = host[4:]
    return host


def classify_source(request):
    utm_source = _clean_label(request.GET.get('utm_source'))
    utm_medium = _clean_label(request.GET.get('utm_medium'))
    if utm_source or utm_medium:
        return 'Campaign/UTM', utm_source or utm_medium or 'Campaign'

    referrer = request.META.get('HTTP_REFERER', '')
    if not referrer:
        return 'Direct', ''

    host = normalize_host(referrer)
    if not host:
        return 'Other', ''

    try:
        site_host = normalize_host(request.get_host())
    except Exception:
        site_host = ''

    if site_host and (host == site_host or host.endswith(f'.{site_host}')):
        return 'Direct', ''
    if _host_matches(host, SEARCH_ENGINE_HOSTS):
        return 'Organic Search', host
    if _host_matches(host, SOCIAL_HOSTS):
        return 'Social', host
    return 'Referral', host


def page_title_for_path(path):
    titles = {
        '/': 'Home',
        '/support/': 'Support',
        '/privacy-policy/': 'Privacy Policy',
        '/terms-conditions/': 'Terms & Conditions',
        '/refund-cancellation-policy/': 'Refund & Cancellation Policy',
        '/shipping-delivery-policy/': 'Shipping & Delivery Policy',
        '/products/wordpress/': 'WordPress Themes',
        '/products/excel/': 'Excel Templates',
    }
    if path in titles:
        return titles[path]
    parts = [part for part in path.split('/') if part]
    if len(parts) >= 2 and parts[0] == 'products':
        return f'{parts[1].title()} · {parts[-1].replace("-", " ").title()}'
    if parts:
        return parts[-1].replace('-', ' ').title()
    return 'Home'


def is_excluded_path(path):
    return path in EXCLUDED_PATHS or path.startswith(EXCLUDED_PREFIXES)


def should_track(request, response):
    if request.method != 'GET':
        return False
    if response.status_code != 200:
        return False
    if not response.get('Content-Type', '').startswith('text/html'):
        return False
    if is_excluded_path(request.path_info):
        return False
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return False
    if request.headers.get('DNT') == '1':
        return False
    if getattr(request.user, 'is_authenticated', False):
        return False
    return True


def track_page_view(request, response):
    if not should_track(request, response):
        return None

    now = timezone.now()
    path = request.path_info[:500]
    visitor_key = get_visitor_key(request)
    session_key = get_session_key(request, visitor_key)
    source_category, source_label = classify_source(request)

    try:
        with transaction.atomic():
            visitor, visitor_created = Visitor.objects.get_or_create(
                visitor_key=visitor_key,
                defaults={'first_seen': now, 'last_seen': now},
            )
            session, session_created = AnalyticsSession.objects.get_or_create(
                session_key=session_key,
                defaults={
                    'visitor': visitor,
                    'started_at': now,
                    'last_seen_at': now,
                    'page_view_count': 0,
                    'is_returning': not visitor_created,
                    'source_category': source_category,
                    'source_label': source_label[:120],
                    'landing_path': path,
                },
            )

            recent_duplicate = PageView.objects.filter(
                session=session,
                path=path,
                viewed_at__gte=now - timedelta(seconds=90),
            ).exists()
            if recent_duplicate:
                return None

            PageView.objects.create(session=session, visitor=visitor, path=path, viewed_at=now)
            AnalyticsSession.objects.filter(pk=session.pk).update(
                page_view_count=F('page_view_count') + 1,
                last_seen_at=now,
            )
            Visitor.objects.filter(pk=visitor.pk).update(last_seen=now)
            return session
    except (DatabaseError, IntegrityError):
        return None
