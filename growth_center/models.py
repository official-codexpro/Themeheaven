import os
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify

from .content_constants import (
    CONTENT_PRIORITIES,
    CONTENT_STATUSES,
    CONTENT_TYPES as CONTENT_MARKETING_TYPES,
    IDEA_SOURCES,
    REFRESH_STATUSES,
)
from .conversion_constants import (
    COST_PERIODS,
    FUNNEL_STATUSES,
    FUNNEL_STEP_TYPES,
    GOAL_STATUSES,
    GOAL_TYPES,
    TRACKING_RULE_STATUSES,
)
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


class ContentCategory(models.Model):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    description = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('name',)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:140] or f'category-{uuid.uuid4().hex[:8]}'
        super().save(*args, **kwargs)


class ContentTag(models.Model):
    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=100, unique=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('name',)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:100] or f'tag-{uuid.uuid4().hex[:8]}'
        super().save(*args, **kwargs)


class MarketingContent(models.Model):
    STATUS_CHOICES = CONTENT_STATUSES
    TYPE_CHOICES = CONTENT_MARKETING_TYPES
    PRIORITY_CHOICES = CONTENT_PRIORITIES

    content_key = models.CharField(max_length=32, unique=True, editable=False, db_index=True)
    title = models.CharField(max_length=180)
    slug = models.SlugField(max_length=180, blank=True)
    content_type = models.CharField(max_length=24, choices=TYPE_CHOICES, default='Blog Post', db_index=True)
    description = models.TextField(blank=True)
    brief = models.TextField(blank=True)
    body = models.TextField(blank=True)
    target_audience = models.CharField(max_length=200, blank=True)
    search_intent = models.CharField(max_length=120, blank=True)
    primary_keyword = models.CharField(max_length=120, blank=True, db_index=True)
    secondary_keywords = models.CharField(max_length=500, blank=True)
    topic = models.CharField(max_length=120, blank=True, db_index=True)
    category = models.ForeignKey(ContentCategory, null=True, blank=True, on_delete=models.SET_NULL, related_name='content_items')
    tags = models.ManyToManyField(ContentTag, blank=True, related_name='content_items')
    author = models.CharField(max_length=120, blank=True)
    assigned_to = models.CharField(max_length=120, blank=True)
    priority = models.CharField(max_length=12, choices=PRIORITY_CHOICES, default='Medium', db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Idea', db_index=True)
    target_publication_date = models.DateField(null=True, blank=True, db_index=True)
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)
    publication_url = models.URLField(max_length=500, blank=True)
    campaign = models.ForeignKey(Campaign, null=True, blank=True, on_delete=models.SET_NULL, related_name='content_items')
    social_posts = models.ManyToManyField(SocialPost, blank=True, related_name='content_items')
    seo_title = models.CharField(max_length=160, blank=True)
    meta_description = models.TextField(max_length=360, blank=True)
    canonical_url = models.URLField(max_length=500, blank=True)
    og_title = models.CharField(max_length=160, blank=True)
    og_description = models.TextField(max_length=360, blank=True)
    og_image_alt = models.CharField(max_length=200, blank=True)
    heading_structure = models.TextField(blank=True)
    internal_links = models.TextField(blank=True)
    image_alt_text = models.TextField(blank=True)
    cta = models.CharField(max_length=300, blank=True)
    seo_notes = models.TextField(blank=True)
    internal_notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='marketing_content')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-created_at',)
        indexes = [
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['content_type', '-created_at']),
            models.Index(fields=['priority', 'status']),
            models.Index(fields=['target_publication_date', 'status']),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.content_key:
            self.content_key = f'CNT-{uuid.uuid4().hex[:10].upper()}'
        if not self.slug:
            self.slug = slugify(self.title)[:180] or f'content-{uuid.uuid4().hex[:8]}'
        super().save(*args, **kwargs)

    @property
    def body_text(self):
        return ' '.join((self.body or '').split())

    @property
    def word_count(self):
        return len(self.body_text.split()) if self.body_text else 0

    @property
    def reading_time(self):
        return max(1, (self.word_count + 224) // 225) if self.word_count else 0

    @property
    def is_overdue(self):
        if not self.target_publication_date or self.status in {'Published', 'Archived'}:
            return False
        return self.target_publication_date < timezone.localdate()

    def seo_checklist(self):
        checks = {
            'primary_keyword': bool(self.primary_keyword.strip()),
            'seo_title': bool(self.seo_title.strip()),
            'meta_description': bool(self.meta_description.strip()),
            'url_slug': bool(self.slug.strip()) and self.slug != slugify(self.title)[:180],
            'heading_structure': bool(self.heading_structure.strip()),
            'internal_links': bool(self.internal_links.strip()),
            'image_alt_text': bool(self.image_alt_text.strip()),
            'content_preview': bool(self.body_text),
            'cta': bool(self.cta.strip()),
        }
        return checks


class ContentIdea(models.Model):
    SOURCE_CHOICES = IDEA_SOURCES
    TYPE_CHOICES = CONTENT_MARKETING_TYPES
    PRIORITY_CHOICES = CONTENT_PRIORITIES

    idea_key = models.CharField(max_length=32, unique=True, editable=False, db_index=True)
    title = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    topic = models.CharField(max_length=120, blank=True, db_index=True)
    category = models.ForeignKey(ContentCategory, null=True, blank=True, on_delete=models.SET_NULL, related_name='ideas')
    target_audience = models.CharField(max_length=200, blank=True)
    potential_keywords = models.CharField(max_length=500, blank=True)
    content_type = models.CharField(max_length=24, choices=TYPE_CHOICES, default='Blog Post', db_index=True)
    priority = models.CharField(max_length=12, choices=PRIORITY_CHOICES, default='Medium', db_index=True)
    notes = models.TextField(blank=True)
    source = models.CharField(max_length=24, choices=SOURCE_CHOICES, default='Manual', db_index=True)
    is_used = models.BooleanField(default=False, db_index=True)
    used_at = models.DateTimeField(null=True, blank=True)
    converted_content = models.ForeignKey(MarketingContent, null=True, blank=True, on_delete=models.SET_NULL, related_name='source_ideas')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='content_ideas')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-created_at',)
        indexes = [
            models.Index(fields=['is_used', '-created_at']),
            models.Index(fields=['source', '-created_at']),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.idea_key:
            self.idea_key = f'IDEA-{uuid.uuid4().hex[:10].upper()}'
        super().save(*args, **kwargs)


class ContentBrief(models.Model):
    brief_key = models.CharField(max_length=32, unique=True, editable=False, db_index=True)
    content = models.ForeignKey(MarketingContent, null=True, blank=True, on_delete=models.CASCADE, related_name='briefs')
    working_title = models.CharField(max_length=180)
    objective = models.TextField(blank=True)
    target_audience = models.CharField(max_length=200, blank=True)
    audience_pain_points = models.TextField(blank=True)
    search_intent = models.CharField(max_length=120, blank=True)
    primary_keyword = models.CharField(max_length=120, blank=True)
    secondary_keywords = models.CharField(max_length=500, blank=True)
    topic = models.CharField(max_length=120, blank=True)
    proposed_slug = models.SlugField(max_length=180, blank=True)
    suggested_headings = models.TextField(blank=True)
    outline = models.TextField(blank=True)
    questions_to_answer = models.TextField(blank=True)
    internal_links = models.TextField(blank=True)
    external_references = models.TextField(blank=True)
    cta = models.CharField(max_length=300, blank=True)
    content_type = models.CharField(max_length=24, choices=CONTENT_MARKETING_TYPES, default='Blog Post', db_index=True)
    desired_length = models.CharField(max_length=80, blank=True)
    competitor_urls = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    is_reusable = models.BooleanField(default=False, db_index=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='content_briefs')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return self.working_title

    def save(self, *args, **kwargs):
        if not self.brief_key:
            self.brief_key = f'BRF-{uuid.uuid4().hex[:10].upper()}'
        super().save(*args, **kwargs)


class ContentTemplate(models.Model):
    template_key = models.CharField(max_length=32, unique=True, editable=False, db_index=True)
    name = models.CharField(max_length=150, unique=True)
    content_type = models.CharField(max_length=24, choices=CONTENT_MARKETING_TYPES, default='Blog Post', db_index=True)
    structure = models.TextField(blank=True)
    headings = models.TextField(blank=True)
    brief_fields = models.TextField(blank=True)
    cta = models.CharField(max_length=300, blank=True)
    seo_checklist = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='content_templates')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('name',)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.template_key:
            self.template_key = f'CTPL-{uuid.uuid4().hex[:10].upper()}'
        super().save(*args, **kwargs)


