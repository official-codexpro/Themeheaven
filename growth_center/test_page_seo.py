import tempfile
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase, override_settings
from django.urls import path, reverse
from unittest.mock import patch

from core.views import POLICIES
from growth_center.forms import PageSEOForm
from growth_center.models import PageSEO
from growth_center.page_registry import (
    ManagedPage,
    discover_pages,
    get_managed_page,
    get_managed_page_by_path,
)
from growth_center.page_seo import (
    build_page_seo_context,
    is_page_indexable,
    page_seo_status,
)
from growth_center.page_seo_cache import clear_page_seo_cache
from growth_center.seo import build_seo_context
from growth_center.seo_settings import clear_seo_settings_cache, get_seo_settings
from growth_center.validators import (
    is_valid_canonical_url,
    make_test_image,
    sanitize_jsonld,
    validate_jsonld,
)
from growth_center.views import page_seo_dashboard, page_seo_editor


class PageSEORegistryTests(TestCase):
    def test_discovers_only_supported_public_pages(self):
        pages = discover_pages()
        keys = {page.key for page in pages}
        paths = {page.path for page in pages}

        self.assertIn('home', keys)
        self.assertIn('support', keys)
        self.assertIn('policy:privacy-policy', keys)
        self.assertIn('policy:shipping-delivery-policy', keys)
        self.assertIn('/', paths)
        self.assertIn('/support/', paths)
        self.assertIn('/privacy-policy/', paths)
        self.assertNotIn('/admin/', paths)
        self.assertNotIn('/products/wordpress/', paths)
        self.assertNotIn('/products/excel/', paths)
        self.assertNotIn('/products/preview/wordpress/1/', paths)

    def test_lookup_uses_stable_keys_and_normalizes_paths(self):
        self.assertEqual(get_managed_page('home').path, '/')
        self.assertIsNone(get_managed_page('admin'))
        self.assertIsNone(get_managed_page('/admin/'))

        page = get_managed_page_by_path('/support')
        self.assertIsNotNone(page)
        self.assertEqual(page.key, 'support')
        self.assertIsNone(get_managed_page_by_path('/admin/'))
        self.assertIsNone(get_managed_page_by_path('/this-page-does-not-exist/'))

    def test_policy_titles_come_from_real_views(self):
        page = get_managed_page('policy:privacy-policy')
        self.assertIsNotNone(page)
        self.assertEqual(page.title, POLICIES['privacy-policy']['title'])
        self.assertEqual(page.path, '/privacy-policy/')

    def test_discovers_new_static_route_without_manual_registration(self):
        fake_resolver = SimpleNamespace(url_patterns=[
            path('admin/', lambda request: None),
            path('api/status/', lambda request: None),
            path('support/', lambda request: None, name='support'),
            path('new-seo-page/', lambda request: None, name='new_seo_page'),
            path('products/<slug:slug>/', lambda request: None),
        ])

        with patch('growth_center.page_registry.get_resolver', return_value=fake_resolver):
            pages = discover_pages()

        paths = {page.path for page in pages}

        self.assertIn('/new-seo-page/', paths)
        self.assertNotIn('/admin/', paths)
        self.assertNotIn('/api/status/', paths)
        self.assertNotIn('/products/<slug:slug>/', paths)
        self.assertEqual(len([item for item in pages if item.path == '/support/']), 1)
        self.assertEqual([item.key for item in pages if item.path == '/support/'], ['support'])

        discovered = next(item for item in pages if item.path == '/new-seo-page/')
        self.assertEqual(discovered.key, 'url:/new-seo-page')
        self.assertEqual(discovered.title, 'New Seo Page')
        self.assertEqual(discovered.source, 'route')


class PageSEOValidatorTests(TestCase):
    def test_canonical_url_validation(self):
        self.assertTrue(is_valid_canonical_url(''))
        self.assertTrue(is_valid_canonical_url('https://example.com/page/'))
        self.assertFalse(is_valid_canonical_url('javascript:alert(1)'))
        self.assertFalse(is_valid_canonical_url('https://user:pass@example.com/'))
        self.assertFalse(is_valid_canonical_url('https://example.com/?a=1'))
        self.assertFalse(is_valid_canonical_url('https://example.com/page#top'))

    def test_jsonld_validation_and_sanitization(self):
        self.assertEqual(validate_jsonld('   '), '')
        with self.assertRaises(Exception):
            validate_jsonld('{bad json}')
        with self.assertRaises(Exception):
            validate_jsonld('"text only"')

        cleaned = sanitize_jsonld('{"name":"<script>alert(1)</script>"}')
        self.assertNotIn('<script>', cleaned)
        self.assertIn('\\u003cscript\\u003e', cleaned)


