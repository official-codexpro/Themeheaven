import os
import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from .storage import appearance_svg_storage, whatsapp_svg_storage
from .svg_sanitizer import SvgValidationError, sanitize_svg
from .validators import HEX_COLOR, validate_admin_logo, validate_gif_upload, validate_hex_color, validate_svg_upload, validate_whatsapp_phone

DEFAULT_WHATSAPP_MESSAGE = 'Hi ThemeHaven! I need help regarding themes and templates.'


def default_whatsapp_number():
    return settings.WHATSAPP_PHONE_NUMBER


def whatsapp_svg_path(instance, filename):
    return f'whatsapp-icon-{uuid.uuid4().hex}.svg'


def appearance_svg_path(instance, filename):
    return f'theme-switcher-{uuid.uuid4().hex}.svg'


class FooterSettings(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)

    brand_description = models.TextField(
        'Brand Description',
        max_length=320,
        default='Premium website themes and templates to bring your ideas to life. Find flexible, ready-to-use resources for modern websites and growing ideas.',
    )

    help_heading = models.CharField('Help & Support Heading', max_length=60, default='Help & Support')
    help_intro = models.CharField(
        'Help & Support Introduction',
        max_length=240,
        default='Need a hand finding the right theme or template?',
    )
    support_button_label = models.CharField('Support Button Text', max_length=60, default='Contact Support')
    support_url = models.CharField(
        'Support Page URL',
        max_length=200,
        default='/support/',
        help_text='Use an internal path such as /support/ or a full http(s) URL.',
    )

    policies_heading = models.CharField('Policies Heading', max_length=60, default='Policies')
    privacy_label = models.CharField('Privacy Policy Title', max_length=80, default='Privacy Policy')
    privacy_url = models.CharField(
        'Privacy Policy URL',
        max_length=200,
        default='/privacy-policy/',
        help_text='Use an internal path or a full http(s) URL.',
    )
    terms_label = models.CharField('Terms & Conditions Title', max_length=80, default='Terms & Conditions')
    terms_url = models.CharField(
        'Terms & Conditions URL',
        max_length=200,
        default='/terms-conditions/',
        help_text='Use an internal path or a full http(s) URL.',
    )
    refund_label = models.CharField('Refund Policy Title', max_length=80, default='Refund Policy')
    refund_url = models.CharField(
        'Refund Policy URL',
        max_length=200,
        default='/refund-cancellation-policy/',
        help_text='Use an internal path or a full http(s) URL.',
    )
    agreement_label = models.CharField('User Agreement Title', max_length=80, default='User Agreement')
    agreement_url = models.CharField(
        'User Agreement URL',
        max_length=200,
        default='/shipping-delivery-policy/',
        help_text='Use an internal path or a full http(s) URL.',
    )

    contact_heading = models.CharField('Contact Heading', max_length=60, default='Get in Touch')
    contact_email = models.EmailField('Contact Email', blank=True)
    contact_phone = models.CharField('Contact Phone Number', max_length=60, blank=True)
    contact_message = models.CharField(
        'Empty Contact Message',
        max_length=160,
        default='Contact details have not been configured yet.',
        help_text='Shown only when both email and phone are empty.',
    )
    whatsapp_url = models.URLField('WhatsApp URL', blank=True, help_text='Icon appears only when set.')
    instagram_url = models.URLField('Instagram URL', blank=True, help_text='Icon appears only when set.')
    x_url = models.URLField('X / Twitter URL', blank=True, help_text='Icon appears only when set.')
    linkedin_url = models.URLField('LinkedIn URL', blank=True, help_text='Icon appears only when set.')

    copyright_text = models.CharField(
        'Copyright Text',
        max_length=160,
        default='© 2026 ThemeHaven. All Rights Reserved.',
    )

    class Meta:
        verbose_name = 'Footer Settings'
        verbose_name_plural = 'Footer Settings'

    def __str__(self):
        return 'Footer Settings'

    def save(self, *args, **kwargs):
        self.pk = 1
        return super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        configured = getattr(settings, 'SOCIAL_LINKS', {})
        defaults = {
            'whatsapp_url': configured.get('whatsapp', ''),
            'instagram_url': configured.get('instagram', ''),
            'x_url': configured.get('x', ''),
            'linkedin_url': configured.get('linkedin', ''),
        }
        obj, _created = cls.objects.get_or_create(pk=1, defaults=defaults)
        return obj


