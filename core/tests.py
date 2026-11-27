import tempfile

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import models
from django.template.loader import get_template
from django.test import RequestFactory, TestCase
from django.urls import reverse

from core.admin import AppearanceSettingsAdmin
from core.context_processors import footer_links
from core.models import AppearanceSettings, FooterSettings
from core.storage import appearance_svg_storage, whatsapp_svg_storage
from core.svg_sanitizer import sanitize_svg
from core.validators import validate_hex_color, validate_svg_upload, validate_whatsapp_phone


UNSAFE_SVG = (
    b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)">'
    b'<script>alert(1)</script>'
    b'<path d="M0 0" fill="red" onclick="alert(2)"/></svg>'
)


def nav_html(response):
    html = response.content.decode()
    return html.split('<nav', 1)[1].split('</nav>', 1)[0]


def admin_post_data(obj):
    data = {}
    for field in AppearanceSettings._meta.fields:
        if not field.editable or field.primary_key or isinstance(field, models.FileField):
            continue
        value = getattr(obj, field.attname)
        if isinstance(field, models.BooleanField):
            data[field.name] = 'on' if value else ''
        else:
            data[field.name] = str(value)
    return data


class AppearanceSettingsModelTests(TestCase):
    def test_defaults_and_single_record(self):
        settings_obj = AppearanceSettings.load()
        self.assertEqual(settings_obj.pk, 1)
        self.assertEqual(settings_obj.theme_mode, 'multi')
        self.assertEqual(settings_obj.default_theme, 'dark')
        self.assertTrue(settings_obj.dark_theme_enabled)
        self.assertTrue(settings_obj.light_theme_enabled)
        self.assertTrue(settings_obj.allow_visitor_switching)
        self.assertTrue(settings_obj.desktop_enabled)
        self.assertTrue(settings_obj.mobile_enabled)
        self.assertTrue(settings_obj.whatsapp_enabled)
        self.assertTrue(settings_obj.global_animations_enabled)
        self.assertEqual(settings_obj.preference_policy, 'keep')
        self.assertEqual(settings_obj.switch_behavior, 'smooth')

        AppearanceSettings.load()
        self.assertEqual(AppearanceSettings.objects.count(), 1)

    def test_saved_values_are_read_fresh(self):
        settings_obj = AppearanceSettings.load()
        settings_obj.default_theme = 'light'
        settings_obj.global_accent_color = '#123456'
        settings_obj.save()
        reloaded = AppearanceSettings.load()
        self.assertEqual(reloaded.default_theme, 'light')
        self.assertEqual(reloaded.global_accent_color, '#123456')

    def test_all_svg_uploads_are_sanitized_and_can_be_removed(self):
        appearance_root = tempfile.TemporaryDirectory()
        whatsapp_root = tempfile.TemporaryDirectory()
        original_appearance_location = appearance_svg_storage.location
        original_whatsapp_location = whatsapp_svg_storage.location
        appearance_svg_storage.location = appearance_root.name
        whatsapp_svg_storage.location = whatsapp_root.name
        try:
            settings_obj = AppearanceSettings.load()
            upload = SimpleUploadedFile('icon.svg', UNSAFE_SVG, content_type='image/svg+xml')
            settings_obj.desktop_custom_svg = upload
            settings_obj.mobile_custom_svg = SimpleUploadedFile('icon.svg', UNSAFE_SVG, content_type='image/svg+xml')
            settings_obj.custom_svg = SimpleUploadedFile('icon.svg', UNSAFE_SVG, content_type='image/svg+xml')
            settings_obj.full_clean()
            settings_obj.save()
            settings_obj.refresh_from_db()

            for markup in (
                settings_obj.desktop_svg_markup,
                settings_obj.mobile_svg_markup,
                settings_obj.custom_svg_markup,
            ):
                self.assertIn('<path', markup)
                self.assertIn('currentColor', markup)
                self.assertNotIn('script', markup)
                self.assertNotIn('onload', markup)
                self.assertNotIn('onclick', markup)

            settings_obj.desktop_custom_svg = ''
            settings_obj.mobile_custom_svg = ''
            settings_obj.custom_svg = ''
            settings_obj.save()
            settings_obj.refresh_from_db()
            self.assertEqual(settings_obj.desktop_svg_markup, '')
            self.assertEqual(settings_obj.mobile_svg_markup, '')
            self.assertEqual(settings_obj.custom_svg_markup, '')
        finally:
            appearance_svg_storage.location = original_appearance_location
            whatsapp_svg_storage.location = original_whatsapp_location
            appearance_root.cleanup()
            whatsapp_root.cleanup()

    def test_validator_rejects_invalid_svg(self):
        upload = SimpleUploadedFile('invalid.svg', b'<p>not an svg</p>', content_type='image/svg+xml')
        with self.assertRaises(ValidationError):
            validate_svg_upload(upload)

    def test_sanitizer_rewrites_colors_and_keeps_safe_shapes(self):
        markup = sanitize_svg(
            '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" fill="#ff0000" stroke="blue"/></svg>'
        )
        self.assertIn('viewBox="0 0 24 24"', markup)
        self.assertIn('r="10"', markup)
        self.assertIn('fill="currentColor"', markup)
        self.assertIn('stroke="currentColor"', markup)

    def test_validators(self):
        with self.assertRaises(ValidationError):
            validate_hex_color('red')
        with self.assertRaises(ValidationError):
            validate_whatsapp_phone('123')
        validate_hex_color('#AABBCC')
        validate_whatsapp_phone('+91 99999 99999')