class ContentRefreshTask(models.Model):
    STATUS_CHOICES = REFRESH_STATUSES
    PRIORITY_CHOICES = CONTENT_PRIORITIES

    refresh_key = models.CharField(max_length=32, unique=True, editable=False, db_index=True)
    content = models.ForeignKey(MarketingContent, on_delete=models.CASCADE, related_name='refresh_tasks')
    reason = models.TextField(blank=True)
    due_date = models.DateField(null=True, blank=True, db_index=True)
    priority = models.CharField(max_length=12, choices=PRIORITY_CHOICES, default='Medium', db_index=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='Pending', db_index=True)
    update_notes = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='content_refresh_tasks')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('due_date', '-created_at')

    def __str__(self):
        return f'Refresh: {self.content.title}'

    def save(self, *args, **kwargs):
        if not self.refresh_key:
            self.refresh_key = f'REF-{uuid.uuid4().hex[:10].upper()}'
        super().save(*args, **kwargs)


class ConversionGoal(models.Model):
    GOAL_TYPE_CHOICES = GOAL_TYPES
    STATUS_CHOICES = GOAL_STATUSES
    EVENT_TYPE_BY_GOAL = {
        'Page Visit': 'page_visit',
        'CTA Click': 'cta_click',
        'Form Submission': 'form_submission',
        'Custom Event': 'custom_event',
        'Download': 'download',
        'External Link Click': 'external_link_click',
    }

    goal_key = models.CharField(max_length=32, unique=True, editable=False, db_index=True)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    goal_type = models.CharField(max_length=24, choices=GOAL_TYPE_CHOICES, default='CTA Click', db_index=True)
    event_name = models.CharField(max_length=80, blank=True, db_index=True)
    target_page = models.CharField(max_length=500, blank=True)
    target_url = models.URLField(max_length=500, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='Active', db_index=True)
    value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='conversion_goals')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('name',)
        indexes = [
            models.Index(fields=['status', 'goal_type']),
            models.Index(fields=['event_name', 'status']),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.goal_key:
            self.goal_key = f'GOAL-{uuid.uuid4().hex[:10].upper()}'
        self.event_name = ' '.join(str(self.event_name or '').split()).lower()[:80]
        self.target_page = ' '.join(str(self.target_page or '').split())[:500]
        super().save(*args, **kwargs)

    def clean(self):
        if self.goal_type != 'Page Visit' and not self.event_name:
            raise ValidationError({'event_name': 'Enter an event name for this goal type.'})
        if self.goal_type == 'Page Visit' and not (self.target_page or self.target_url):
            raise ValidationError({'target_page': 'Enter a target page or URL for a page visit goal.'})

    @staticmethod
    def _path_value(value):
        if not value:
            return ''
        parsed = urlsplit(str(value))
        if parsed.scheme in {'http', 'https'}:
            value = parsed.path
        return str(value).split('?', 1)[0].split('#', 1)[0].rstrip('/') or '/'

    def matches(self, event_name='', event_type='', path=''):
        if self.status != 'Active':
            return False
        normalized_name = ' '.join(str(event_name or '').split()).lower()
        if self.goal_type == 'Page Visit':
            target = self._path_value(self.target_page or self.target_url)
            return bool(target) and self._path_value(path) == target
        if normalized_name != self.event_name:
            return False
        expected_type = self.EVENT_TYPE_BY_GOAL.get(self.goal_type)
        return not expected_type or not event_type or event_type == expected_type


class ConversionEvent(models.Model):
    EVENT_TYPE_CHOICES = (
        ('cta_click', 'CTA Click'),
        ('form_submission', 'Form Submission'),
        ('newsletter_signup', 'Newsletter Signup'),
        ('contact_request', 'Contact Request'),
        ('lead_generated', 'Lead Generated'),
        ('download', 'Download'),
        ('external_link_click', 'External Link Click'),
        ('phone_click', 'Phone Click'),
        ('email_click', 'Email Click'),
        ('page_visit', 'Page Visit'),
        ('custom_event', 'Custom Event'),
    )

    event_key = models.CharField(max_length=32, unique=True, editable=False, db_index=True)
    session = models.ForeignKey(AnalyticsSession, on_delete=models.CASCADE, related_name='conversion_events')
    visitor = models.ForeignKey(Visitor, on_delete=models.CASCADE, related_name='conversion_events')
    goal = models.ForeignKey(ConversionGoal, null=True, blank=True, on_delete=models.SET_NULL, related_name='events')
    name = models.CharField(max_length=80, db_index=True)
    event_type = models.CharField(max_length=24, choices=EVENT_TYPE_CHOICES, default='custom_event', db_index=True)
    description = models.CharField(max_length=300, blank=True)
    category = models.CharField(max_length=120, blank=True, db_index=True)
    source_label = models.CharField(max_length=120, blank=True)
    path = models.CharField(max_length=500, blank=True, db_index=True)
    occurred_at = models.DateTimeField(default=timezone.now, db_index=True)
    dedupe_key = models.CharField(max_length=120, db_index=True)
    value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    source_category = models.CharField(max_length=32, default='Direct', db_index=True)
    utm_source = models.CharField(max_length=120, blank=True, db_index=True)
    utm_medium = models.CharField(max_length=120, blank=True, db_index=True)
    utm_campaign = models.CharField(max_length=120, blank=True, db_index=True)
    utm_term = models.CharField(max_length=120, blank=True)
    utm_content = models.CharField(max_length=120, blank=True)
    device_category = models.CharField(max_length=16, default='Desktop', db_index=True)
    landing_path = models.CharField(max_length=500, blank=True, db_index=True)

    class Meta:
        ordering = ('-occurred_at',)
        constraints = [
            models.UniqueConstraint(fields=['session', 'dedupe_key'], name='unique_conversion_per_session'),
        ]
        indexes = [
            models.Index(fields=['name', '-occurred_at']),
            models.Index(fields=['event_type', '-occurred_at']),
            models.Index(fields=['goal', '-occurred_at']),
            models.Index(fields=['path', '-occurred_at']),
            models.Index(fields=['source_category', '-occurred_at']),
            models.Index(fields=['utm_campaign', '-occurred_at']),
            models.Index(fields=['device_category', '-occurred_at']),
        ]

    def __str__(self):
        return f'{self.name} at {self.occurred_at:%Y-%m-%d %H:%M}'

    def save(self, *args, **kwargs):
        if not self.event_key:
            self.event_key = f'EVT-{uuid.uuid4().hex[:10].upper()}'
        super().save(*args, **kwargs)

    @property
    def privacy_safe_visitor(self):
        return self.visitor.visitor_key[:12]

    @property
    def privacy_safe_session(self):
        return self.session.session_key[:12]


class ConversionFunnel(models.Model):
    STATUS_CHOICES = FUNNEL_STATUSES

    funnel_key = models.CharField(max_length=32, unique=True, editable=False, db_index=True)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='Active', db_index=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='conversion_funnels')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('name',)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.funnel_key:
            self.funnel_key = f'FUN-{uuid.uuid4().hex[:10].upper()}'
        super().save(*args, **kwargs)


