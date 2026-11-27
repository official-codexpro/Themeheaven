import logging
import platform
import time

import django
from django.conf import settings
from django.utils import timezone, translation

from .models import SystemSettings

logger = logging.getLogger('core.system_settings')

_cache = {'instance': None, 'expires': 0.0}


def clear_system_settings_cache():
    _cache['instance'] = None
    _cache['expires'] = 0.0


def get_system_settings():
    now = time.monotonic()
    instance = _cache['instance']
    if instance is not None and now < _cache['expires']:
        return instance

    instance, _created = SystemSettings.objects.get_or_create(pk=1)
    _cache['instance'] = instance
    _cache['expires'] = now + max(1, instance.cache_timeout)
    return instance


def get_page_size():
    instance = get_system_settings()
    return min(max(1, instance.page_size), max(1, instance.max_page_size))


def activate_locale():
    instance = get_system_settings()
    try:
        translation.activate(instance.language_code)
    except Exception:
        translation.activate(settings.LANGUAGE_CODE)
    try:
        timezone.activate(instance.time_zone)
    except Exception:
        timezone.activate(settings.TIME_ZONE)
    return instance


def log_settings_change(request, category, changes):
    username = getattr(getattr(request, 'user', None), 'username', 'unknown')
    logger.info('System settings updated by %s in %s: %s', username, category, ', '.join(changes))
    try:
        from .models import SystemSettingsChange

        SystemSettingsChange.objects.create(
            user=request.user if getattr(request.user, 'is_authenticated', False) else None,
            category=category,
            changes='\n'.join(changes),
        )
    except Exception:
        logger.exception('Could not write system settings audit entry.')


def _backend_name(path_or_backend):
    return str(path_or_backend).rsplit('.', 1)[-1]


def system_information(instance):
    return [
        ('Django version', django.get_version(), 'Runtime version.'),
        ('Python version', platform.python_version(), 'Runtime version.'),
        ('Application version', instance.app_version or 'Not set', 'Managed in General Configuration.'),
        ('Environment', instance.get_environment_display(), 'Managed in General Configuration.'),
        ('DEBUG status', 'Enabled' if settings.DEBUG else 'Disabled', 'Environment-controlled; not editable here.'),
        ('Database engine', _backend_name(settings.DATABASES['default']['ENGINE']), 'No connection details are shown.'),
        ('Cache backend', _backend_name(settings.CACHES['default']['BACKEND']), 'Default Django cache.'),
        ('Current time zone', timezone.get_current_timezone_name(), 'Admin rendering uses the configured time zone.'),
        ('Installed apps', f"{len(settings.INSTALLED_APPS)} configured", 'Core and Products are enabled.'),
    ]


def email_information(instance=None):
    return [
        ('Email backend', _backend_name(settings.EMAIL_BACKEND), 'Managed through environment configuration.'),
        ('Email host', 'Configured' if settings.EMAIL_HOST else 'Not configured', 'Host name is hidden.'),
        ('Default sender', settings.DEFAULT_FROM_EMAIL or 'Not configured', 'Read-only.'),
        ('TLS / SSL', f"TLS {'on' if settings.EMAIL_USE_TLS else 'off'} / SSL {'on' if settings.EMAIL_USE_SSL else 'off'}", 'Read-only.'),
        ('Configuration source', 'Environment / settings.py', 'Credentials are never displayed or editable here.'),
    ]


def storage_information(instance=None):
    return [
        ('Storage backend', 'Local filesystem', 'Django default storage is in use.'),
        ('Media storage', 'Configured' if settings.MEDIA_URL else 'Not configured', 'Uploaded images use this storage.'),
        ('Static files', 'Configured' if settings.STATIC_URL else 'Not configured', 'Served by the configured static backend.'),
        ('Maximum upload size', f'{settings.FILE_UPLOAD_MAX_MEMORY_SIZE / (1024 * 1024):.1f} MB', 'Per-file memory limit.'),
        ('Maximum request size', f'{settings.DATA_UPLOAD_MAX_MEMORY_SIZE / (1024 * 1024):.1f} MB', 'Total request data limit.'),
        ('Cloud storage', 'Not configured', 'No cloud storage backend is installed.'),
    ]