class AppearanceContextTests(TestCase):
    def test_multi_theme_defaults_allow_switching(self):
        context = footer_links(RequestFactory().get('/'))
        appearance = context['appearance']
        self.assertTrue(appearance['can_switch'])
        self.assertIsNone(appearance['forced_theme'])
        self.assertEqual(appearance['available_themes'], ['dark', 'light'])
        self.assertEqual(appearance['preference_token'], 'keep')
        self.assertEqual(appearance['default_theme'], 'dark')
        self.assertTrue(appearance['desktop']['enabled'])
        self.assertTrue(appearance['mobile']['enabled'])

    def test_single_theme_forces_default_and_removes_switchers(self):
        settings_obj = AppearanceSettings.load()
        settings_obj.theme_mode = 'single'
        settings_obj.default_theme = 'light'
        settings_obj.save()

        context = footer_links(RequestFactory().get('/'))
        appearance = context['appearance']
        self.assertFalse(appearance['can_switch'])
        self.assertEqual(appearance['forced_theme'], 'light')
        self.assertFalse(appearance['desktop']['enabled'])
        self.assertFalse(appearance['mobile']['enabled'])

        html = nav_html(self.client.get('/'))
        self.assertNotIn('id="themePullToggle"', html)
        self.assertNotIn('appearance-mobile-switcher', html)

    def test_disabling_themes_or_switching_removes_switchers(self):
        settings_obj = AppearanceSettings.load()
        settings_obj.light_theme_enabled = False
        settings_obj.save()
        context = footer_links(RequestFactory().get('/'))
        self.assertFalse(context['appearance']['can_switch'])
        self.assertEqual(context['appearance']['available_themes'], ['dark'])
        self.assertEqual(context['appearance']['forced_theme'], 'dark')

        settings_obj.light_theme_enabled = True
        settings_obj.allow_visitor_switching = False
        settings_obj.save()
        self.assertFalse(footer_links(RequestFactory().get('/'))['appearance']['can_switch'])

        settings_obj.allow_visitor_switching = True
        settings_obj.show_theme_switchers = False
        settings_obj.save()
        self.assertFalse(footer_links(RequestFactory().get('/'))['appearance']['can_switch'])

        settings_obj.show_theme_switchers = True
        settings_obj.desktop_enabled = False
        settings_obj.mobile_enabled = False
        settings_obj.save()
        html = nav_html(self.client.get('/'))
        self.assertNotIn('id="themePullToggle"', html)
        self.assertNotIn('appearance-mobile-switcher', html)

    def test_follow_policy_token_changes_with_default(self):
        settings_obj = AppearanceSettings.load()
        settings_obj.preference_policy = 'follow'
        settings_obj.save()
        first = footer_links(RequestFactory().get('/'))['appearance']['preference_token']
        settings_obj.default_theme = 'light'
        settings_obj.save()
        second = footer_links(RequestFactory().get('/'))['appearance']['preference_token']
        self.assertNotEqual(first, 'keep')
        self.assertNotEqual(first, second)

    def test_whatsapp_url_uses_admin_phone_and_message(self):
        settings_obj = AppearanceSettings.load()
        settings_obj.phone_number = '+1 555 123 4567'
        settings_obj.default_message = 'Hello there!'
        settings_obj.save()
        context = footer_links(RequestFactory().get('/'))
        self.assertEqual(context['whatsapp_url'], 'https://wa.me/15551234567?text=Hello+there%21')
        self.assertTrue(context['whatsapp_number_configured'])

    def test_whatsapp_url_falls_back_to_footer_social_link(self):
        FooterSettings.load()
        AppearanceSettings.load()
        FooterSettings.objects.filter(pk=1).update(whatsapp_url='https://wa.me/447700900999')
        AppearanceSettings.objects.filter(pk=1).update(phone_number='')
        context = footer_links(RequestFactory().get('/'))
        self.assertEqual(context['whatsapp_url'], 'https://wa.me/447700900999')


