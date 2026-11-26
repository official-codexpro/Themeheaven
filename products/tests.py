import io
import tempfile
import uuid
import zipfile
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils.text import slugify
from PIL import Image

from .models import ExcelDashboard, WordPressTheme
from .storage import PrivateProductStorage
from .validators import (
    validate_excel_workbook,
    validate_http_url,
    validate_product_image,
    validate_wordpress_package,
)


def image_file(name='preview.png'):
    buffer = io.BytesIO()
    Image.new('RGB', (120, 80), (110, 70, 190)).save(buffer, format='PNG')
    return ContentFile(buffer.getvalue(), name=name)


def zip_file(name='theme.zip'):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('style.css', '/* test theme */')
    return ContentFile(buffer.getvalue(), name=name)


def workbook_file(name='dashboard.xlsx'):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('[Content_Types].xml', '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        archive.writestr('xl/workbook.xml', '<workbook/>')
    return ContentFile(buffer.getvalue(), name=name)


class ValidatorTests(TestCase):
    def test_valid_image_passes(self):
        validate_product_image(image_file())

    def test_invalid_image_extension_is_rejected(self):
        with self.assertRaises(ValidationError):
            validate_product_image(ContentFile(b'not an image', name='preview.exe'))

    def test_image_extension_must_match_content(self):
        buffer = io.BytesIO()
        Image.new('RGB', (80, 60), (80, 120, 200)).save(buffer, format='JPEG')
        with self.assertRaises(ValidationError):
            validate_product_image(ContentFile(buffer.getvalue(), name='preview.png'))

    def test_valid_wordpress_package_passes(self):
        validate_wordpress_package(zip_file())

    def test_fake_wordpress_package_is_rejected(self):
        with self.assertRaises(ValidationError):
            validate_wordpress_package(ContentFile(b'not a zip', name='theme.zip'))

    def test_valid_excel_workbook_passes(self):
        validate_excel_workbook(workbook_file())

    def test_zip_without_workbook_metadata_is_rejected(self):
        with self.assertRaises(ValidationError):
            validate_excel_workbook(zip_file('dashboard.xlsx'))

    def test_unsafe_url_is_rejected(self):
        with self.assertRaises(ValidationError):
            validate_http_url('javascript:alert(1)')


class ProductFixtureTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tempdir = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tempdir.cleanup)
        cls.settings_override = override_settings(
            MEDIA_ROOT=cls.tempdir.name,
            PRODUCT_PRIVATE_ROOT=cls.tempdir.name,
        )
        cls.settings_override.enable()
        cls.addClassCleanup(cls.settings_override.disable)

        public_storage = FileSystemStorage(location=cls.tempdir.name, base_url='/media/')
        private_storage = PrivateProductStorage()
        for model, field_name, storage in (
            (WordPressTheme, 'thumbnail', public_storage),
            (WordPressTheme, 'download_file', private_storage),
            (ExcelDashboard, 'thumbnail', public_storage),
            (ExcelDashboard, 'download_file', private_storage),
        ):
            field = model._meta.get_field(field_name)
            original = field.storage
            field.storage = storage
            cls.addClassCleanup(setattr, field, 'storage', original)

        cls.client = Client(HTTP_HOST='localhost')

    def create_wordpress(self, title, active=True, order=0):
        slug = f"{slugify(title)}-{uuid.uuid4().hex[:8]}"
        return WordPressTheme.objects.create(
            title=title,
            slug=slug,
            short_description='A polished WordPress theme.',
            description='A polished WordPress theme with flexible layouts.',
            thumbnail=image_file(f'{slug}.png'),
            price=Decimal('59.00'),
            sale_price=Decimal('39.00'),
            download_file=zip_file(f'{slug}.zip'),
            theme_version='1.0',
            is_active=active,
            display_order=order,
        )

    def create_excel(self, title, active=True, order=0):
        slug = f"{slugify(title)}-{uuid.uuid4().hex[:8]}"
        return ExcelDashboard.objects.create(
            title=title,
            slug=slug,
            short_description='A clear Excel reporting dashboard.',
            description='A clear Excel reporting dashboard for everyday work.',
            thumbnail=image_file(f'{slug}.png'),
            price=Decimal('29.00'),
            download_file=workbook_file(f'{slug}.xlsx'),
            workbook_version='1.0',
            sheet_count=4,
            is_active=active,
            display_order=order,
        )


