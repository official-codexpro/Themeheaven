from pathlib import Path
import re

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


STATIC_ROOT = Path(__file__).resolve().parent.parent / 'static'


class AdminUiSmokeTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser('ui-admin', 'ui@example.com', 'password')
        self.client.force_login(self.user)

    def page_names(self):
        names = [
            'admin:index',
            'admin:system-settings-index',
            'admin:growth-center-analytics',
            'admin:growth-center-campaigns',
            'admin:growth-center-social',
            'admin:growth-center-content',
            'admin:growth-center-conversion',
            'admin:growth-center-seo-settings',
            'admin:growth-center-page-seo',
            'admin:growth-center-campaign-create',
            'admin:growth-center-social-post-create',
            'admin:growth-center-content-create',
            'admin:growth-center-conversion-goal-create',
            'admin:growth-center-conversion-funnel-create',
            'admin:growth-center-conversion-rule-create',
            'admin:growth-center-conversion-cost-create',
        ]
        for model, model_admin in admin.site._registry.items():
            if model_admin:
                names.append(f'admin:{model._meta.app_label}_{model._meta.model_name}_changelist')
        return names

    def test_admin_pages_render_with_shared_ui_stylesheet(self):
        for name in self.page_names():
            with self.subTest(name=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)
                self.assertIn('css/admin_ui.css', response.content.decode())

    def test_system_settings_pages_render_with_shared_ui_stylesheet(self):
        for slug in ('email', 'system'):
            with self.subTest(slug=slug):
                response = self.client.get(reverse('admin:system-settings-category', args=[slug]))
                self.assertEqual(response.status_code, 200)
                self.assertIn('css/admin_ui.css', response.content.decode())

    def test_conversion_page_uses_shared_kpi_vocabulary(self):
        html = self.client.get(reverse('admin:growth-center-conversion')).content.decode()
        self.assertIn('gc-kpi-grid', html)
        self.assertIn('gc-kpi', html)
        self.assertNotIn('gcm-kpi-grid gct-kpi-grid', html)

    def test_campaign_toolbar_uses_logical_control_groups(self):
        html = self.client.get(reverse('admin:growth-center-campaigns')).content.decode()
        self.assertEqual(len(re.findall(r'class="gc-control-group ', html)), 4)
        self.assertIn('gc-control-group--dates', html)
        self.assertIn('gc-control-group--filters', html)
        self.assertIn('gc-control-group--display', html)
        self.assertIn('gc-control-group--actions', html)
        self.assertIn('gccamp-refresh', html)

    def test_admin_shell_has_no_inline_layout_styles(self):
        for url in ('admin:index', 'admin:system-settings-index'):
            with self.subTest(url=url):
                html = self.client.get(reverse(url)).content.decode()
                self.assertIsNone(re.search(r'style="[^"]*(?:border-left|width\s*:\s*100%)', html))

    def test_shared_css_primitives_are_defined(self):
        css = (STATIC_ROOT / 'css' / 'admin_ui.css').read_text()
        self.assertIsNotNone(re.search(r'\.admin-table-wrap\s*\{', css))
        self.assertIsNotNone(re.search(r'overflow-x\s*:\s*auto', css))
        self.assertIsNotNone(re.search(r'flex-wrap\s*:\s*wrap', css))
        self.assertIsNotNone(re.search(r'@media\s*\(max-width\s*:\s*480px\)', css))

    def test_module_css_defects_are_resolved(self):
        conversion = (STATIC_ROOT / 'css' / 'growth_conversion.css').read_text()
        social = (STATIC_ROOT / 'css' / 'growth_social_media.css').read_text()
        campaigns = (STATIC_ROOT / 'css' / 'growth_campaigns.css').read_text()

        self.assertIsNotNone(re.search(r'\.gct-kpi-grid\s*\{', conversion))
        self.assertIsNotNone(re.search(r'\.gct-kpi(?:,|\s*\{)', conversion))
        self.assertIsNotNone(re.search(r'max-height\s*:\s*calc\(100dvh\s*-\s*32px\)', social))
        self.assertIsNotNone(re.search(r'\.gccamp-editor-shell', campaigns))
        self.assertIsNotNone(re.search(r'flex-wrap\s*:\s*wrap', campaigns))