def security_information(instance):
    def status(value):
        return 'Enabled' if value else 'Disabled'

    return [
        ('Environment label', instance.get_environment_display(), 'Managed in General Configuration.'),
        ('HTTPS redirect (live)', status(settings.SECURE_SSL_REDIRECT), 'Environment-controlled until restart.'),
        ('HTTPS redirect (saved)', status(instance.secure_ssl_redirect), 'Applies after a server restart.'),
        ('Secure session cookie (live)', status(settings.SESSION_COOKIE_SECURE), 'Environment-controlled until restart.'),
        ('Secure session cookie (saved)', status(instance.session_cookie_secure), 'Applies after a server restart.'),
        ('Secure CSRF cookie (live)', status(settings.CSRF_COOKIE_SECURE), 'Environment-controlled until restart.'),
        ('Secure CSRF cookie (saved)', status(instance.csrf_cookie_secure), 'Applies after a server restart.'),
        ('HSTS (live)', status(settings.SECURE_HSTS_SECONDS > 0), f'{settings.SECURE_HSTS_SECONDS} seconds.'),
        ('HSTS (saved)', status(instance.hsts_enabled), f'{instance.hsts_seconds} seconds; applies after a restart.'),
        ('DEBUG (live)', status(settings.DEBUG), 'Environment-controlled; not editable here.'),
    ]


def session_information(instance):
    return [
        ('Session backend', _backend_name(settings.SESSION_ENGINE), 'Environment-controlled.'),
        ('Secure session cookie', 'Yes' if settings.SESSION_COOKIE_SECURE else 'No', 'Stored value requires a restart.'),
        ('HTTP-only session cookie', 'Yes' if settings.SESSION_COOKIE_HTTPONLY else 'No', 'Environment-controlled.'),
        ('Live session age', f'{settings.SESSION_COOKIE_AGE} seconds', 'Stored value requires a restart.'),
        ('Expire at browser close', 'Yes' if instance.session_expire_at_browser_close else 'No', 'Stored value requires a restart.'),
        ('Password validation', f'{len(settings.AUTH_PASSWORD_VALIDATORS)} rules enabled', 'Managed in settings.py.'),
    ]


def cache_information(instance=None):
    from products.catalogue import PAGE_SIZE

    return [
        ('Cache backend', _backend_name(settings.CACHES['default']['BACKEND']), 'No new cache system was introduced.'),
        ('Source pagination size', str(PAGE_SIZE), 'Source default; the database value is used on product pages.'),
    ]


def restart_notice(instance):
    issues = []
    pairs = (
        ('Allowed Hosts', instance.allowed_hosts.strip(), ','.join(settings.ALLOWED_HOSTS)),
        ('HTTPS redirect', instance.secure_ssl_redirect, settings.SECURE_SSL_REDIRECT),
        ('Secure session cookie', instance.session_cookie_secure, settings.SESSION_COOKIE_SECURE),
        ('Secure CSRF cookie', instance.csrf_cookie_secure, settings.CSRF_COOKIE_SECURE),
        ('HSTS enabled', instance.hsts_enabled, settings.SECURE_HSTS_SECONDS > 0),
        ('HSTS max age', str(instance.hsts_seconds), str(settings.SECURE_HSTS_SECONDS)),
        ('HSTS subdomains', instance.hsts_include_subdomains, settings.SECURE_HSTS_INCLUDE_SUBDOMAINS),
        ('HSTS preload', instance.hsts_preload, settings.SECURE_HSTS_PRELOAD),
        ('Session expiry behavior', instance.session_expire_at_browser_close, settings.SESSION_EXPIRE_AT_BROWSER_CLOSE),
        ('Session age', str(instance.session_cookie_age), str(settings.SESSION_COOKIE_AGE)),
    )
    for label, stored, live in pairs:
        if str(stored) != str(live):
            issues.append(f'{label}: saved value differs from the running server. Restart required.')
    return issues


def security_warnings(instance):
    warnings = []
    if instance.environment == 'production' and settings.DEBUG:
        warnings.append('DEBUG is enabled in the running environment. Do not deploy this configuration to production.')
    if instance.environment == 'production':
        if not instance.secure_ssl_redirect:
            warnings.append('HTTPS redirect is disabled while the environment is set to Production.')
        if not instance.session_cookie_secure or not instance.csrf_cookie_secure:
            warnings.append('Secure session or CSRF cookies are disabled while the environment is set to Production.')
        if not instance.hsts_enabled:
            warnings.append('HSTS is disabled while the environment is set to Production.')
    if instance.allowed_hosts.strip() == '*':
        warnings.append('Allowed Hosts is set to “*”. Restrict this before production use.')
    return warnings