class AppearanceFrontendTests(TestCase):
    def test_config_and_dynamic_colors_render(self):
        settings_obj = AppearanceSettings.load()
        settings_obj.dark_bg_primary = '#111111'
        settings_obj.dark_accent_color = '#222222'
        settings_obj.light_footer_bg = '#333333'
        settings_obj.global_border_radius = 20
        settings_obj.global_accent_color = '#444444'
        settings_obj.save()

        response = self.client.get('/')
        self.assertContains(response, '"canSwitch": true')
        self.assertContains(response, '"defaultTheme": "dark"')
        self.assertContains(response, '--bg-primary: #111111')
        self.assertContains(response, '--accent: #222222')
        self.assertContains(response, '--footer-bg: #333333')
        self.assertContains(response, '--global-radius: 20px')
        self.assertContains(response, '--global-accent: #444444')
        self.assertContains(response, 'id="site-footer"')

    def test_default_switchers_render(self):
        html = nav_html(self.client.get('/'))
        self.assertIn('id="themePullToggle"', html)
        self.assertIn('appearance-mobile-switcher', html)
        self.assertNotIn('appearance-mobile-tooltip-enabled', html)

    def test_switcher_custom_values_render(self):
        settings_obj = AppearanceSettings.load()
        settings_obj.desktop_background_enabled = True
        settings_obj.desktop_background_color = '#101010'
        settings_obj.desktop_icon_color = '#202020'
        settings_obj.desktop_icon_size = 14
        settings_obj.desktop_button_size = 64
        settings_obj.desktop_border_radius = 24
        settings_obj.desktop_position = 'bottom-left'
        settings_obj.desktop_tooltip_text = 'Desktop tooltip'
        settings_obj.desktop_hover_effects = False
        settings_obj.desktop_transition = False
        settings_obj.mobile_background_enabled = True
        settings_obj.mobile_background_color = '#303030'
        settings_obj.mobile_icon_color = '#404040'
        settings_obj.mobile_icon_size = 28
        settings_obj.mobile_button_size = 52
        settings_obj.mobile_border_radius = 16
        settings_obj.mobile_position = 'bottom-right'
        settings_obj.mobile_tooltip_enabled = True
        settings_obj.mobile_tooltip_text = 'Mobile tooltip'
        settings_obj.mobile_hover_effects = False
        settings_obj.mobile_transition = False
        settings_obj.save()

        response = self.client.get('/')
        self.assertContains(response, '--desktop-bg: #101010')
        self.assertContains(response, '--desktop-icon-color: #202020')
        self.assertContains(response, '--desktop-icon-size: 14px')
        self.assertContains(response, '--desktop-button-size: 64')
        self.assertContains(response, '--desktop-radius: 24px')
        self.assertContains(response, '--mobile-icon-size: 28px')
        self.assertContains(response, '--mobile-button-size: 52px')
        html = nav_html(response)
        self.assertIn('theme-pull-slot--bottom-left', html)
        self.assertIn('appearance-desktop-custom-bg', html)
        self.assertIn('appearance-desktop-no-hover', html)
        self.assertIn('appearance-desktop-no-transition', html)
        self.assertIn('Desktop tooltip', html)
        self.assertIn('appearance-mobile-bottom-right', html)
        self.assertIn('appearance-mobile-custom-bg', html)
        self.assertIn('appearance-mobile-tooltip-enabled', html)
        self.assertIn('appearance-mobile-no-hover', html)
        self.assertIn('Mobile tooltip', html)

    def test_navbar_transparency_is_desktop_only(self):
        html = self.client.get('/').content.decode()
        before_media, media_block = html.split('@media (min-width: 1280px) {', 1)
        media_block = media_block.split('\n  }', 1)[0]

        self.assertNotIn('#themehub-navbar { background-color', before_media)
        self.assertIn('#themehub-navbar { background-color: transparent !important; }', media_block)
        self.assertIn(
            '[data-theme] #themehub-navbar.is-scrolled { background-color: var(--header-bg) !important; }',
            media_block,
        )

    def test_footer_anchors_use_theme_text_color(self):
        html = self.client.get('/').content.decode()
        self.assertIn('#site-footer a * { color: var(--text-primary) !important; }', html)
        self.assertNotIn('main a:not(.btn), #site-footer a:not(.btn) { color: var(--link-color); }', html)

    def test_home_product_cards_have_no_background_shadow(self):
        source = get_template('products/partials/card.html').template.source
        self.assertNotIn('shadow-[var(--shadow-card)]', source)
        self.assertNotIn('hover:shadow-[', source)

    def test_global_ui_classes_and_font_render(self):
        settings_obj = AppearanceSettings.load()
        settings_obj.global_animations_enabled = False
        settings_obj.global_hover_enabled = False
        settings_obj.global_transitions_enabled = False
        settings_obj.switch_behavior = 'instant'
        settings_obj.font_family = 'inter'
        settings_obj.global_button_style = 'pill'
        settings_obj.save()

        response = self.client.get('/')
        self.assertContains(response, 'appearance-no-animation appearance-no-hover appearance-no-transition appearance-instant-theme')
        self.assertContains(response, 'family=Inter')
        self.assertContains(response, '--global-button-radius: 999px')

    def test_custom_svg_markup_rendered_for_all_buttons(self):
        AppearanceSettings.load()
        AppearanceSettings.objects.filter(pk=1).update(
            desktop_svg_markup='<svg><path d="MDESKTOP"/></svg>',
            mobile_svg_markup='<svg><path d="MMOBILE"/></svg>',
            custom_svg_markup='<svg><path d="MWHATSAPP"/></svg>',
        )
        html = self.client.get('/').content.decode()
        self.assertIn('d="MDESKTOP"', html)
        self.assertIn('d="MMOBILE"', html)
        self.assertIn('d="MWHATSAPP"', html)

    def test_whatsapp_button_configured_values_render(self):
        settings_obj = AppearanceSettings.load()
        settings_obj.phone_number = '+919999999999'
        settings_obj.background_color = '#123456'
        settings_obj.icon_color = '#abcdef'
        settings_obj.button_size = 80
        settings_obj.icon_size = 40
        settings_obj.border_radius = 18
        settings_obj.position = 'bottom-left'
        settings_obj.horizontal_offset = 25
        settings_obj.vertical_offset = 30
        settings_obj.z_index = 99
        settings_obj.tooltip_text = 'Ping us'
        settings_obj.animation = 'pulse'
        settings_obj.save()

        response = self.client.get('/')
        self.assertContains(response, 'https://wa.me/919999999999')
        self.assertContains(response, '--wa-background: #123456')
        self.assertContains(response, '--wa-icon-color: #abcdef')
        self.assertContains(response, '--wa-button-size: 80px')
        self.assertContains(response, '--wa-icon-size: 40px')
        self.assertContains(response, '--wa-border-radius: 18px')
        self.assertContains(response, '--wa-offset-x: 25px')
        self.assertContains(response, '--wa-offset-y: 30px')
        self.assertContains(response, '--wa-z-index: 99')
        self.assertContains(response, 'whatsapp-float--bottom-left')
        self.assertContains(response, 'whatsapp-float--animation-pulse')
        self.assertContains(response, 'Ping us')

    def test_disabled_whatsapp_button_is_not_rendered(self):
        settings_obj = AppearanceSettings.load()
        settings_obj.whatsapp_enabled = False
        settings_obj.save()
        self.assertNotContains(self.client.get('/'), 'class="whatsapp-float')

    def test_whatsapp_device_visibility_and_tooltip(self):
        settings_obj = AppearanceSettings.load()
        settings_obj.show_on_mobile = False
        settings_obj.tooltip_enabled = False
        settings_obj.save()
        html = self.client.get('/').content.decode()
        self.assertIn('whatsapp-float--hide-mobile', html)
        self.assertNotIn('whatsapp-float__tooltip', html.split('</style>')[-1])


