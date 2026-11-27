import os
import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from .social_platforms import (
    ACCOUNT_STATUSES,
    CONTENT_TYPES,
    PLATFORM_CHOICES,
    STATUSES,
    TEMPLATE_KINDS,
)
from .social_storage import social_media_storage
from .social_validators import validate_social_media

from .validators import SAFE_ROBOTS_TXT, validate_seo_image


def seo_image_path(instance, filename):
    extension = os.path.splitext(filename.lower())[1]
    return f'seo/default-{uuid.uuid4().hex}{extension}'


def page_seo_image_path(instance, filename):
    extension = os.path.splitext(filename.lower())[1]
    return f'seo/pages/{uuid.uuid4().hex}{extension}'


class Visitor(models.Model):
    visitor_key = models.CharField(max_length=64, unique=True, db_index=True)
    first_seen = models.DateTimeField(default=timezone.now, db_index=True)
    last_seen = models.DateTimeField(default=timezone.now)
    country_code = models.CharField(max_length=2, blank=True, db_index=True)

    class Meta:
        ordering = ('-last_seen',)

    def __str__(self):
        return f'Visitor {self.visitor_key[:12]}'


class AnalyticsSession(models.Model):
    DEVICE_CHOICES = (
        ('Desktop', 'Desktop'),
        ('Mobile', 'Mobile'),
        ('Tablet', 'Tablet'),
    )

    session_key = models.CharField(max_length=64, unique=True, db_index=True)
    visitor = models.ForeignKey(Visitor, on_delete=models.CASCADE, related_name='sessions')
    started_at = models.DateTimeField(default=timezone.now, db_index=True)
    last_seen_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True, db_index=True)
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    page_view_count = models.PositiveIntegerField(default=0)
    is_returning = models.BooleanField(default=False, db_index=True)
    source_category = models.CharField(max_length=32, default='Direct', db_index=True)
    source_label = models.CharField(max_length=120, blank=True)
    referrer_host = models.CharField(max_length=253, blank=True)
    utm_source = models.CharField(max_length=120, blank=True)
    utm_medium = models.CharField(max_length=120, blank=True)
    utm_campaign = models.CharField(max_length=120, blank=True)
    utm_term = models.CharField(max_length=120, blank=True)
    utm_content = models.CharField(max_length=120, blank=True)
    landing_path = models.CharField(max_length=500, blank=True, db_index=True)
    exit_path = models.CharField(max_length=500, blank=True, db_index=True)
    device_category = models.CharField(max_length=16, default='Desktop', choices=DEVICE_CHOICES, db_index=True)
    browser_category = models.CharField(max_length=20, default='Other', db_index=True)
    country_code = models.CharField(max_length=2, blank=True, db_index=True)

    class Meta:
        ordering = ('-started_at',)
        indexes = [
            models.Index(fields=['visitor', '-started_at']),
            models.Index(fields=['source_category', '-started_at']),
            models.Index(fields=['device_category', '-started_at']),
            models.Index(fields=['landing_path', '-started_at']),
            models.Index(fields=['country_code', '-started_at']),
        ]

    def __str__(self):
        return f'Session {self.session_key[:12]}'


class PageView(models.Model):
    session = models.ForeignKey(AnalyticsSession, on_delete=models.CASCADE, related_name='page_views')
    visitor = models.ForeignKey(Visitor, on_delete=models.CASCADE, related_name='page_views')
    path = models.CharField(max_length=500, db_index=True)
    title = models.CharField(max_length=220, blank=True)
    from_path = models.CharField(max_length=500, blank=True, db_index=True)
    viewed_at = models.DateTimeField(default=timezone.now, db_index=True)
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ('-viewed_at',)
        indexes = [
            models.Index(fields=['path', '-viewed_at']),
            models.Index(fields=['session', 'path', '-viewed_at']),
            models.Index(fields=['from_path', 'path', '-viewed_at']),
        ]

    def __str__(self):
        return f'{self.path} at {self.viewed_at:%Y-%m-%d %H:%M}'