class HomepageProductTests(ProductFixtureTestCase):
    def setUp(self):
        for index in range(10):
            self.create_wordpress(f'WP Theme {index}', order=index)
        for index in range(10):
            self.create_excel(f'Excel Dashboard {index}', order=index)
        self.create_wordpress('Hidden Theme', active=False, order=20)
        self.create_excel('Hidden Dashboard', active=False, order=20)

    def test_homepage_renders_initial_eight_for_each_type(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertEqual(html.count('data-product-preview="'), 16)
        self.assertNotIn('Discover More', html)
        self.assertNotIn('Start with your industry', html)
        self.assertNotIn('Find your next starting point', html)
        self.assertIn('id="wordpress-themes"', html)
        self.assertIn('id="excel-dashboards"', html)

    def test_show_more_batches_are_independent(self):
        wordpress = self.client.get(reverse('products:wordpress_more'), {'offset': 8})
        excel = self.client.get(reverse('products:excel_more'), {'offset': 8})
        self.assertEqual(wordpress.status_code, 200)
        self.assertEqual(excel.status_code, 200)
        wordpress_data = wordpress.json()
        excel_data = excel.json()
        self.assertEqual(wordpress_data['html'].count('data-product-preview="'), 2)
        self.assertEqual(excel_data['html'].count('data-product-preview="'), 2)
        self.assertFalse(wordpress_data['has_more'])
        self.assertFalse(excel_data['has_more'])
        self.assertNotIn('Hidden Theme', wordpress_data['html'])
        self.assertNotIn('Hidden Dashboard', excel_data['html'])

    def test_search_filters_both_types(self):
        response = self.client.get('/', {'q': 'Theme 3'})
        html = response.content.decode()
        self.assertIn('WP Theme 3', html)
        self.assertNotIn('WP Theme 4', html)
        self.assertNotIn('Excel Dashboard 3', html)

    def test_inactive_products_return_not_found(self):
        hidden_wordpress = WordPressTheme.objects.get(title='Hidden Theme')
        hidden_excel = ExcelDashboard.objects.get(title='Hidden Dashboard')
        self.assertEqual(self.client.get(hidden_wordpress.get_absolute_url()).status_code, 404)
        self.assertEqual(self.client.get(hidden_excel.get_absolute_url()).status_code, 404)


class ProductSecurityTests(ProductFixtureTestCase):
    def setUp(self):
        self.wordpress = self.create_wordpress('Secure Theme')
        self.excel = self.create_excel('Secure Dashboard')
        self.user = self.client.get('/').wsgi_request.user

    def test_download_requires_staff(self):
        response = self.client.get(reverse('products:download_wordpress', args=[self.wordpress.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response['Location'])

    def test_staff_can_download_without_public_file_url(self):
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.create_superuser(
            username='staff',
            email='staff@example.com',
            password='strong-password-123',
        )
        self.client.force_login(user)
        response = self.client.get(reverse('products:download_excel', args=[self.excel.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.streaming)
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertEqual(self.excel.download_file.url, '')

    def test_detail_page_hides_download_for_public_users(self):
        response = self.client.get(self.wordpress.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertNotIn(reverse('products:download_wordpress', args=[self.wordpress.pk]), html)
        self.assertIn('Request Access', html)


class AdminSeparationTests(ProductFixtureTestCase):
    def setUp(self):
        self.wordpress = self.create_wordpress('Admin Theme')
        self.excel = self.create_excel('Admin Dashboard')

    def test_admin_has_distinct_product_models(self):
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.create_superuser(
            username='admin-user',
            email='admin@example.com',
            password='strong-password-123',
        )
        self.client.force_login(user)
        response = self.client.get('/admin/')
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('WordPress Themes', html)
        self.assertIn('Excel Dashboards', html)

    def test_admin_forms_render_for_both_product_types(self):
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.create_superuser(
            username='form-admin',
            email='form-admin@example.com',
            password='strong-password-123',
        )
        self.client.force_login(user)
        urls = (
            reverse('admin:products_wordpresstheme_add'),
            reverse('admin:products_exceldashboard_add'),
            reverse('admin:products_wordpresstheme_change', args=[self.wordpress.pk]),
            reverse('admin:products_exceldashboard_change', args=[self.excel.pk]),
        )
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