class ConversionFunnelStep(models.Model):
    STEP_TYPE_CHOICES = FUNNEL_STEP_TYPES

    step_key = models.CharField(max_length=32, unique=True, editable=False, db_index=True)
    funnel = models.ForeignKey(ConversionFunnel, on_delete=models.CASCADE, related_name='steps')
    order = models.PositiveSmallIntegerField(default=1, db_index=True)
    label = models.CharField(max_length=150)
    step_type = models.CharField(max_length=16, choices=STEP_TYPE_CHOICES, default='conversion', db_index=True)
    event_name = models.CharField(max_length=80, blank=True)
    target_path = models.CharField(max_length=500, blank=True)
    goal = models.ForeignKey(ConversionGoal, null=True, blank=True, on_delete=models.SET_NULL, related_name='funnel_steps')

    class Meta:
        ordering = ('order', 'step_key')
        constraints = [
            models.UniqueConstraint(fields=['funnel', 'order'], name='unique_funnel_step_order'),
        ]

    def __str__(self):
        return f'{self.order}. {self.label}'

    def save(self, *args, **kwargs):
        if not self.step_key:
            self.step_key = f'STEP-{uuid.uuid4().hex[:10].upper()}'
        self.event_name = ' '.join(str(self.event_name or '').split()).lower()[:80]
        self.target_path = ' '.join(str(self.target_path or '').split())[:500]
        super().save(*args, **kwargs)