class Campaign(models.Model):
    STATUS_CHOICES = (
        ('Draft', 'Draft'),
        ('Active', 'Active'),
        ('Paused', 'Paused'),
        ('Completed', 'Completed'),
        ('Archived', 'Archived'),
    )

    OBJECTIVE_CHOICES = (
        ('traffic', 'Website Traffic'),
        ('leads', 'Lead Generation'),
        ('sales', 'Sales'),
        ('awareness', 'Brand Awareness'),
        ('engagement', 'Engagement'),
    )

    campaign_key = models.CharField(max_length=32, unique=True, editable=False, db_index=True)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    objective = models.CharField(max_length=24, choices=OBJECTIVE_CHOICES, default='traffic')
    destination_url = models.URLField(max_length=500)
    utm_source = models.CharField(max_length=120, db_index=True)
    utm_medium = models.CharField(max_length=120, db_index=True)
    utm_campaign = models.CharField(max_length=120, unique=True, db_index=True)
    utm_term = models.CharField(max_length=120, blank=True)
    utm_content = models.CharField(max_length=120, blank=True)
    start_date = models.DateField(null=True, blank=True, db_index=True)
    end_date = models.DateField(null=True, blank=True, db_index=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='Draft', db_index=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='campaigns',
    )

    class Meta:
        ordering = ('-created_at',)
        indexes = [
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['utm_campaign', 'utm_source', 'utm_medium']),
            models.Index(fields=['utm_source', '-created_at']),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({'end_date': 'End date must be on or after the start date.'})

    def save(self, *args, **kwargs):
        if not self.campaign_key:
            self.campaign_key = f'CMP-{uuid.uuid4().hex[:10].upper()}'
        super().save(*args, **kwargs)


def social_asset_path(instance, filename):
    suffix = Path(filename).suffix.lower()
    return f'social-media/{uuid.uuid4().hex}{suffix}'


class SocialMediaAsset(models.Model):
    MEDIA_TYPES = (
        ('Image', 'Image'),
        ('Video', 'Video'),
    )

    asset_key = models.CharField(max_length=32, unique=True, editable=False, db_index=True)
    title = models.CharField(max_length=150)
    file = models.FileField(
        upload_to=social_asset_path,
        storage=social_media_storage,
        validators=[validate_social_media],
        max_length=300,
    )
    media_type = models.CharField(max_length=8, choices=MEDIA_TYPES, default='Image', db_index=True)
    alt_text = models.CharField(max_length=200, blank=True)
    mime_type = models.CharField(max_length=100, blank=True)
    size_bytes = models.PositiveBigIntegerField(default=0)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='social_media_assets')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ('-created_at',)
        indexes = [
            models.Index(fields=['media_type', '-created_at']),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.asset_key:
            self.asset_key = f'SMA-{uuid.uuid4().hex[:10].upper()}'
        if self.file and not self.mime_type:
            import mimetypes

            self.mime_type = mimetypes.guess_type(self.file.name)[0] or ''
        if self.file and not self.size_bytes:
            try:
                self.size_bytes = self.file.size
            except (AttributeError, OSError, ValueError):
                self.size_bytes = 0
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        file = self.file
        result = super().delete(*args, **kwargs)
        if file:
            file.delete(save=False)
        return result

    @property
    def size_display(self):
        size = float(self.size_bytes or 0)
        for unit in ('B', 'KB', 'MB', 'GB'):
            if size < 1024 or unit == 'GB':
                return f'{size:.0f} {unit}' if unit == 'B' else f'{size:.1f} {unit}'
            size /= 1024
        return '0 B'


class SocialPost(models.Model):
    STATUS_CHOICES = STATUSES
    CONTENT_TYPE_CHOICES = CONTENT_TYPES

    post_key = models.CharField(max_length=32, unique=True, editable=False, db_index=True)
    title = models.CharField(max_length=150)
    content = models.TextField()
    content_type = models.CharField(max_length=24, choices=CONTENT_TYPE_CHOICES, default='post')
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='Draft', db_index=True)
    scheduled_at = models.DateTimeField(null=True, blank=True, db_index=True)
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)
    campaign = models.ForeignKey(Campaign, null=True, blank=True, on_delete=models.SET_NULL, related_name='social_posts')
    media = models.ManyToManyField(SocialMediaAsset, blank=True, related_name='posts')
    destination_url = models.URLField(max_length=500, blank=True)
    utm_source = models.CharField(max_length=120, blank=True)
    utm_medium = models.CharField(max_length=120, blank=True, db_index=True)
    utm_campaign = models.CharField(max_length=120, blank=True, db_index=True)
    utm_term = models.CharField(max_length=120, blank=True)
    utm_content = models.CharField(max_length=120, blank=True)
    hashtags = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='social_posts')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-created_at',)
        indexes = [
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['status', 'scheduled_at']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.post_key:
            self.post_key = f'SOC-{uuid.uuid4().hex[:10].upper()}'
        super().save(*args, **kwargs)

    @property
    def platform_keys(self):
        return list(self.platform_entries.values_list('platform', flat=True))

    @property
    def content_preview(self):
        text = ' '.join((self.content or '').split())
        return text[:140] + ('…' if len(text) > 140 else '')


class SocialPostPlatform(models.Model):
    STATUS_CHOICES = STATUSES

    post = models.ForeignKey(SocialPost, on_delete=models.CASCADE, related_name='platform_entries')
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES, db_index=True)
    content = models.TextField(blank=True)
    platform_title = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='Draft', db_index=True)
    scheduled_at = models.DateTimeField(null=True, blank=True, db_index=True)
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)
    published_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='social_platform_publications')
    publication_url = models.URLField(max_length=500, blank=True)
    tracking_url = models.URLField(max_length=500, blank=True)

    class Meta:
        ordering = ('platform',)
        constraints = [
            models.UniqueConstraint(fields=['post', 'platform'], name='unique_social_post_platform'),
        ]
        indexes = [
            models.Index(fields=['platform', 'status']),
            models.Index(fields=['platform', 'scheduled_at']),
        ]

    def __str__(self):
        return f'{self.post.title} on {self.get_platform_display()}'


