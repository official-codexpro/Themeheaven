import base64
import hashlib
import hmac
import json
import os
import re
from datetime import timedelta
from urllib.parse import urlparse

from django.conf import settings
from django.db import DatabaseError, IntegrityError, transaction
from django.db.models import F
from django.middleware.csrf import get_token
from django.urls import NoReverseMatch, reverse
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
    '/analytics/',
)

EXCLUDED_PATHS = {
    '/favicon.ico',
    '/robots.txt',
    '/sitemap.xml',
    '/manifest.json',
}

BOT_UA_PATTERN = re.compile(
    r'bot|crawler|spider|slurp|bingpreview|headless|phantomjs|scrapy|wget|curl|python-requests',
    re.IGNORECASE,
)

PAID_MEDIA = {'cpc', 'ppc', 'paid', 'paidsearch', 'paid-search'}
EMAIL_MEDIA = {'email', 'mail', 'newsletter'}
TOKEN_TTL_SECONDS = 60 * 60 * 24


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


def _b64encode(value):
    return base64.urlsafe_b64encode(value).rstrip(b'=').decode('ascii')


def _b64decode(value):
    padding = '=' * (-len(value) % 4)
    return base64.urlsafe_b64decode(f'{value}{padding}'.encode('ascii'))


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


def classify_device(user_agent):
    text = str(user_agent or '').lower()
    if not text:
        return 'Desktop'
    if 'ipad' in text or 'tablet' in text or 'kindle' in text or 'silk' in text:
        return 'Tablet'
    if 'android' in text and 'mobile' not in text:
        return 'Tablet'
    if any(token in text for token in ('iphone', 'ipod', 'mobi', 'android')):
        return 'Mobile'
    return 'Desktop'


def classify_browser(user_agent):
    text = str(user_agent or '').lower()
    if not text:
        return 'Other'
    if 'edg/' in text or 'edge/' in text:
        return 'Edge'
    if 'opr/' in text or 'opera' in text:
        return 'Opera'
    if 'firefox/' in text:
        return 'Firefox'
    if 'chrome/' in text or 'crios/' in text:
        return 'Chrome'
    if 'safari/' in text:
        return 'Safari'
    return 'Other'


def is_bot_request(request):
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    return bool(user_agent and BOT_UA_PATTERN.search(user_agent))


def country_code_from_request(request):
    code = str(request.META.get('HTTP_CF_IPCOUNTRY') or '').strip().upper()
    if len(code) == 2 and code.isalpha() and code != 'XX':
        return code
    return ''


def campaign_values(request):
    return {
        'utm_source': _clean_label(request.GET.get('utm_source')),
        'utm_medium': _clean_label(request.GET.get('utm_medium')),
        'utm_campaign': _clean_label(request.GET.get('utm_campaign')),
        'utm_term': _clean_label(request.GET.get('utm_term')),
        'utm_content': _clean_label(request.GET.get('utm_content')),
    }


def classify_source_details(request):
    values = campaign_values(request)
    source = values['utm_source']
    medium = values['utm_medium'].lower()

    if medium in PAID_MEDIA:
        values.update({'category': 'Paid Search', 'label': source or 'Paid Search', 'referrer_host': ''})
        return values
    if medium in EMAIL_MEDIA or source.lower() in EMAIL_MEDIA:
        values.update({'category': 'Email', 'label': source or medium or 'Email', 'referrer_host': ''})
        return values
    if source or medium:
        values.update({'category': 'Campaign/UTM', 'label': source or medium or 'Campaign', 'referrer_host': ''})
        return values

    referrer = request.META.get('HTTP_REFERER', '')
    if not referrer:
        values.update({'category': 'Direct', 'label': '', 'referrer_host': ''})
        return values

    host = normalize_host(referrer)
    if not host:
        values.update({'category': 'Other', 'label': '', 'referrer_host': ''})
        return values

    try:
        site_host = normalize_host(request.get_host())
    except Exception:
        site_host = ''

    if site_host and (host == site_host or host.endswith(f'.{site_host}')):
        category, label = 'Direct', ''
    elif _host_matches(host, SEARCH_ENGINE_HOSTS):
        category, label = 'Organic Search', host
    elif _host_matches(host, SOCIAL_HOSTS):
        category, label = 'Social', host
    else:
        category, label = 'Referral', host
    values.update({'category': category, 'label': label, 'referrer_host': host})
    return values


def classify_source(request):
    details = classify_source_details(request)
    return details['category'], details['label']


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