class TrackingRule(models.Model):
    STATUS_CHOICES = TRACKING_RULE_STATUSES

    rule_key = models.CharField(max_length=32, unique=True, editable=False, db_index=True)
    name = models.CharField(max_length=150)
    selector = models.CharField(max_length=200, db_index=True)
    event_type = models.CharField(max_length=24, choices=ConversionEvent.EVENT_TYPE_CHOICES, default='cta_click', db_index=True)
    event_name = models.CharField(max_length=80, db_index=True)
    target_path = models.CharField(max_length=500, blank=True)
    goal = models.ForeignKey(ConversionGoal, null=True, blank=True, on_delete=models.SET_NULL, related_name='tracking_rules')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='Active', db_index=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='tracking_rules')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('name',)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.rule_key:
            self.rule_key = f'RULE-{uuid.uuid4().hex[:10].upper()}'
        self.event_name = ' '.join(str(self.event_name or '').split()).lower()[:80]
        super().save(*args, **kwargs)


class CampaignCost(models.Model):
    PERIOD_CHOICES = COST_PERIODS

    campaign = models.OneToOneField(Campaign, on_delete=models.CASCADE, related_name='cost')
    cost_amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default='INR')
    cost_period = models.CharField(max_length=12, choices=PERIOD_CHOICES, default='one_time')
    notes = models.TextField(blank=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='campaign_costs')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('campaign__name',)

    def __str__(self):
        return f'{self.campaign.name} cost'


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