class AppearanceAdminTests(TestCase):
    def test_admin_branding(self):
        response = self.client.get('/admin/login/')
        self.assertContains(response, 'themehaven.in')
        self.assertNotContains(response, 'Django administration')

    def test_admin_only_allows_one_record(self):
        settings_obj = AppearanceSettings.load()
        model_admin = AppearanceSettingsAdmin(AppearanceSettings, admin.site)
        request = RequestFactory().get('/admin/')
        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_delete_permission(request, settings_obj))

    def test_admin_fieldsets(self):
        AppearanceSettings.load()
        user = get_user_model().objects.create_superuser('admin', 'admin@example.com', 'password')
        self.client.force_login(user)
        response = self.client.get(reverse('admin:core_appearancesettings_change', args=[1]))
        self.assertEqual(response.status_code, 200)
        for heading in (
            'General Appearance',
            'Theme Mode',
            'Default Theme',
            'Dark Theme Colors',
            'Light Theme Colors',
            'Desktop Theme Switcher',
            'Mobile Theme Switcher',
            'WhatsApp Floating Button',
            'Global UI Settings',
        ):
            self.assertContains(response, heading)
        html = response.content.decode()
        self.assertRegex(html, r'<details>\s*<summary>\s*<h2[^>]*>Dark Theme Colors</h2>\s*</summary>')
        self.assertRegex(html, r'<details>\s*<summary>\s*<h2[^>]*>Light Theme Colors</h2>\s*</summary>')
        self.assertNotRegex(html, r'<details[^>]*\bopen\b')

    def test_color_fieldsets_are_collapsed_by_default(self):
        options = dict(AppearanceSettingsAdmin.fieldsets)
        for heading in ('Dark Theme Colors', 'Light Theme Colors'):
            self.assertIn('collapse', options[heading].get('classes', ()))
        for heading in (
            'General Appearance',
            'Theme Mode',
            'Default Theme',
            'Desktop Theme Switcher',
            'Mobile Theme Switcher',
            'WhatsApp Floating Button',
            'Global UI Settings',
        ):
            self.assertNotIn('collapse', options[heading].get('classes', ()))

    def test_admin_save_updates_frontend(self):
        appearance_root = tempfile.TemporaryDirectory()
        whatsapp_root = tempfile.TemporaryDirectory()
        original_appearance_location = appearance_svg_storage.location
        original_whatsapp_location = whatsapp_svg_storage.location
        appearance_svg_storage.location = appearance_root.name
        whatsapp_svg_storage.location = whatsapp_root.name
        try:
            settings_obj = AppearanceSettings.load()
            user = get_user_model().objects.create_superuser('admin', 'admin@example.com', 'password')
            self.client.force_login(user)
            data = admin_post_data(settings_obj)
            data.update({
                'theme_mode': 'multi',
                'default_theme': 'light',
                'dark_bg_primary': '#654321',
                'desktop_tooltip_text': 'Admin desktop tooltip',
                'phone_number': '+1 222 333 4444',
                'default_message': 'Admin message',
                'background_color': '#123123',
                'desktop_custom_svg': SimpleUploadedFile('icon.svg', UNSAFE_SVG, content_type='image/svg+xml'),
                'custom_svg': SimpleUploadedFile('icon.svg', UNSAFE_SVG, content_type='image/svg+xml'),
            })
            response = self.client.post(
                reverse('admin:core_appearancesettings_change', args=[1]), data
            )
            self.assertEqual(response.status_code, 302)

            settings_obj = AppearanceSettings.objects.get(pk=1)
            self.assertEqual(settings_obj.default_theme, 'light')
            self.assertEqual(settings_obj.phone_number, '+1 222 333 4444')
            self.assertIn('currentColor', settings_obj.desktop_svg_markup)
            self.assertNotIn('onclick', settings_obj.custom_svg_markup)

            html = self.client.get('/').content.decode()
            self.assertIn('"defaultTheme": "light"', html)
            self.assertIn('--bg-primary: #654321', html)
            self.assertIn('Admin desktop tooltip', html)
            self.assertIn('https://wa.me/12223334444?text=Admin+message', html)
            self.assertIn('--wa-background: #123123', html)
        finally:
            appearance_svg_storage.location = original_appearance_location
            whatsapp_svg_storage.location = original_whatsapp_location
            appearance_root.cleanup()
            whatsapp_root.cleanup()
