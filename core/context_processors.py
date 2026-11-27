import colorsys
import hashlib
import re
from urllib.parse import urlencode, urlparse

from django.conf import settings

from core.models import DEFAULT_WHATSAPP_MESSAGE, AppearanceSettings, FooterSettings


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


def _digits(value):
    return re.sub(r'\D', '', value or '')


def _whatsapp_chat_url(phone_number, message):
    digits = _digits(phone_number)
    query = urlencode({'text': message}) if message else ''
    return f"https://wa.me/{digits}{'?' + query if query else ''}"


def _shade(hex_color, amount):
    value = (hex_color or '#000000').lstrip('#')
    if len(value) != 6:
        return hex_color
    red, green, blue = (int(value[index:index + 2], 16) / 255 for index in (0, 2, 4))
    hue, lightness, saturation = colorsys.rgb_to_hls(red, green, blue)
    lightness = min(1, max(0, lightness + amount))
    red, green, blue = colorsys.hls_to_rgb(hue, lightness, saturation)
    return '#{:02X}{:02X}{:02X}'.format(round(red * 255), round(green * 255), round(blue * 255))


def _theme_colors(config, prefix):
    names = (
        'bg_primary', 'bg_secondary', 'bg_card', 'header_bg', 'footer_bg',
        'text_primary', 'text_secondary', 'heading_color', 'border_color',
        'button_bg', 'button_text', 'input_bg', 'input_text', 'link_color',
        'accent_color',
    )
    colors = {name: getattr(config, f'{prefix}_{name}') for name in names}
    colors['accent_hover'] = _shade(colors['accent_color'], 0.12)
    colors['button_hover'] = _shade(colors['button_bg'], -0.1)
    return colors


def _switcher(config, prefix):
    enabled = getattr(config, f'{prefix}_enabled')
    return {
        'enabled': enabled,
        'background_enabled': getattr(config, f'{prefix}_background_enabled'),
        'background_color': getattr(config, f'{prefix}_background_color'),
        'icon_color': getattr(config, f'{prefix}_icon_color'),
        'svg_markup': getattr(config, f'{prefix}_svg_markup'),
        'icon_size': getattr(config, f'{prefix}_icon_size'),
        'button_size': getattr(config, f'{prefix}_button_size'),
        'border_radius': getattr(config, f'{prefix}_border_radius'),
        'position': getattr(config, f'{prefix}_position'),
        'tooltip_enabled': getattr(config, f'{prefix}_tooltip_enabled'),
        'tooltip_text': getattr(config, f'{prefix}_tooltip_text'),
        'hover_effects': getattr(config, f'{prefix}_hover_effects'),
        'transition': getattr(config, f'{prefix}_transition'),
    }


