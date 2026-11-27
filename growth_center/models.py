import os
import uuid

from django.db import models
from django.utils import timezone

from .validators import SAFE_ROBOTS_TXT, validate_seo_image


def seo_image_path(instance, filename):
    extension = os.path.splitext(filename.lower())[1]
    return f'seo/default-{uuid.uuid4().hex}{extension}'


class Visitor(models.Model):
    visitor_key = models.CharField(max_length=64, unique=True, db_index=True)
    first_seen = models.DateTimeField(default=timezone.now, db_index=True)
    last_seen = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ('-last_seen',)

    def __str__(self):
        return f'Visitor {self.visitor_key[:12]}'


class AnalyticsSession(models.Model):
    session_key = models.CharField(max_length=64, unique=True, db_index=True)
    visitor = models.ForeignKey(Visitor, on_delete=models.CASCADE, related_name='sessions')
    started_at = models.DateTimeField(default=timezone.now, db_index=True)
    last_seen_at = models.DateTimeField(default=timezone.now)
    page_view_count = models.PositiveIntegerField(default=0)
    is_returning = models.BooleanField(default=False, db_index=True)
    source_category = models.CharField(max_length=32, default='Direct', db_index=True)
    source_label = models.CharField(max_length=120, blank=True)
    landing_path = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ('-started_at',)
        indexes = [
            models.Index(fields=['visitor', '-started_at']),
            models.Index(fields=['source_category', '-started_at']),
        ]

    def __str__(self):
        return f'Session {self.session_key[:12]}'


class PageView(models.Model):
    session = models.ForeignKey(AnalyticsSession, on_delete=models.CASCADE, related_name='page_views')
    visitor = models.ForeignKey(Visitor, on_delete=models.CASCADE, related_name='page_views')
    path = models.CharField(max_length=500, db_index=True)
    viewed_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ('-viewed_at',)
        indexes = [
            models.Index(fields=['path', '-viewed_at']),
            models.Index(fields=['session', 'path', '-viewed_at']),
        ]

    def __str__(self):
        return f'{self.path} at {self.viewed_at:%Y-%m-%d %H:%M}'


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
