import json
import os
import uuid

from django.db import models
from django.urls import reverse
from django.utils.text import slugify

from .storage import private_product_storage
from .validators import (
    validate_excel_workbook,
    validate_http_url,
    validate_product_image,
    validate_wordpress_package,
)


def wordpress_image_path(instance, filename):
    extension = os.path.splitext(filename.lower())[1]
    slug = slugify(instance.title) or 'wordpress-theme'
    return f"wordpress/{slug}/{uuid.uuid4().hex}{extension}"


def wordpress_package_path(instance, filename):
    extension = os.path.splitext(filename.lower())[1]
    slug = slugify(instance.title) or 'wordpress-theme'
    return f"packages/wordpress/{slug}/{uuid.uuid4().hex}{extension}"


def excel_image_path(instance, filename):
    extension = os.path.splitext(filename.lower())[1]
    slug = slugify(instance.title) or 'excel-dashboard'
    return f"excel/{slug}/{uuid.uuid4().hex}{extension}"


def excel_workbook_path(instance, filename):
    extension = os.path.splitext(filename.lower())[1]
    slug = slugify(instance.title) or 'excel-dashboard'
    return f"packages/excel/{slug}/{uuid.uuid4().hex}{extension}"


def preview_image_path(instance, filename):
    extension = os.path.splitext(filename.lower())[1]
    slug = slugify(instance.product.title) or 'preview'
    return f"previews/{slug}/{uuid.uuid4().hex}{extension}"


class ProductBase(models.Model):
    title = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180, unique=True)
    short_description = models.TextField(max_length=360)
    description = models.TextField()
    thumbnail = models.ImageField(
        upload_to=wordpress_image_path,
        validators=[validate_product_image],
    )
    price = models.DecimalField(max_digits=9, decimal_places=2)
    sale_price = models.DecimalField(
        max_digits=9,
        decimal_places=2,
        null=True,
        blank=True,
    )
    demo_url = models.URLField(
        max_length=300,
        blank=True,
        validators=[validate_http_url],
    )
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    display_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    def __str__(self):
        return self.title

    @property
    def price_label(self):
        return f'${self.price:,.2f}'

    @property
    def display_price_label(self):
        if self.has_sale:
            return f'${self.sale_price:,.2f}'
        return self.price_label

    @property
    def has_sale(self):
        return self.sale_price is not None and self.sale_price < self.price

    @property
    def preview_count(self):
        return self.screenshots.filter(is_active=True).count()

    @property
    def preview_data_json(self):
        payload = {
            'title': self.title,
            'kind': self.product_kind,
            'shortDescription': self.short_description,
            'description': self.description,
            'thumbnail': self.thumbnail.url if self.thumbnail else '',
            'price': self.display_price_label,
            'originalPrice': self.price_label if self.has_sale else '',
            'detailUrl': self.get_absolute_url(),
            'demoUrl': self.demo_url,
            'screenshots': [
                {
                    'url': image.image.url,
                    'alt': image.caption or f'{self.title} preview {image.display_order}',
                    'caption': image.caption,
                }
                for image in self.screenshots.filter(is_active=True)
            ],
        }
        return json.dumps(payload, separators=(',', ':'))

    def _delete_replaced_files(self):
        if not self.pk:
            return
        try:
            previous = type(self).objects.get(pk=self.pk)
        except type(self).DoesNotExist:
            return
        for field_name in ('thumbnail', 'download_file'):
            old_file = getattr(previous, field_name, None)
            new_file = getattr(self, field_name, None)
            if old_file and old_file.name and old_file.name != getattr(new_file, 'name', None):
                old_file.delete(save=False)

    def save(self, *args, **kwargs):
        self._delete_replaced_files()
        return super().save(*args, **kwargs)


class PreviewImageBase(models.Model):
    caption = models.CharField(max_length=160, blank=True)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True
        ordering = ('display_order', 'created_at')

    def __str__(self):
        return f'{self.product.title} preview {self.display_order}'


class WordPressTheme(ProductBase):
    thumbnail = models.ImageField(
        upload_to=wordpress_image_path,
        validators=[validate_product_image],
    )
    download_file = models.FileField(
        upload_to=wordpress_package_path,
        storage=private_product_storage,
        validators=[validate_wordpress_package],
        max_length=300,
    )
    theme_version = models.CharField(max_length=40)
    minimum_wordpress_version = models.CharField(max_length=40, blank=True)
    page_builder = models.CharField(max_length=80, blank=True)
    requires_license_key = models.BooleanField(default=False)

    product_kind = 'wordpress'
    kind_label = 'WordPress Theme'

    class Meta:
        ordering = ('display_order', '-created_at')
        verbose_name = 'WordPress Theme'
        verbose_name_plural = 'WordPress Themes'

    def get_absolute_url(self):
        return reverse('products:wordpress_detail', args=[self.slug])


class ExcelDashboard(ProductBase):
    thumbnail = models.ImageField(
        upload_to=excel_image_path,
        validators=[validate_product_image],
    )
    download_file = models.FileField(
        upload_to=excel_workbook_path,
        storage=private_product_storage,
        validators=[validate_excel_workbook],
        max_length=300,
    )
    workbook_version = models.CharField(max_length=40)
    sheet_count = models.PositiveIntegerField(default=1)
    excel_compatibility = models.CharField(max_length=80, blank=True)
    has_macros = models.BooleanField(default=False)

    product_kind = 'excel'
    kind_label = 'Excel Dashboard'

    class Meta:
        ordering = ('display_order', '-created_at')
        verbose_name = 'Excel Dashboard'
        verbose_name_plural = 'Excel Dashboards'

    def get_absolute_url(self):
        return reverse('products:excel_detail', args=[self.slug])


class WordPressThemeImage(PreviewImageBase):
    product = models.ForeignKey(
        WordPressTheme,
        on_delete=models.CASCADE,
        related_name='screenshots',
    )
    image = models.ImageField(
        upload_to=preview_image_path,
        validators=[validate_product_image],
    )


class ExcelDashboardImage(PreviewImageBase):
    product = models.ForeignKey(
        ExcelDashboard,
        on_delete=models.CASCADE,
        related_name='screenshots',
    )
    image = models.ImageField(
        upload_to=preview_image_path,
        validators=[validate_product_image],
    )