def footer_links(request):
    footer_settings = FooterSettings.load()
    appearance = AppearanceSettings.load()
    social_links = {
        'whatsapp': _http_url(footer_settings.whatsapp_url),
        'instagram': _http_url(footer_settings.instagram_url),
        'x': _http_url(footer_settings.x_url),
        'linkedin': _http_url(footer_settings.linkedin_url),
    }
    social_links = {name: url for name, url in social_links.items() if url}

    contact_email = (footer_settings.contact_email or '').strip()
    contact_phone = (footer_settings.contact_phone or '').strip()
    message = (appearance.default_message or '').strip() or DEFAULT_WHATSAPP_MESSAGE
    admin_phone = (appearance.phone_number or '').strip()
    env_phone = settings.WHATSAPP_PHONE_NUMBER or ''

    if _digits(admin_phone):
        whatsapp_url = _whatsapp_chat_url(admin_phone, message)
    elif social_links.get('whatsapp'):
        whatsapp_url = social_links['whatsapp']
    elif _digits(contact_phone):
        whatsapp_url = _whatsapp_chat_url(contact_phone, message)
    elif _digits(env_phone):
        whatsapp_url = _whatsapp_chat_url(env_phone, message)
    else:
        whatsapp_url = _whatsapp_chat_url('', message)

    number_configured = any((
        _digits(admin_phone),
        social_links.get('whatsapp'),
        _digits(contact_phone),
        _digits(env_phone),
    ))

    available_themes = [
        theme for theme, enabled in (
            ('dark', appearance.dark_theme_enabled),
            ('light', appearance.light_theme_enabled),
        ) if enabled
    ]
    if not available_themes:
        available_themes = [appearance.default_theme]
    default_theme = appearance.default_theme if appearance.default_theme in available_themes else available_themes[0]

    can_switch = (
        appearance.theme_mode == 'multi'
        and appearance.allow_visitor_switching
        and appearance.show_theme_switchers
        and len(available_themes) > 1
    )
    forced_theme = default_theme if not can_switch else None
    desktop = _switcher(appearance, 'desktop')
    mobile = _switcher(appearance, 'mobile')
    desktop['enabled'] = can_switch and desktop['enabled']
    mobile['enabled'] = can_switch and mobile['enabled']

    preference_token = 'keep'
    if appearance.preference_policy == 'follow':
        token_source = f'{appearance.theme_mode}|{default_theme}|{can_switch}|{"".join(available_themes)}'
        preference_token = hashlib.sha256(token_source.encode()).hexdigest()[:12]

    accent = appearance.global_accent_color
    button_radius = {'rounded': 12, 'pill': 999, 'square': 0}[appearance.global_button_style]
    font_stacks = {
        'jakarta': '"Plus Jakarta Sans", sans-serif',
        'inter': '"Inter", sans-serif',
        'system': 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
        'georgia': 'Georgia, "Times New Roman", serif',
    }
    html_classes = []
    if not appearance.global_animations_enabled:
        html_classes.append('appearance-no-animation')
    if not appearance.global_hover_enabled:
        html_classes.append('appearance-no-hover')
    if not appearance.global_transitions_enabled:
        html_classes.append('appearance-no-transition')
    if appearance.switch_behavior == 'instant':
        html_classes.append('appearance-instant-theme')

    dark_colors = _theme_colors(appearance, 'dark')
    light_colors = _theme_colors(appearance, 'light')
    tooltip_text = appearance.tooltip_text or ''
    tooltip_title = tooltip_text
    if not number_configured:
        tooltip_title = f'{tooltip_title} — select ThemeHaven from your WhatsApp contacts'.strip()

    appearance_data = {
        'theme_mode': appearance.theme_mode,
        'default_theme': default_theme,
        'forced_theme': forced_theme,
        'can_switch': can_switch,
        'available_themes': available_themes,
        'preference_policy': appearance.preference_policy,
        'preference_token': preference_token,
        'switch_behavior': appearance.switch_behavior,
        'dark': dark_colors,
        'light': light_colors,
        'desktop': desktop,
        'mobile': mobile,
        'global': {
            'border_radius': appearance.global_border_radius,
            'accent_color': accent,
            'accent_hover': _shade(accent, 0.12),
            'accent_shadow': _shade(accent, -0.12),
            'button_radius': button_radius,
            'font_stack': font_stacks[appearance.font_family],
            'font_family': appearance.font_family,
        },
        'html_classes': ' '.join(html_classes),
        'config': {
            'canSwitch': can_switch,
            'themes': available_themes,
            'defaultTheme': default_theme,
            'forcedTheme': forced_theme,
            'preferencePolicy': appearance.preference_policy,
            'token': preference_token,
            'behavior': appearance.switch_behavior,
            'metaColors': {
                'dark': dark_colors['bg_primary'],
                'light': light_colors['bg_primary'],
            },
            'desktopCustomIcon': bool(appearance.desktop_svg_markup),
            'mobileCustomIcon': bool(appearance.mobile_svg_markup),
            'desktopTooltip': appearance.desktop_tooltip_text if appearance.desktop_tooltip_enabled else '',
        },
    }

    whatsapp_float = {
        'enabled': appearance.whatsapp_enabled and (
            appearance.show_on_mobile or appearance.show_on_desktop
        ),
        'url': whatsapp_url,
        'number_configured': number_configured,
        'background_color': appearance.background_color,
        'icon_color': appearance.icon_color,
        'svg_markup': appearance.custom_svg_markup,
        'icon_size': appearance.icon_size,
        'button_size': appearance.button_size,
        'border_radius': appearance.border_radius,
        'position': appearance.position,
        'horizontal_offset': appearance.horizontal_offset,
        'vertical_offset': appearance.vertical_offset,
        'z_index': appearance.z_index,
        'tooltip_enabled': appearance.tooltip_enabled and bool(tooltip_text),
        'tooltip_text': tooltip_text,
        'tooltip_title': tooltip_title,
        'hide_on_mobile': not appearance.show_on_mobile,
        'hide_on_desktop': not appearance.show_on_desktop,
        'animation': appearance.animation,
    }

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
        'whatsapp_url': whatsapp_url,
        'whatsapp_number_configured': number_configured,
        'whatsapp_float': whatsapp_float,
        'appearance': appearance_data,
    }