class AppearanceSettings(models.Model):
    THEME_MODE_CHOICES = (
        ('single', 'Single Theme Mode'),
        ('multi', 'Multi Theme Mode'),
    )
    THEME_CHOICES = (
        ('dark', 'Default Dark Theme'),
        ('light', 'Default Light Theme'),
    )
    PREFERENCE_POLICY_CHOICES = (
        ('keep', 'Keep visitor preference'),
        ('follow', 'Follow new admin default'),
    )
    SWITCH_BEHAVIOR_CHOICES = (
        ('smooth', 'Smooth transition'),
        ('instant', 'Instant switch'),
    )
    DESKTOP_POSITION_CHOICES = (
        ('navbar', 'Navbar (default)'),
        ('bottom-right', 'Bottom right'),
        ('bottom-left', 'Bottom left'),
    )
    MOBILE_POSITION_CHOICES = (
        ('menu', 'Mobile menu (default)'),
        ('bottom-right', 'Bottom right'),
        ('bottom-left', 'Bottom left'),
    )
    WHATSAPP_POSITION_CHOICES = (
        ('bottom-right', 'Bottom right'),
        ('bottom-left', 'Bottom left'),
    )
    ANIMATION_CHOICES = (
        ('none', 'None'),
        ('float', 'Floating'),
        ('pulse', 'Pulse'),
        ('bounce', 'Bounce'),
    )
    BUTTON_STYLE_CHOICES = (
        ('rounded', 'Rounded'),
        ('pill', 'Pill'),
        ('square', 'Square'),
    )
    FONT_CHOICES = (
        ('jakarta', 'Plus Jakarta Sans'),
        ('inter', 'Inter'),
        ('system', 'System UI'),
        ('georgia', 'Georgia'),
    )

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)

    preference_policy = models.CharField(
        'Visitor Preference Policy',
        max_length=10,
        choices=PREFERENCE_POLICY_CHOICES,
        default='keep',
        help_text='Keep: saved visitor themes remain after the default changes. Follow new admin default: saved themes are reset when the default changes.',
    )
    switch_behavior = models.CharField(
        'Theme Switching Behavior',
        max_length=10,
        choices=SWITCH_BEHAVIOR_CHOICES,
        default='smooth',
    )

    theme_mode = models.CharField(
        'Theme Mode',
        max_length=10,
        choices=THEME_MODE_CHOICES,
        default='multi',
    )
    default_theme = models.CharField(
        'Default Theme',
        max_length=10,
        choices=THEME_CHOICES,
        default='dark',
        help_text='Used for new visitors and forced on everyone in Single Theme Mode.',
    )
    dark_theme_enabled = models.BooleanField('Dark Theme Available', default=True)
    light_theme_enabled = models.BooleanField('Light Theme Available', default=True)
    allow_visitor_switching = models.BooleanField('Allow Visitors to Switch Themes', default=True)
    show_theme_switchers = models.BooleanField('Show Theme Switchers Globally', default=True)

    dark_bg_primary = models.CharField('Main Background', max_length=7, default='#080611', validators=[validate_hex_color])
    dark_bg_secondary = models.CharField('Secondary Background', max_length=7, default='#100D1B', validators=[validate_hex_color])
    dark_bg_card = models.CharField('Card Background', max_length=7, default='#171326', validators=[validate_hex_color])
    dark_header_bg = models.CharField('Header / Navbar Background', max_length=7, default='#0B0915', validators=[validate_hex_color])
    dark_footer_bg = models.CharField('Footer Background', max_length=7, default='#100D1B', validators=[validate_hex_color])
    dark_text_primary = models.CharField('Primary Text Color', max_length=7, default='#F8F6FF', validators=[validate_hex_color])
    dark_text_secondary = models.CharField('Secondary Text Color', max_length=7, default='#C2BDD0', validators=[validate_hex_color])
    dark_heading_color = models.CharField('Heading Color', max_length=7, default='#F8F6FF', validators=[validate_hex_color])
    dark_border_color = models.CharField('Border Color', max_length=7, default='#342B45', validators=[validate_hex_color])
    dark_button_bg = models.CharField('Button Background', max_length=7, default='#8B35F5', validators=[validate_hex_color])
    dark_button_text = models.CharField('Button Text Color', max_length=7, default='#FFFFFF', validators=[validate_hex_color])
    dark_input_bg = models.CharField('Input Background', max_length=7, default='#171326', validators=[validate_hex_color])
    dark_input_text = models.CharField('Input Text Color', max_length=7, default='#F8F6FF', validators=[validate_hex_color])
    dark_link_color = models.CharField('Link Color', max_length=7, default='#A04FFF', validators=[validate_hex_color])
    dark_accent_color = models.CharField('Accent Color', max_length=7, default='#8B35F5', validators=[validate_hex_color])

    light_bg_primary = models.CharField('Main Background', max_length=7, default='#FAF8FF', validators=[validate_hex_color])
    light_bg_secondary = models.CharField('Secondary Background', max_length=7, default='#FFFFFF', validators=[validate_hex_color])
    light_bg_card = models.CharField('Card Background', max_length=7, default='#F1EDFB', validators=[validate_hex_color])
    light_header_bg = models.CharField('Header / Navbar Background', max_length=7, default='#FAF8FF', validators=[validate_hex_color])
    light_footer_bg = models.CharField('Footer Background', max_length=7, default='#FFFFFF', validators=[validate_hex_color])
    light_text_primary = models.CharField('Primary Text Color', max_length=7, default='#101027', validators=[validate_hex_color])
    light_text_secondary = models.CharField('Secondary Text Color', max_length=7, default='#3E3A59', validators=[validate_hex_color])
    light_heading_color = models.CharField('Heading Color', max_length=7, default='#101027', validators=[validate_hex_color])
    light_border_color = models.CharField('Border Color', max_length=7, default='#D9CDF0', validators=[validate_hex_color])
    light_button_bg = models.CharField('Button Background', max_length=7, default='#8B35F5', validators=[validate_hex_color])
    light_button_text = models.CharField('Button Text Color', max_length=7, default='#FFFFFF', validators=[validate_hex_color])
    light_input_bg = models.CharField('Input Background', max_length=7, default='#FFFFFF', validators=[validate_hex_color])
    light_input_text = models.CharField('Input Text Color', max_length=7, default='#101027', validators=[validate_hex_color])
    light_link_color = models.CharField('Link Color', max_length=7, default='#7E28E0', validators=[validate_hex_color])
    light_accent_color = models.CharField('Accent Color', max_length=7, default='#8B35F5', validators=[validate_hex_color])

    desktop_enabled = models.BooleanField('Enable Desktop Theme Button', default=True)
    desktop_background_enabled = models.BooleanField('Use Custom Background', default=False)
    desktop_background_color = models.CharField('Button Background Color', max_length=7, default='#1A1228', validators=[validate_hex_color])
    desktop_icon_color = models.CharField('Icon Color', max_length=7, default='#E9DFFF', validators=[validate_hex_color])
    desktop_custom_svg = models.FileField(
        'Custom SVG Icon',
        upload_to=appearance_svg_path,
        storage=appearance_svg_storage,
        validators=[validate_svg_upload],
        blank=True,
        help_text='Optional sanitized SVG that replaces the default lamp indicator icon.',
    )
    desktop_svg_markup = models.TextField(editable=False, blank=True)
    desktop_icon_size = models.PositiveIntegerField('Icon Size (px)', default=8, validators=[MinValueValidator(4), MaxValueValidator(120)])
    desktop_button_size = models.PositiveIntegerField('Button Size (px)', default=48, validators=[MinValueValidator(16), MaxValueValidator(240)])
    desktop_border_radius = models.PositiveIntegerField('Border Radius (px)', default=16, validators=[MaxValueValidator(200)])
    desktop_position = models.CharField('Button Position', max_length=12, choices=DESKTOP_POSITION_CHOICES, default='navbar')
    desktop_tooltip_enabled = models.BooleanField('Enable Tooltip', default=True)
    desktop_tooltip_text = models.CharField('Tooltip Text', max_length=120, default='Pull to switch theme')
    desktop_hover_effects = models.BooleanField('Enable Hover Effects', default=True)
    desktop_transition = models.BooleanField('Enable Transition Animation', default=True)

    mobile_enabled = models.BooleanField('Enable Mobile Theme Button', default=True)
    mobile_background_enabled = models.BooleanField('Use Custom Background', default=False)
    mobile_background_color = models.CharField('Button Background Color', max_length=7, default='#171326', validators=[validate_hex_color])
    mobile_icon_color = models.CharField('Icon Color', max_length=7, default='#8B35F5', validators=[validate_hex_color])
    mobile_custom_svg = models.FileField(
        'Custom SVG Icon',
        upload_to=appearance_svg_path,
        storage=appearance_svg_storage,
        validators=[validate_svg_upload],
        blank=True,
        help_text='Optional sanitized SVG that replaces the default mobile theme icon.',
    )
    mobile_svg_markup = models.TextField(editable=False, blank=True)
    mobile_icon_size = models.PositiveIntegerField('Icon Size (px)', default=20, validators=[MinValueValidator(8), MaxValueValidator(120)])
    mobile_button_size = models.PositiveIntegerField('Button Size (px)', default=44, validators=[MinValueValidator(24), MaxValueValidator(200)])
    mobile_border_radius = models.PositiveIntegerField('Border Radius (px)', default=8, validators=[MaxValueValidator(200)])
    mobile_position = models.CharField('Button Position', max_length=12, choices=MOBILE_POSITION_CHOICES, default='menu')
    mobile_tooltip_enabled = models.BooleanField('Enable Tooltip', default=False)
    mobile_tooltip_text = models.CharField('Tooltip Text', max_length=120, default='Switch theme')
    mobile_hover_effects = models.BooleanField('Enable Hover Effects', default=True)
    mobile_transition = models.BooleanField('Enable Transition Animation', default=True)

    whatsapp_enabled = models.BooleanField('Enable WhatsApp Floating Button', default=True)
    phone_number = models.CharField(
        'WhatsApp Number',
        max_length=40,
        blank=True,
        default=default_whatsapp_number,
        validators=[validate_whatsapp_phone],
        help_text='Include the country code, for example +1 555 123 4567.',
    )
    default_message = models.CharField(
        'Default Message',
        max_length=500,
        blank=True,
        default=DEFAULT_WHATSAPP_MESSAGE,
        help_text='Pre-filled in WhatsApp when a visitor opens the chat.',
    )
    background_color = models.CharField('Button Background Color', max_length=7, default='#25D366', validators=[validate_hex_color])
    icon_color = models.CharField('Icon Color', max_length=7, default='#FFFFFF', validators=[validate_hex_color])
    custom_svg = models.FileField(
        'Custom SVG Icon',
        upload_to=whatsapp_svg_path,
        storage=whatsapp_svg_storage,
        validators=[validate_svg_upload],
        blank=True,
        help_text='Upload a .svg file (256 KB max). Unsafe scripts and external references are removed. Clear the field to restore the default icon.',
    )
    custom_svg_markup = models.TextField(editable=False, blank=True)
    button_size = models.PositiveIntegerField('Button Size (px)', default=60, validators=[MinValueValidator(24), MaxValueValidator(240)])
    icon_size = models.PositiveIntegerField('Icon Size (px)', default=32, validators=[MinValueValidator(8), MaxValueValidator(200)])
    border_radius = models.PositiveIntegerField('Border Radius (px)', default=999, validators=[MinValueValidator(0), MaxValueValidator(9999)])
    position = models.CharField('Button Position', max_length=12, choices=WHATSAPP_POSITION_CHOICES, default='bottom-right')
    horizontal_offset = models.PositiveIntegerField('Horizontal Offset (px)', default=16, validators=[MaxValueValidator(500)])
    vertical_offset = models.PositiveIntegerField('Vertical Offset (px)', default=16, validators=[MaxValueValidator(500)])
    z_index = models.PositiveIntegerField('Z-Index', default=70, validators=[MinValueValidator(1), MaxValueValidator(2147483647)])
    tooltip_enabled = models.BooleanField('Enable Tooltip', default=True)
    tooltip_text = models.CharField('Tooltip Text', max_length=120, default='Chat with us')
    animation = models.CharField('Button Animation', max_length=10, choices=ANIMATION_CHOICES, default='none')
    show_on_mobile = models.BooleanField('Show on Mobile', default=True)
    show_on_desktop = models.BooleanField('Show on Desktop', default=True)

    global_animations_enabled = models.BooleanField('Enable Website Animations', default=True)
    global_hover_enabled = models.BooleanField('Enable Hover Effects', default=True)
    global_transitions_enabled = models.BooleanField('Enable Smooth Transitions', default=True)
    global_border_radius = models.PositiveIntegerField('Global Border Radius (px)', default=12, validators=[MaxValueValidator(200)])
    global_accent_color = models.CharField('Global Accent Color', max_length=7, default='#8B35F5', validators=[validate_hex_color])
    global_button_style = models.CharField('Global Button Style', max_length=10, choices=BUTTON_STYLE_CHOICES, default='rounded')
    font_family = models.CharField('Website Font Family', max_length=10, choices=FONT_CHOICES, default='jakarta')

    class Meta:
        verbose_name = 'Appearance & Theme Settings'
        verbose_name_plural = 'Appearance & Theme Settings'

    def __str__(self):
        return 'Appearance & Theme Settings'

    def _refresh_svg_markup(self, field_name, markup_name):
        upload = getattr(self, field_name)
        if not upload:
            setattr(self, markup_name, '')
            return
        try:
            upload.seek(0)
            setattr(self, markup_name, sanitize_svg(upload.read()))
        except (OSError, ValueError, SvgValidationError):
            setattr(self, markup_name, '')
        finally:
            upload.seek(0)

    def save(self, *args, **kwargs):
        self.pk = 1
        previous = None
        if not self._state.adding:
            previous = type(self).objects.filter(pk=1).first()

        for field_name, markup_name in (
            ('desktop_custom_svg', 'desktop_svg_markup'),
            ('mobile_custom_svg', 'mobile_svg_markup'),
            ('custom_svg', 'custom_svg_markup'),
        ):
            self._refresh_svg_markup(field_name, markup_name)

        if kwargs.get('update_fields') is not None:
            kwargs['update_fields'] = set(kwargs['update_fields']) | {
                'desktop_svg_markup', 'mobile_svg_markup', 'custom_svg_markup',
            }

        super().save(*args, **kwargs)

        if previous:
            for field_name in ('desktop_custom_svg', 'mobile_custom_svg', 'custom_svg'):
                old_file = getattr(previous, field_name)
                if old_file and old_file.name != getattr(self, field_name).name:
                    old_file.delete(save=False)

    def delete(self, *args, **kwargs):
        for field_name in ('desktop_custom_svg', 'mobile_custom_svg', 'custom_svg'):
            upload = getattr(self, field_name)
            if upload:
                upload.delete(save=False)
        return super().delete(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj


def error_page_gif_path(instance, filename):
    return f'error_pages/404/{uuid.uuid4().hex}.gif'


_error_page_settings_cache = None


class ErrorPageSettings(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)

    enabled = models.BooleanField(
        'Enable Custom 404 Page',
        default=True,
        help_text='Turn off to return a plain 404 response without the custom page.',
    )
    gif = models.ImageField(
        '404 GIF',
        upload_to=error_page_gif_path,
        validators=[validate_gif_upload],
        blank=True,
        help_text='Upload a .gif file. Animation is preserved and displayed as uploaded.',
    )
    background_color = models.CharField(
        '404 Background Color',
        max_length=7,
        default='#ffffff',
        validators=[validate_hex_color],
        help_text='Use a hex color such as #ffffff.',
    )
    heading = models.CharField('404 Heading', max_length=80, blank=True, default='Page Not Found')
    message = models.CharField(
        '404 Message',
        max_length=200,
        blank=True,
        default="The page you're looking for doesn't exist, has been moved, or may be temporarily unavailable.",
    )
    supporting_message = models.CharField(
        '404 Supporting Message',
        max_length=240,
        blank=True,
        default='Check the address or use one of the buttons below to keep browsing.',
    )
    home_button_enabled = models.BooleanField('Show Home Button', default=True)
    home_button_text = models.CharField('Home Button Text', max_length=40, default='Back to Home')

    class Meta:
        verbose_name = '404 Error Page Settings'
        verbose_name_plural = '404 Error Page Settings'

    def __str__(self):
        return '404 Error Page Settings'

    @property
    def safe_background_color(self):
        value = (self.background_color or '').strip()
        return value if HEX_COLOR.fullmatch(value) else '#ffffff'

    def save(self, *args, **kwargs):
        self.pk = 1
        previous_file = None
        if not self._state.adding:
            existing = type(self).objects.filter(pk=1).first()
            if existing and existing.gif and existing.gif.name != self.gif.name:
                previous_file = existing.gif

        super().save(*args, **kwargs)
        clear_error_page_settings_cache()

        if previous_file and previous_file.name != self.gif.name:
            previous_file.delete(save=False)

    def delete(self, *args, **kwargs):
        if self.gif:
            self.gif.delete(save=False)
        clear_error_page_settings_cache()
        return super().delete(*args, **kwargs)

    @classmethod
    def load(cls):
        global _error_page_settings_cache
        if _error_page_settings_cache is None:
            obj, _created = cls.objects.get_or_create(pk=1)
            _error_page_settings_cache = obj
        return _error_page_settings_cache


def clear_error_page_settings_cache():
    global _error_page_settings_cache
    _error_page_settings_cache = None


def system_admin_logo_path(instance, filename):
    return f'system/admin/logo-{uuid.uuid4().hex}{os.path.splitext(filename)[1].lower()}'


COMMON_TIMEZONES = (
    'UTC',
    'America/Anchorage', 'America/Chicago', 'America/Denver', 'America/Los_Angeles',
    'America/New_York', 'America/Sao_Paulo', 'America/Toronto',
    'Asia/Dubai', 'Asia/Hong_Kong', 'Asia/Jakarta', 'Asia/Karachi',
    'Asia/Kolkata', 'Asia/Seoul', 'Asia/Shanghai', 'Asia/Singapore',
    'Asia/Tokyo', 'Australia/Brisbane', 'Australia/Melbourne', 'Australia/Sydney',
    'Europe/Amsterdam', 'Europe/Berlin', 'Europe/London', 'Europe/Madrid',
    'Europe/Paris', 'Europe/Rome', 'Europe/Warsaw', 'Europe/Zurich',
    'Pacific/Auckland', 'Pacific/Honolulu',
)


def timezone_choices():
    return [(zone, zone) for zone in COMMON_TIMEZONES]


LANGUAGE_CHOICES = (
    ('en-us', 'English (US)'),
    ('en-gb', 'English (UK)'),
    ('hi', 'Hindi'),
    ('es-es', 'Spanish'),
    ('fr', 'French'),
    ('de', 'German'),
)

ENVIRONMENT_CHOICES = (
    ('development', 'Development'),
    ('staging', 'Staging'),
    ('production', 'Production'),
)


class SystemSettings(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)

    admin_site_name = models.CharField('Admin Site Name', max_length=80, default='themehaven.in')
    admin_header = models.CharField('Admin Header', max_length=80, default='themehaven.in')
    admin_browser_title = models.CharField('Admin Browser Title', max_length=80, default='themehaven.in')
    admin_welcome_text = models.TextField('Admin Welcome Text', max_length=500, blank=True)
    admin_logo = models.ImageField(
        'Admin Logo',
        upload_to=system_admin_logo_path,
        validators=[validate_admin_logo],
        blank=True,
        help_text='Optional PNG, JPG, WebP, or GIF up to 512 KB. SVG is not accepted.',
    )

    allowed_hosts = models.TextField(
        'Allowed Hosts',
        max_length=500,
        blank=True,
        help_text='One host per line. Requires a server restart. Leave empty to keep the environment configuration.',
    )
    time_zone = models.CharField('Time Zone', max_length=64, choices=timezone_choices, default='UTC')
    language_code = models.CharField('Language Code', max_length=10, choices=LANGUAGE_CHOICES, default='en-us')
    site_base_url = models.URLField('Site Base URL', blank=True, help_text='Used for the admin “View site” link.')
    environment = models.CharField('Environment', max_length=12, choices=ENVIRONMENT_CHOICES, default='development')
    app_version = models.CharField('Application Version', max_length=40, blank=True)

    secure_ssl_redirect = models.BooleanField('Force HTTPS Redirect', default=False)
    session_cookie_secure = models.BooleanField('Secure Session Cookie', default=False)
    csrf_cookie_secure = models.BooleanField('Secure CSRF Cookie', default=False)
    hsts_enabled = models.BooleanField('Enable HSTS', default=True)
    hsts_seconds = models.PositiveIntegerField('HSTS Max Age (seconds)', default=31536000, validators=[MinValueValidator(60), MaxValueValidator(63072000)])
    hsts_include_subdomains = models.BooleanField('HSTS Include Subdomains', default=True)
    hsts_preload = models.BooleanField('HSTS Preload', default=False)

    session_expire_at_browser_close = models.BooleanField('Expire Session at Browser Close', default=True)
    session_cookie_age = models.PositiveIntegerField('Session Cookie Age (seconds)', default=1209600, validators=[MinValueValidator(60), MaxValueValidator(31536000)])

    cache_timeout = models.PositiveIntegerField('Settings Cache Timeout (seconds)', default=300, validators=[MinValueValidator(1), MaxValueValidator(86400)])
    page_size = models.PositiveIntegerField('Default Page Size', default=8, validators=[MinValueValidator(1), MaxValueValidator(48)])
    max_page_size = models.PositiveIntegerField('Maximum Page Size', default=48, validators=[MinValueValidator(1), MaxValueValidator(100)])

    class Meta:
        verbose_name = 'System Settings'
        verbose_name_plural = 'System Settings'

    def __str__(self):
        return 'System Settings'

    def save(self, *args, **kwargs):
        self.pk = 1
        previous_file = None
        if not self._state.adding:
            existing = type(self).objects.filter(pk=1).first()
            if existing and existing.admin_logo and existing.admin_logo.name != self.admin_logo.name:
                previous_file = existing.admin_logo

        super().save(*args, **kwargs)
        clear_system_settings_cache()

        if previous_file and previous_file.name != self.admin_logo.name:
            previous_file.delete(save=False)

    def delete(self, *args, **kwargs):
        if self.admin_logo:
            self.admin_logo.delete(save=False)
        clear_system_settings_cache()
        return super().delete(*args, **kwargs)

    @classmethod
    def load(cls):
        from .system_settings import get_system_settings

        return get_system_settings()


class SystemSettingsChange(models.Model):
    changed_at = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    category = models.CharField(max_length=40)
    changes = models.TextField()

    class Meta:
        verbose_name = 'System Settings Change'
        verbose_name_plural = 'System Settings Changes'
        ordering = ('-changed_at',)

    def __str__(self):
        return f'{self.category} settings changed at {self.changed_at:%Y-%m-%d %H:%M}'


def clear_system_settings_cache():
    from .system_settings import clear_system_settings_cache as clear

    clear()