def is_trackable_request(request):
    if request.method != 'GET':
        return False
    if is_excluded_path(request.path_info):
        return False
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return False
    if request.headers.get('DNT') == '1':
        return False
    if getattr(request.user, 'is_authenticated', False):
        return False
    if is_bot_request(request):
        return False
    return True


def should_track(request, response):
    if not is_trackable_request(request):
        return False
    if response.status_code != 200:
        return False
    if not response.get('Content-Type', '').startswith('text/html'):
        return False
    return True


def build_tracking_token(request):
    payload = {
        'v': get_visitor_key(request),
        's': get_session_key(request, get_visitor_key(request)),
        'p': request.path_info[:500],
        'iat': int(timezone.now().timestamp()),
    }
    encoded = _b64encode(json.dumps(payload, separators=(',', ':')).encode('utf-8'))
    signature = _b64encode(hmac.new(_salt().encode('utf-8'), encoded.encode('ascii'), hashlib.sha256).digest())
    return f'{encoded}.{signature}'


def decode_tracking_token(token):
    try:
        encoded, signature = str(token or '').split('.', 1)
    except ValueError:
        return None
    expected = _b64encode(hmac.new(_salt().encode('utf-8'), encoded.encode('ascii'), hashlib.sha256).digest())
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        payload = json.loads(_b64decode(encoded).decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return None
    if not all(key in payload for key in ('v', 's', 'p', 'iat')):
        return None
    issued = int(payload['iat'])
    now = int(timezone.now().timestamp())
    if issued > now + 60 or now - issued > TOKEN_TTL_SECONDS:
        return None
    if not str(payload['p']).startswith('/') or len(str(payload['p'])) > 500:
        return None
    return payload


def build_tracking_config(request):
    if not is_trackable_request(request):
        return None
    try:
        endpoint = reverse('analytics_beacon')
    except NoReverseMatch:
        endpoint = '/analytics/beacon/'
    return {
        'enabled': True,
        'endpoint': endpoint,
        'token': build_tracking_token(request),
        'path': request.path_info[:500],
        'csrfToken': get_token(request),
    }


def track_page_view(request, response):
    if not should_track(request, response):
        return None

    now = timezone.now()
    path = request.path_info[:500]
    user_agent = request.META.get('HTTP_USER_AGENT', '')[:200]
    visitor_key = get_visitor_key(request)
    session_key = get_session_key(request, visitor_key)
    source = classify_source_details(request)
    country_code = country_code_from_request(request)

    try:
        with transaction.atomic():
            visitor, visitor_created = Visitor.objects.get_or_create(
                visitor_key=visitor_key,
                defaults={'first_seen': now, 'last_seen': now, 'country_code': country_code},
            )
            if country_code and visitor.country_code != country_code:
                Visitor.objects.filter(pk=visitor.pk).update(country_code=country_code)

            session, session_created = AnalyticsSession.objects.get_or_create(
                session_key=session_key,
                defaults={
                    'visitor': visitor,
                    'started_at': now,
                    'last_seen_at': now,
                    'page_view_count': 0,
                    'is_returning': not visitor_created,
                    'source_category': source['category'],
                    'source_label': source['label'][:120],
                    'referrer_host': source['referrer_host'][:253],
                    'utm_source': source['utm_source'],
                    'utm_medium': source['utm_medium'],
                    'utm_campaign': source['utm_campaign'],
                    'utm_term': source['utm_term'],
                    'utm_content': source['utm_content'],
                    'landing_path': path,
                    'exit_path': path,
                    'device_category': classify_device(user_agent),
                    'browser_category': classify_browser(user_agent),
                    'country_code': country_code,
                },
            )

            last_view = PageView.objects.filter(session=session).order_by('-viewed_at').first()
            if last_view:
                age_seconds = (now - last_view.viewed_at).total_seconds()
                if last_view.path == path and 0 <= age_seconds < 90:
                    return None
                if last_view.duration_seconds is None and age_seconds > 0:
                    PageView.objects.filter(pk=last_view.pk).update(
                        duration_seconds=min(int(age_seconds), 86400),
                    )

            from_path = ''
            if last_view and 0 <= (now - last_view.viewed_at).total_seconds() <= 1800:
                from_path = last_view.path

            PageView.objects.create(
                session=session,
                visitor=visitor,
                path=path,
                title=page_title_for_path(path)[:220],
                from_path=from_path[:500],
                viewed_at=now,
            )
            AnalyticsSession.objects.filter(pk=session.pk).update(
                page_view_count=F('page_view_count') + 1,
                last_seen_at=now,
                exit_path=path,
            )
            Visitor.objects.filter(pk=visitor.pk).update(last_seen=now)
            return session
    except (DatabaseError, IntegrityError):
        return None