class SocialAccount(models.Model):
    STATUS_CHOICES = ACCOUNT_STATUSES

    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES, unique=True)
    account_name = models.CharField(max_length=150, blank=True)
    status = models.CharField(max_length=14, choices=STATUS_CHOICES, default='Not Connected', db_index=True)
    connected_at = models.DateTimeField(null=True, blank=True)
    disconnected_at = models.DateTimeField(null=True, blank=True)
    capabilities = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('platform',)

    def __str__(self):
        return f'{self.get_platform_display()}: {self.status}'


class SocialPostTemplate(models.Model):
    KIND_CHOICES = TEMPLATE_KINDS

    template_key = models.CharField(max_length=32, unique=True, editable=False, db_index=True)
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=12, choices=KIND_CHOICES, default='template', db_index=True)
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES, blank=True, db_index=True)
    content = models.TextField()
    hashtags = models.CharField(max_length=500, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='social_templates')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.template_key:
            self.template_key = f'SPT-{uuid.uuid4().hex[:10].upper()}'
        super().save(*args, **kwargs)


class SEOSettings(models.Model):
    WWW_CHOICES = (
        ('auto', 'Use configured domain as-is'),
        ('with', 'Prefer www'),
        ('without', 'Prefer non-www'),
    )
    CANONICAL_CHOICES = (
        ('auto', 'Use current public domain'),
        ('force_domain', 'Always use primary domain'),
    )
    TRAILING_CHOICES = (
        ('preserve', 'Preserve URL as requested'),
        ('force_slash', 'Prefer trailing slash'),
        ('strip_slash', 'Prefer no trailing slash'),
    )

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    seo_title = models.CharField(max_length=120, blank=True)
    meta_description = models.TextField(max_length=320, blank=True)
    meta_keywords = models.CharField(max_length=500, blank=True)
    site_name = models.CharField(max_length=120, blank=True)
    default_image = models.ImageField(upload_to=seo_image_path, validators=[validate_seo_image], blank=True)
    index_enabled = models.BooleanField(default=True)
    follow_enabled = models.BooleanField(default=True)
    primary_domain = models.CharField(max_length=253, blank=True)
    prefer_https = models.BooleanField(default=True)
    preferred_www = models.CharField(max_length=10, choices=WWW_CHOICES, default='auto')
    canonical_behavior = models.CharField(max_length=20, choices=CANONICAL_CHOICES, default='auto')
    trailing_slash_behavior = models.CharField(max_length=20, choices=TRAILING_CHOICES, default='preserve')
    sitemap_enabled = models.BooleanField(default=True)
    robots_txt_enabled = models.BooleanField(default=True)
    robots_txt_content = models.TextField(blank=True)
    google_verification_token = models.CharField(max_length=120, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'SEO Settings'
        verbose_name_plural = 'SEO Settings'

    def __str__(self):
        return 'Global SEO Settings'

    @classmethod
    def load(cls):
        from .seo_settings import get_seo_settings

        return get_seo_settings()

    @classmethod
    def safe_defaults(cls):
        return {
            'seo_title': '',
            'meta_description': '',
            'meta_keywords': '',
            'site_name': '',
            'default_image': '',
            'index_enabled': True,
            'follow_enabled': True,
            'primary_domain': '',
            'prefer_https': True,
            'preferred_www': 'auto',
            'canonical_behavior': 'auto',
            'trailing_slash_behavior': 'preserve',
            'sitemap_enabled': True,
            'robots_txt_enabled': True,
            'robots_txt_content': SAFE_ROBOTS_TXT,
            'google_verification_token': '',
        }

    def save(self, *args, **kwargs):
        from .seo_settings import clear_seo_settings_cache

        self.pk = 1
        previous = type(self).objects.filter(pk=1).first()
        if previous and previous.default_image and previous.default_image.name != self.default_image.name:
            previous.default_image.delete(save=False)
        super().save(*args, **kwargs)
        clear_seo_settings_cache()

    def delete(self, *args, **kwargs):
        from .seo_settings import clear_seo_settings_cache

        clear_seo_settings_cache()
        return 0, {}


class PageSEO(models.Model):
    INDEX_CHOICES = (
        ('inherit', 'Inherit Global Setting'),
        ('index', 'Index'),
        ('noindex', 'Noindex'),
    )
    FOLLOW_CHOICES = (
        ('inherit', 'Inherit Global Setting'),
        ('follow', 'Follow'),
        ('nofollow', 'Nofollow'),
    )
    SCHEMA_MODE_CHOICES = (
        ('inherit', 'Inherit default behavior'),
        ('disabled', 'Disable page schema'),
        ('generated', 'Generate from real page data'),
        ('custom', 'Custom JSON-LD'),
    )
    SCHEMA_TYPE_CHOICES = (
        ('webpage', 'WebPage'),
        ('article', 'Article'),
        ('product', 'Product'),
        ('organization', 'Organization'),
        ('breadcrumblist', 'BreadcrumbList'),
        ('faqpage', 'FAQPage'),
    )

    page_key = models.CharField(max_length=220, unique=True)
    seo_title = models.CharField(max_length=120, blank=True)
    meta_description = models.TextField(max_length=320, blank=True)
    og_title = models.CharField(max_length=120, blank=True)
    og_description = models.TextField(max_length=320, blank=True)
    og_image_alt = models.CharField(max_length=160, blank=True)
    og_image = models.ImageField(upload_to=page_seo_image_path, validators=[validate_seo_image], blank=True)
    canonical_override = models.CharField(max_length=500, blank=True)
    index_mode = models.CharField(max_length=10, choices=INDEX_CHOICES, default='inherit')
    follow_mode = models.CharField(max_length=10, choices=FOLLOW_CHOICES, default='inherit')
    schema_mode = models.CharField(max_length=12, choices=SCHEMA_MODE_CHOICES, default='inherit')
    schema_type = models.CharField(max_length=16, choices=SCHEMA_TYPE_CHOICES, default='webpage')
    schema_json = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('page_key',)
        indexes = [
            models.Index(fields=['index_mode']),
            models.Index(fields=['schema_mode']),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(index_mode__in=['inherit', 'index', 'noindex']),
                name='pageseo_valid_index_mode',
            ),
            models.CheckConstraint(
                condition=Q(follow_mode__in=['inherit', 'follow', 'nofollow']),
                name='pageseo_valid_follow_mode',
            ),
            models.CheckConstraint(
                condition=Q(schema_mode__in=['inherit', 'disabled', 'generated', 'custom']),
                name='pageseo_valid_schema_mode',
            ),
        ]

    def __str__(self):
        return f'Page SEO: {self.page_key}'

    @property
    def is_configured(self):
        return bool(
            self.seo_title
            or self.meta_description
            or self.og_title
            or self.og_description
            or self.og_image
            or self.canonical_override
            or self.index_mode != 'inherit'
            or self.follow_mode != 'inherit'
            or self.schema_mode != 'inherit'
        )

    def save(self, *args, **kwargs):
        from .page_seo_cache import clear_page_seo_cache

        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).first()
            if previous and previous.og_image and previous.og_image.name != self.og_image.name:
                previous.og_image.delete(save=False)
        super().save(*args, **kwargs)
        clear_page_seo_cache(self.page_key)

    def delete(self, *args, **kwargs):
        from .page_seo_cache import clear_page_seo_cache

        key = self.page_key
        if self.og_image:
            self.og_image.delete(save=False)
        result = super().delete(*args, **kwargs)
        clear_page_seo_cache(key)
        return result
