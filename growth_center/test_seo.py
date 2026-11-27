import tempfile
import xml.etree.ElementTree as ET

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from growth_center.forms import SEOSettingsForm
from growth_center.models import AnalyticsSession, PageView, SEOSettings, Visitor
from growth_center.seo import build_canonical_url, build_seo_context
from growth_center.seo_health import seo_health_summary
from growth_center.seo_settings import clear_seo_settings_cache, get_seo_settings
from growth_center.validators import SAFE_ROBOTS_TXT, make_test_image


class SEOSettingsTests(TestCase):
    def setUp(self):
        clear_seo_settings_cache()

    def tearDown(self):
        clear_seo_settings_cache()

    def update_settings(self, **fields):
        instance = get_seo_settings()
        for key, value in fields.items():
            setattr(instance, key, value)
        instance.save()
        clear_seo_settings_cache()
        return instance

    def test_singleton_safe_defaults(self):
        first = SEOSettings.load()
        second = SEOSettings.load()
        self.assertEqual(first.pk, 1)
        self.assertEqual(second.pk, 1)
        self.assertTrue(first.index_enabled)
        self.assertTrue(first.follow_enabled)
        self.assertTrue(first.sitemap_enabled)
        self.assertIn('Allow: /', first.robots_txt_content)

    def test_form_validates_domain_token_and_robots(self):
        instance = get_seo_settings()
        bad_domain = SEOSettingsForm(instance=instance, data={
            'primary_domain': 'https://example.com/path',
            'robots_txt_content': SAFE_ROBOTS_TXT,
        })
        self.assertFalse(bad_domain.is_valid())

        bad_token = SEOSettingsForm(instance=instance, data={
            'primary_domain': 'example.com',
            'google_verification_token': '<script>alert(1)</script>',
            'robots_txt_content': SAFE_ROBOTS_TXT,
        })
        self.assertFalse(bad_token.is_valid())

        dangerous_robots = SEOSettingsForm(instance=instance, data={
            'primary_domain': 'example.com',
            'robots_txt_content': 'User-agent: *\nDisallow: /',
        })
        self.assertFalse(dangerous_robots.is_valid())

        valid = SEOSettingsForm(instance=instance, data={
            'seo_title': 'ThemeHaven — Premium Digital Products',
            'meta_description': 'A' * 130,
            'site_name': 'ThemeHaven',
            'meta_keywords': '',
            'primary_domain': 'https://www.example.com',
            'preferred_www': 'without',
            'canonical_behavior': 'auto',
            'trailing_slash_behavior': 'preserve',
            'google_verification_token': '<meta name="google-site-verification" content="abcDEF123_-456" />',
            'robots_txt_content': SAFE_ROBOTS_TXT,
        })
        self.assertTrue(valid.is_valid(), valid.errors)
        self.assertEqual(valid.cleaned_data['primary_domain'], 'www.example.com')
        self.assertEqual(valid.cleaned_data['google_verification_token'], 'abcDEF123_-456')

    @override_settings(MEDIA_ROOT=tempfile.mkdtemp())
    def test_default_image_upload_and_public_url(self):
        upload = SimpleUploadedFile('share.png', make_test_image(), content_type='image/png')
        form = SEOSettingsForm(
            instance=get_seo_settings(),
            data={
                'primary_domain': 'example.com',
                'prefer_https': 'on',
                'preferred_www': 'auto',
                'canonical_behavior': 'auto',
                'trailing_slash_behavior': 'preserve',
                'robots_txt_content': SAFE_ROBOTS_TXT,
            },
            files={'default_image': upload},
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        request = RequestFactory().get('/')
        context = build_seo_context(request)
        self.assertTrue(context['image'].endswith(form.instance.default_image.url))
        self.assertIn('https://example.com/media/seo/', context['image'])

    def test_canonical_url_service(self):
        instance = self.update_settings(
            primary_domain='www.example.com',
            prefer_https=True,
            preferred_www='without',
            trailing_slash_behavior='strip_slash',
        )
        request = RequestFactory().get('/support/', HTTP_HOST='untrusted.invalid')
        self.assertEqual(build_canonical_url(request, instance=instance), 'https://example.com/support')

        request = RequestFactory().get('/admin/', HTTP_HOST='testserver')
        self.assertEqual(build_canonical_url(request, instance=instance), '')

    @override_settings(DEBUG=False)
    def test_public_metadata_is_injected_without_duplicates(self):
        self.update_settings(
            seo_title='Global SEO Title',
            meta_description='Global description for the website.',
            meta_keywords='themes, dashboards',
            site_name='ThemeHaven Global',
            google_verification_token='abcDEF123_-456',
            follow_enabled=False,
        )
        response = self.client.get('/')
        html = response.content.decode()

        self.assertContains(response, 'Global SEO Title')
        self.assertContains(response, 'Global description for the website.')
        self.assertContains(response, 'themes, dashboards')
        self.assertContains(response, 'name="google-site-verification" content="abcDEF123_-456"')
        self.assertContains(response, 'content="index, nofollow"')
        self.assertEqual(html.count('name="description"'), 1)
        self.assertEqual(html.count('rel="canonical"'), 1)
        self.assertEqual(html.count('google-site-verification'), 1)

        admin_response = self.client.get(reverse('admin:login'))
        self.assertNotContains(admin_response, 'google-site-verification')

        missing = self.client.get('/definitely-missing-page/')
        self.assertNotIn('rel="canonical"', missing.content.decode())

    def test_robots_endpoint(self):
        self.update_settings(
            primary_domain='example.com',
            robots_txt_enabled=True,
            robots_txt_content='User-agent: *\nAllow: /\nDisallow: /admin/\n',
            sitemap_enabled=True,
        )
        response = self.client.get('/robots.txt')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['Content-Type'].startswith('text/plain'))
        self.assertContains(response, 'User-agent: *')
        self.assertContains(response, 'Disallow: /admin/')
        self.assertContains(response, 'Sitemap: https://example.com/sitemap.xml')
        self.assertNotContains(response, 'Disallow: /static/')

    def test_sitemap_endpoint(self):
        instance = self.update_settings(primary_domain='example.com', sitemap_enabled=True)
        response = self.client.get('/sitemap.xml')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['Content-Type'].startswith('application/xml'))

        root = ET.fromstring(response.content)
        namespace = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        locations = [node.text for node in root.findall('.//s:loc', namespace)]
        self.assertIn('https://example.com/', locations)
        self.assertIn('https://example.com/support/', locations)
        self.assertNotIn('https://example.com/admin/', locations)
        self.assertNotIn('https://example.com/products/preview/wordpress/1/', locations)
        self.assertEqual(len(locations), len(set(locations)))

        instance.sitemap_enabled = False
        instance.save()
        clear_seo_settings_cache()
        disabled = self.client.get('/sitemap.xml')
        disabled_root = ET.fromstring(disabled.content)
        self.assertEqual(disabled_root.findall('.//s:loc', namespace), [])

    def test_health_summary_reflects_real_settings(self):
        self.update_settings(
            seo_title='A' * 45,
            meta_description='B' * 140,
            primary_domain='example.com',
            google_verification_token='abcDEF123_-456',
        )
        health = seo_health_summary()
        statuses = {check['label']: check['status'] for check in health['checks']}
        self.assertEqual(statuses['SEO title configured'], 'configured')
        self.assertEqual(statuses['Meta description configured'], 'configured')
        self.assertEqual(statuses['Canonical URL configuration valid'], 'configured')
        self.assertEqual(statuses['Search Console verification configured'], 'configured')
        self.assertEqual(statuses['Default social image configured'], 'missing')
        self.assertGreater(health['readiness_percent'], 0)
        self.assertIn('not a ranking score', health['readiness_label'])


