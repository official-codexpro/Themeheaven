import re

from django import forms
from django.conf import settings

from .models import SystemSettings
from . import system_settings as system

HOST_PATTERN = re.compile(r'^(?:\*|[A-Za-z0-9.-]+(?::\d+)?)$')


class AdminBrandingForm(forms.ModelForm):
    class Meta:
        model = SystemSettings
        fields = ('admin_site_name', 'admin_header', 'admin_browser_title', 'admin_welcome_text', 'admin_logo')
        widgets = {
            'admin_welcome_text': forms.Textarea(attrs={'rows': 4}),
        }


class GeneralConfigurationForm(forms.ModelForm):
    class Meta:
        model = SystemSettings
        fields = ('allowed_hosts', 'time_zone', 'language_code', 'site_base_url', 'environment', 'app_version')
        widgets = {
            'allowed_hosts': forms.Textarea(attrs={'rows': 4}),
        }
        help_texts = {
            'allowed_hosts': 'One host per line. This value requires a server restart to affect the running server.',
            'time_zone': 'Applied to admin rendering immediately; the project default requires a restart.',
            'language_code': 'Applied to admin rendering immediately; the project default requires a restart.',
        }

    def clean_allowed_hosts(self):
        value = (self.cleaned_data.get('allowed_hosts') or '').strip()
        hosts = [host.strip() for host in re.split(r'[\n,]', value) if host.strip()]
        for host in hosts:
            if not HOST_PATTERN.fullmatch(host):
                raise forms.ValidationError(f'“{host}” is not a valid host. Use one host per line.')
        return '\n'.join(hosts)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('environment') == 'production' and settings.DEBUG:
            self.add_error(None, 'DEBUG is enabled in the running environment. Production must be deployed with DEBUG disabled.')
        return cleaned


class SecurityForm(forms.ModelForm):
    class Meta:
        model = SystemSettings
        fields = (
            'secure_ssl_redirect', 'session_cookie_secure', 'csrf_cookie_secure',
            'hsts_enabled', 'hsts_seconds', 'hsts_include_subdomains', 'hsts_preload',
        )
        help_texts = {
            'secure_ssl_redirect': 'Requires a server restart. Do not disable on a public site.',
            'session_cookie_secure': 'Requires a server restart.',
            'csrf_cookie_secure': 'Requires a server restart.',
            'hsts_enabled': 'Requires a server restart.',
        }

    def clean(self):
        cleaned = super().clean()
        if self.instance.environment != 'production':
            return cleaned

        if not cleaned.get('secure_ssl_redirect'):
            self.add_error('secure_ssl_redirect', 'HTTPS redirect must stay enabled in Production.')
        if not cleaned.get('session_cookie_secure'):
            self.add_error('session_cookie_secure', 'Secure session cookies must stay enabled in Production.')
        if not cleaned.get('csrf_cookie_secure'):
            self.add_error('csrf_cookie_secure', 'Secure CSRF cookies must stay enabled in Production.')
        if not cleaned.get('hsts_enabled'):
            self.add_error('hsts_enabled', 'HSTS must stay enabled in Production.')
        return cleaned


class SessionsForm(forms.ModelForm):
    class Meta:
        model = SystemSettings
        fields = ('session_expire_at_browser_close', 'session_cookie_age')
        help_texts = {
            'session_cookie_age': 'Used only when sessions do not expire at browser close. Requires a restart.',
        }


class PerformanceForm(forms.ModelForm):
    class Meta:
        model = SystemSettings
        fields = ('cache_timeout', 'page_size', 'max_page_size')
        help_texts = {
            'cache_timeout': 'Applies immediately to system settings caching.',
            'page_size': 'Applies immediately to product listings on the website.',
            'max_page_size': 'Upper limit accepted for the default page size.',
        }

    def clean(self):
        cleaned = super().clean()
        page_size = cleaned.get('page_size')
        max_page_size = cleaned.get('max_page_size')
        if page_size and max_page_size and page_size > max_page_size:
            self.add_error('page_size', 'Default page size cannot exceed the maximum page size.')
        return cleaned


CATEGORIES = {
    'admin-branding': {
        'name': 'Admin Branding',
        'description': 'Customize the Django admin name, header, welcome text, and logo.',
        'form': AdminBrandingForm,
        'info': None,
    },
    'general': {
        'name': 'General Configuration',
        'description': 'Hosts, language, time zone, environment label, and application version.',
        'form': GeneralConfigurationForm,
        'info': None,
    },
    'security': {
        'name': 'Security',
        'description': 'HTTPS, secure cookies, and HSTS configuration with production safeguards.',
        'form': SecurityForm,
        'info': system.security_information,
    },
    'sessions': {
        'name': 'Sessions & Authentication',
        'description': 'Session lifetime and authentication configuration visibility.',
        'form': SessionsForm,
        'info': system.session_information,
    },
    'performance': {
        'name': 'Performance & Cache',
        'description': 'Settings cache lifetime and product pagination limits.',
        'form': PerformanceForm,
        'info': system.cache_information,
    },
    'email': {
        'name': 'Email Configuration',
        'description': 'Read-only overview of the environment-managed email setup.',
        'form': None,
        'info': system.email_information,
    },
    'storage': {
        'name': 'Storage Configuration',
        'description': 'Read-only overview of media, static, and upload configuration.',
        'form': None,
        'info': system.storage_information,
    },
    'system': {
        'name': 'System Information',
        'description': 'Read-only diagnostics for the running Django project.',
        'form': None,
        'info': system.system_information,
    },
}