class PageSEOContextTests(TestCase):
    def setUp(self):
        clear_seo_settings_cache()
        cache.clear()

    def tearDown(self):
        clear_seo_settings_cache()
        cache.clear()

    def update_settings(self, **fields):
        instance = get_seo_settings()
        for key, value in fields.items():
            setattr(instance, key, value)
        instance.save()
        clear_seo_settings_cache()
        return instance

    def test_custom_page_metadata_overrides_page_and_global_defaults(self):
        self.update_settings(
            primary_domain='example.com',
            seo_title='Global SEO Title',
            meta_description='Global description.',
        )
        PageSEO.objects.create(
            page_key='support',
            seo_title='Custom Support SEO Title',
            meta_description='D' * 130,
            canonical_override='https://example.com/custom-support/',
            index_mode='noindex',
            follow_mode='nofollow',
            schema_mode='generated',
            schema_type='webpage',
        )

        request = RequestFactory().get('/support/', HTTP_HOST='evil.invalid')
        context = build_seo_context(request)

        self.assertEqual(context['title'], 'Custom Support SEO Title')
        self.assertEqual(context['description'], 'D' * 130)
        self.assertEqual(context['canonical_url'], 'https://example.com/custom-support/')
        self.assertEqual(context['robots'], 'noindex, nofollow')
        self.assertEqual(context['canonical_source'], 'custom')
        self.assertEqual(context['index_source'], 'noindex')
        self.assertEqual(context['follow_source'], 'nofollow')
        self.assertIn('"@type":"WebPage"', context['schema_json'])
        self.assertEqual(context['schema_json'].count('<'), 0)

    def test_page_defaults_are_used_before_global_defaults(self):
        self.update_settings(
            primary_domain='example.com',
            seo_title='Global SEO Title',
            meta_description='Global description that is long enough to be used as a fallback description.',
        )
        request = RequestFactory().get('/support/', HTTP_HOST='evil.invalid')
        context = build_seo_context(request)

        self.assertEqual(context['title_source'], 'page')
        self.assertEqual(context['title'], 'Support — ThemeHaven')
        self.assertEqual(context['description_source'], 'page')
        self.assertEqual(
            context['description'],
            'Browse the available themes and templates from the homepage. Support contact details have not been configured for this project yet.',
        )
        self.assertEqual(context['robots'], 'index, follow')

    def test_global_robots_are_inherited_without_a_page_record(self):
        self.update_settings(primary_domain='example.com', index_enabled=False, follow_enabled=False)
        request = RequestFactory().get('/support/')

        context = build_seo_context(request)
        self.assertEqual(context['robots'], 'noindex, nofollow')
        self.assertFalse(is_page_indexable(get_managed_page('support')))

    def test_explicit_page_index_can_override_inherited_noindex(self):
        self.update_settings(primary_domain='example.com', index_enabled=False, follow_enabled=True)
        PageSEO.objects.create(page_key='support', index_mode='index')
        request = RequestFactory().get('/support/')

        context = build_seo_context(request)
        self.assertEqual(context['robots'], 'index, follow')

    def test_custom_jsonld_is_sanitized(self):
        self.update_settings(primary_domain='example.com')
        PageSEO.objects.create(
            page_key='home',
            schema_mode='custom',
            schema_json='{"name":"<img src=x onerror=alert(1)>"}',
        )
        request = RequestFactory().get('/')

        context = build_seo_context(request)
        self.assertNotIn('<img', context['schema_json'])
        self.assertIn('\\u003cimg', context['schema_json'])

    def test_generated_product_schema_falls_back_to_webpage_on_static_pages(self):
        page = get_managed_page('home')
        with patch('growth_center.page_seo.get_managed_page_by_path', return_value=page):
            PageSEO.objects.create(page_key='home', schema_mode='generated', schema_type='product')
            request = RequestFactory().get('/')
            context = build_page_seo_context(request, {})
        self.assertIn('"@type":"WebPage"', context['schema_json'])
        self.assertNotIn('"@type":"Product"', context['schema_json'])

    def test_status_reports_configuration_not_ranking(self):
        status = page_seo_status(get_managed_page('home'))
        labels = {check['label'] for check in status['checks']}
        self.assertIn('SEO title', labels)
        self.assertIn('Title length', labels)
        self.assertIn('Canonical URL', labels)
        self.assertIn('Structured data', labels)
        self.assertFalse(status['configured'])
        self.assertGreaterEqual(status['completeness'], 0)
        self.assertLessEqual(status['completeness'], 100)

    def test_model_save_invalidates_page_cache(self):
        cache_key = 'growth_center:page_seo:home'
        cache.set(cache_key, 'missing')
        PageSEO.objects.create(page_key='home', seo_title='Cached Page Title')
        self.assertIsNone(cache.get(cache_key))
        self.assertEqual(build_seo_context(RequestFactory().get('/'))['title'], 'Cached Page Title')
        clear_page_seo_cache('home')


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class PageSEOFormTests(TestCase):
    def setUp(self):
        clear_seo_settings_cache()
        cache.clear()
        self.page = get_managed_page('support')

    def tearDown(self):
        clear_seo_settings_cache()
        cache.clear()

    def form_data(self, **overrides):
        data = {
            'seo_title': '',
            'meta_description': '',
            'og_title': '',
            'og_description': '',
            'og_image_alt': '',
            'canonical_override': '',
            'index_mode': 'inherit',
            'follow_mode': 'inherit',
            'schema_mode': 'inherit',
            'schema_type': 'webpage',
            'schema_json': '',
        }
        data.update(overrides)
        return data

    def test_form_sanitizes_text_and_jsonld(self):
        form = PageSEOForm(
            data=self.form_data(
                seo_title='  <b>Safe</b>   Title  ',
                meta_description=f'<p>{"A" * 300}</p>',
                schema_mode='custom',
                schema_json='{"name":"<script>bad()</script>"}',
            ),
            page=self.page,
        )
        self.assertTrue(form.is_valid(), form.errors)
        instance = form.save()
        self.assertEqual(instance.seo_title, 'Safe Title')
        self.assertEqual(instance.meta_description, 'A' * 300)
        self.assertNotIn('<script>', instance.schema_json)
        self.assertIn('\\u003cscript\\u003e', instance.schema_json)

    def test_form_rejects_unsafe_canonical_urls(self):
        form = PageSEOForm(
            data=self.form_data(canonical_override='https://user:pass@example.com/path?x=1'),
            page=self.page,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('canonical_override', form.errors)

    def test_form_rejects_product_schema_on_static_pages(self):
        form = PageSEOForm(
            data=self.form_data(schema_mode='generated', schema_type='product'),
            page=self.page,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('schema_type', form.errors)

    def test_form_allows_product_schema_on_product_pages(self):
        product_page = ManagedPage(
            key='products.WordPressTheme:1',
            title='A WordPress Theme',
            path='/products/wordpress/a-wordpress-theme/',
            source='model',
            source_label='WordPress Theme',
            suggested_schema_type='product',
        )
        form = PageSEOForm(
            data=self.form_data(schema_mode='generated', schema_type='product'),
            page=product_page,
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_form_validates_and_removes_custom_image(self):
        upload = SimpleUploadedFile('page.png', make_test_image(), content_type='image/png')
        form = PageSEOForm(data=self.form_data(), files={'og_image': upload}, page=self.page)
        self.assertTrue(form.is_valid(), form.errors)
        instance = form.save()
        self.assertTrue(instance.og_image.name.startswith('seo/pages/'))

        removal_upload = SimpleUploadedFile('page-remove.png', make_test_image(), content_type='image/png')
        removal = PageSEOForm(
            data={**self.form_data(), 'remove_og_image': 'on'},
            files={'og_image': removal_upload},
            instance=instance,
            page=self.page,
        )
        self.assertTrue(removal.is_valid(), removal.errors)
        updated = removal.save()
        self.assertFalse(updated.og_image)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class PageSEOAdminTests(TestCase):
    def setUp(self):
        clear_seo_settings_cache()
        cache.clear()
        self.user = get_user_model().objects.create_superuser(
            username='page-seo-admin',
            email='page-seo@example.com',
            password='pass12345',
        )
        self.client.force_login(self.user)
        self.dashboard_url = reverse('admin:growth-center-page-seo')

    def tearDown(self):
        clear_seo_settings_cache()
        cache.clear()

    def editor_data(self, **overrides):
        data = {
            'seo_title': '',
            'meta_description': '',
            'og_title': '',
            'og_description': '',
            'og_image_alt': '',
            'canonical_override': '',
            'index_mode': 'inherit',
            'follow_mode': 'inherit',
            'schema_mode': 'inherit',
            'schema_type': 'webpage',
            'schema_json': '',
        }
        data.update(overrides)
        return data

    def test_sidebar_has_growth_center_items_in_order(self):
        response = self.client.get(self.dashboard_url)
        html = response.content.decode()
        analytics = html.index('/admin/growth-center/analytics/')
        seo_settings = html.index('/admin/growth-center/seo-settings/')
        page_seo = html.index('/admin/growth-center/page-seo/')
        self.assertLess(analytics, seo_settings)
        self.assertLess(seo_settings, page_seo)
        self.assertEqual(html.count('href="/admin/growth-center/page-seo/"'), 1)

    def test_dashboard_requires_staff_access(self):
        self.client.logout()
        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response.url)

    @override_settings(ALLOWED_HOSTS=['localhost', '127.0.0.1'])
    def test_dashboard_direct_request_does_not_use_synthetic_test_host(self):
        request = RequestFactory().get('/admin/growth-center/page-seo/')
        request.user = self.user
        response = page_seo_dashboard(request)
        self.assertEqual(response.status_code, 200)

    @override_settings(ALLOWED_HOSTS=['localhost', '127.0.0.1'])
    def test_editor_direct_request_does_not_use_synthetic_test_host(self):
        request = RequestFactory().get('/admin/growth-center/page-seo/support/')
        request.user = self.user
        response = page_seo_editor(request, 'support')
        self.assertEqual(response.status_code, 200)

    def test_dashboard_shows_status_columns_and_filters(self):
        PageSEO.objects.create(page_key='support', seo_title='A' * 40, index_mode='noindex')
        response = self.client.get(self.dashboard_url, {'filter': 'noindex', 'q': 'support'})
        self.assertContains(response, 'Support')
        self.assertContains(response, 'Noindex')
        self.assertContains(response, 'Page name/title')
        self.assertNotContains(response, '<code>/</code>')

    def test_editor_persists_page_seo_settings(self):
        url = reverse('admin:growth-center-page-seo-edit', args=['support'])
        response = self.client.post(url, self.editor_data(
            seo_title='Custom Support Title',
            meta_description='B' * 130,
            canonical_override='https://example.com/support-seo/',
            index_mode='noindex',
            follow_mode='nofollow',
            schema_mode='generated',
            schema_type='webpage',
        ))
        self.assertEqual(response.status_code, 302)

        instance = PageSEO.objects.get(page_key='support')
        self.assertEqual(instance.seo_title, 'Custom Support Title')
        self.assertEqual(instance.meta_description, 'B' * 130)
        self.assertEqual(instance.canonical_override, 'https://example.com/support-seo/')
        self.assertEqual(instance.index_mode, 'noindex')
        self.assertEqual(instance.follow_mode, 'nofollow')
        self.assertEqual(instance.schema_mode, 'generated')

        editor = self.client.get(url)
        self.assertContains(editor, 'Custom Support Title')
        self.assertContains(editor, 'Live illustration')
        self.assertContains(editor, 'Generated schema uses only real page data')

    def test_editor_rejects_invalid_settings_without_creating_records(self):
        url = reverse('admin:growth-center-page-seo-edit', args=['home'])
        response = self.client.post(url, self.editor_data(
            canonical_override='javascript:alert(1)',
        ))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Please correct the highlighted page SEO errors')
        self.assertFalse(PageSEO.objects.exists())

    def test_editor_reset_canonical_clears_override(self):
        url = reverse('admin:growth-center-page-seo-edit', args=['support'])
        PageSEO.objects.create(page_key='support', canonical_override='https://example.com/old/')
        response = self.client.post(url, self.editor_data(reset_canonical='1'))
        self.assertEqual(response.status_code, 302)
        instance = PageSEO.objects.get(page_key='support')
        self.assertEqual(instance.canonical_override, '')

    def test_editor_rejects_unknown_page(self):
        url = reverse('admin:growth-center-page-seo-edit', args=['does-not-exist'])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, self.dashboard_url)

    def test_bulk_actions_require_confirmation(self):
        response = self.client.post(self.dashboard_url, {
            'bulk_action': 'noindex',
            'page_keys': ['home', 'support'],
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(PageSEO.objects.exists())

    def test_bulk_actions_update_selected_pages(self):
        response = self.client.post(self.dashboard_url, {
            'bulk_action': 'noindex',
            'page_keys': ['home', 'support', 'not-a-page'],
            'confirm': '1',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(PageSEO.objects.filter(index_mode='noindex').count(), 2)
        self.assertFalse(PageSEO.objects.filter(page_key='not-a-page').exists())

        inherit = self.client.post(self.dashboard_url, {
            'bulk_action': 'inherit',
            'page_keys': ['home'],
            'confirm': '1',
        })
        self.assertEqual(inherit.status_code, 302)
        self.assertEqual(PageSEO.objects.get(page_key='home').index_mode, 'inherit')


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class PageSEOPublicTests(TestCase):
    def setUp(self):
        clear_seo_settings_cache()
        cache.clear()
        instance = get_seo_settings()
        instance.primary_domain = 'example.com'
        instance.save()
        clear_seo_settings_cache()

    def tearDown(self):
        clear_seo_settings_cache()
        cache.clear()

    def test_public_page_uses_page_metadata_without_duplicate_tags(self):
        PageSEO.objects.create(
            page_key='support',
            seo_title='Page Level Support Title',
            meta_description='C' * 130,
            canonical_override='https://example.com/support-page-seo/',
            index_mode='noindex',
            schema_mode='generated',
            schema_type='webpage',
        )
        response = self.client.get('/support/')
        html = response.content.decode()

        self.assertContains(response, 'Page Level Support Title')
        self.assertContains(response, 'content="index, follow"', 0)
        self.assertContains(response, 'content="noindex, follow"')
        self.assertContains(response, 'rel="canonical" href="https://example.com/support-page-seo/"')
        self.assertContains(response, 'property="og:url" content="https://example.com/support-page-seo/"')
        self.assertContains(response, '<script type="application/ld+json">')
        self.assertEqual(html.count('name="description"'), 1)
        self.assertEqual(html.count('rel="canonical"'), 1)
        self.assertEqual(html.count('property="og:title"'), 1)
        self.assertEqual(html.count('property="og:image"'), 1)
        self.assertEqual(html.count('<script type="application/ld+json">'), 1)

    def test_visitors_never_create_page_seo_records(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(PageSEO.objects.exists())

    def test_sitemap_excludes_noindex_and_deduplicates_canonicals(self):
        response = self.client.get('/sitemap.xml')
        self.assertEqual(response.status_code, 200)

        import xml.etree.ElementTree as ET

        namespace = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        locations = [
            node.text for node in ET.fromstring(response.content).findall('.//s:loc', namespace)
        ]
        self.assertIn('https://example.com/', locations)
        self.assertIn('https://example.com/support/', locations)
        self.assertEqual(len(locations), len(set(locations)))

        PageSEO.objects.create(page_key='support', index_mode='noindex')
        noindex_response = self.client.get('/sitemap.xml')
        noindex_locations = [
            node.text for node in ET.fromstring(noindex_response.content).findall('.//s:loc', namespace)
        ]
        self.assertNotIn('https://example.com/support/', noindex_locations)

        support = PageSEO.objects.get(page_key='support')
        support.index_mode = 'inherit'
        support.canonical_override = 'https://example.com/duplicate/'
        support.save()
        PageSEO.objects.create(page_key='home', canonical_override='https://example.com/duplicate/')
        dedupe_response = self.client.get('/sitemap.xml')
        dedupe_locations = [
            node.text for node in ET.fromstring(dedupe_response.content).findall('.//s:loc', namespace)
        ]
        self.assertEqual(dedupe_locations.count('https://example.com/duplicate/'), 1)