class SEODashboardTests(TestCase):
    def setUp(self):
        clear_seo_settings_cache()
        self.user = get_user_model().objects.create_superuser(
            username='seoadmin',
            email='seo@example.com',
            password='pass12345',
        )
        self.url = reverse('admin:growth-center-seo-settings')

    def tearDown(self):
        clear_seo_settings_cache()

    def test_sidebar_has_both_growth_center_items_in_order(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        html = response.content.decode()
        analytics = html.count('href="/admin/growth-center/analytics/"')
        seo = html.count('href="/admin/growth-center/seo-settings/"')
        self.assertGreaterEqual(analytics, 1)
        self.assertEqual(seo, 1)
        self.assertLess(html.index('/admin/growth-center/analytics/'), html.index('/admin/growth-center/seo-settings/'))
        self.assertContains(response, 'GROWTH CENTER')

    def test_requires_staff_access(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response.url)

    def test_save_and_persist_settings(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, {
            'seo_title': 'Saved SEO Title',
            'meta_description': 'Saved description.',
            'site_name': 'ThemeHaven',
            'meta_keywords': '',
            'primary_domain': 'example.com',
            'prefer_https': 'on',
            'preferred_www': 'auto',
            'canonical_behavior': 'auto',
            'trailing_slash_behavior': 'preserve',
            'sitemap_enabled': 'on',
            'robots_txt_enabled': 'on',
            'robots_txt_content': SAFE_ROBOTS_TXT,
            'google_verification_token': '',
        })
        self.assertEqual(response.status_code, 302)
        instance = get_seo_settings()
        self.assertEqual(instance.seo_title, 'Saved SEO Title')
        self.assertEqual(instance.primary_domain, 'example.com')

        refreshed = self.client.get(self.url)
        self.assertContains(refreshed, 'Saved SEO Title')

    def test_reset_keeps_analytics_and_other_data(self):
        visitor = Visitor.objects.create(visitor_key='seo-reset-check')
        session = AnalyticsSession.objects.create(session_key='seo-reset-check', visitor=visitor)
        PageView.objects.create(session=session, visitor=visitor, path='/')

        self.client.force_login(self.user)
        response = self.client.post(self.url, {'reset': '1'})
        self.assertEqual(response.status_code, 302)
        instance = get_seo_settings()
        self.assertEqual(instance.seo_title, '')
        self.assertEqual(instance.robots_txt_content, SAFE_ROBOTS_TXT)
        self.assertTrue(AnalyticsSession.objects.filter(session_key='seo-reset-check').exists())
        self.assertTrue(PageView.objects.filter(path='/').exists())
