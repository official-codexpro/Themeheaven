import re
from urllib.parse import urlencode, urlparse

from django.conf import settings


def _configured_http_links(links):
    return {
        name: url
        for name, url in links.items()
        if url and urlparse(url).scheme in {"http", "https"} and urlparse(url).netloc
    }


def footer_links(request):
    phone_number = re.sub(r"\D", "", settings.WHATSAPP_PHONE_NUMBER)
    message = urlencode({"text": "Hi ThemeHaven! I need help regarding themes and templates."})
    return {
        "social_links": _configured_http_links(settings.SOCIAL_LINKS),
        "legal_links": _configured_http_links(settings.LEGAL_LINKS),
        "whatsapp_url": f"https://wa.me/{phone_number}?{message}" if phone_number else f"https://wa.me/?{message}",
        "whatsapp_number_configured": bool(phone_number),
    }
