import re
from urllib.parse import urlencode, urlparse

from django.conf import settings

from core.models import FooterSettings


def _http_url(value):
    value = (value or '').strip()
    parsed = urlparse(value)
    if parsed.scheme in {'http', 'https'} and parsed.netloc:
        return value
    return ''


def _page_url(value):
    value = (value or '').strip()
    parsed = urlparse(value)
    if parsed.scheme in {'http', 'https'} and parsed.netloc:
        return value
    if value.startswith('/') and not value.startswith('//'):
        return value
    return ''


def footer_links(request):
    footer_settings = FooterSettings.load()
    social_links = {
        'whatsapp': _http_url(footer_settings.whatsapp_url),
        'instagram': _http_url(footer_settings.instagram_url),
        'x': _http_url(footer_settings.x_url),
        'linkedin': _http_url(footer_settings.linkedin_url),
    }
    social_links = {name: url for name, url in social_links.items() if url}

    contact_email = (footer_settings.contact_email or '').strip()
    contact_phone = (footer_settings.contact_phone or '').strip()
    phone_digits = re.sub(r'\D', '', contact_phone) or re.sub(r'\D', '', settings.WHATSAPP_PHONE_NUMBER)
    message = urlencode({'text': 'Hi ThemeHaven! I need help regarding themes and templates.'})
    fallback_whatsapp_url = f'https://wa.me/{phone_digits}?{message}' if phone_digits else f'https://wa.me/?{message}'

    return {
        'footer': {
            'brand_description': footer_settings.brand_description,
            'help_heading': footer_settings.help_heading,
            'help_intro': footer_settings.help_intro,
            'support_button_label': footer_settings.support_button_label,
            'support_url': _page_url(footer_settings.support_url),
            'policies_heading': footer_settings.policies_heading,
            'privacy_label': footer_settings.privacy_label,
            'privacy_url': _page_url(footer_settings.privacy_url),
            'terms_label': footer_settings.terms_label,
            'terms_url': _page_url(footer_settings.terms_url),
            'refund_label': footer_settings.refund_label,
            'refund_url': _page_url(footer_settings.refund_url),
            'agreement_label': footer_settings.agreement_label,
            'agreement_url': _page_url(footer_settings.agreement_url),
            'contact_heading': footer_settings.contact_heading,
            'contact_email': contact_email,
            'contact_phone': contact_phone,
            'contact_phone_href': re.sub(r'[^\d+]', '', contact_phone),
            'contact_message': footer_settings.contact_message,
            'social_links': social_links,
            'copyright_text': footer_settings.copyright_text,
        },
        'social_links': social_links,
        'legal_links': {},
        'whatsapp_url': social_links.get('whatsapp') or fallback_whatsapp_url,
        'whatsapp_number_configured': bool(phone_digits) or bool(social_links.get('whatsapp')),
    }
