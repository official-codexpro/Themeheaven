from urllib.parse import urlsplit

from django import forms

from .campaign_urls import strip_utm_params
from .models import Campaign, PageSEO, SEOSettings
from .seo import normalize_domain
from .validators import (
    SAFE_ROBOTS_TXT,
    is_valid_canonical_url,
    is_valid_google_token,
    robots_txt_warnings,
    sanitize_google_token,
    sanitize_jsonld,
    sanitize_robots_txt,
    sanitize_text,
    validate_jsonld,
)


class SEOSettingsForm(forms.ModelForm):
    remove_default_image = forms.BooleanField(
        required=False,
        label='Remove current image',
        help_text='Clear the current default share image without affecting any other uploads.',
    )

    class Meta:
        model = SEOSettings
        fields = (
            'seo_title',
            'meta_description',
            'meta_keywords',
            'site_name',
            'default_image',
            'index_enabled',
            'follow_enabled',
            'primary_domain',
            'prefer_https',
            'preferred_www',
            'canonical_behavior',
            'trailing_slash_behavior',
            'sitemap_enabled',
            'robots_txt_enabled',
            'robots_txt_content',
            'google_verification_token',
        )
        widgets = {
            'seo_title': forms.TextInput(attrs={
                'class': 'gcseo-input',
                'data-counter': 'title',
                'maxlength': '120',
                'placeholder': 'ThemeHaven — Premium Digital Products',
            }),
            'meta_description': forms.Textarea(attrs={
                'class': 'gcseo-textarea',
                'rows': 4,
                'data-counter': 'description',
                'maxlength': '320',
                'placeholder': 'A concise default description for pages without custom metadata.',
            }),
            'meta_keywords': forms.TextInput(attrs={
                'class': 'gcseo-input',
                'maxlength': '500',
                'placeholder': 'Optional, comma-separated',
            }),
            'site_name': forms.TextInput(attrs={
                'class': 'gcseo-input',
                'maxlength': '120',
                'placeholder': 'ThemeHaven',
            }),
            'default_image': forms.ClearableFileInput(attrs={'class': 'gcseo-file', 'accept': 'image/png,image/jpeg,image/webp'}),
            'primary_domain': forms.TextInput(attrs={
                'class': 'gcseo-input',
                'maxlength': '253',
                'placeholder': 'themehaven.in',
            }),
            'robots_txt_content': forms.Textarea(attrs={
                'class': 'gcseo-code',
                'rows': 14,
                'spellcheck': 'false',
                'data-robots-editor': '',
            }),
            'google_verification_token': forms.TextInput(attrs={
                'class': 'gcseo-input',
                'maxlength': '120',
                'placeholder': 'Paste token or full meta tag',
                'data-verification-input': '',
            }),
        }
        help_texts = {
            'seo_title': 'Recommended: 30–60 characters. Used when a page does not define its own title.',
            'meta_description': 'Recommended: 120–160 characters. Used when a page does not define its own description.',
            'meta_keywords': 'Optional. Modern search engines generally do not use meta keywords as a ranking factor.',
            'site_name': 'Used for metadata and social sharing when a page does not provide its own name.',
            'default_image': 'PNG, JPG, or WebP up to 2 MB. Used as the fallback Open Graph/share image.',
            'index_enabled': 'Default for public pages. Future page-specific settings can override this.',
            'follow_enabled': 'Default for public pages. Future page-specific settings can override this.',
            'prefer_https': 'Generate canonical and absolute URLs over HTTPS.',
            'preferred_www': 'Normalize the configured domain for canonical URLs.',
            'canonical_behavior': 'Canonical tags are metadata only; no redirects are created.',
            'trailing_slash_behavior': 'Applies only to generated canonical URLs, not routing.',
            'robots_txt_enabled': 'Use the custom robots.txt content below. Safe defaults remain active when disabled.',
            'robots_txt_content': 'Dangerous crawl-blocking rules are rejected and must never be applied silently.',
            'google_verification_token': 'Find this token in Google Search Console → Settings → Ownership verification → HTML tag.',
        }

    def clean_seo_title(self):
        return sanitize_text(self.cleaned_data.get('seo_title'), 120)

    def clean_meta_description(self):
        return sanitize_text(self.cleaned_data.get('meta_description'), 320)

    def clean_meta_keywords(self):
        return sanitize_text(self.cleaned_data.get('meta_keywords'), 500)

    def clean_site_name(self):
        return sanitize_text(self.cleaned_data.get('site_name'), 120)

    def clean_primary_domain(self):
        value = sanitize_text(self.cleaned_data.get('primary_domain'), 253)
        if not value:
            return ''
        host = normalize_domain(value)
        if not host:
            raise forms.ValidationError('Enter a domain or absolute URL without paths, query strings, or credentials.')
        return host

    def clean_google_verification_token(self):
        token = sanitize_google_token(self.cleaned_data.get('google_verification_token'))
        if not token:
            return ''
        if not is_valid_google_token(token):
            raise forms.ValidationError('Enter the Google verification token or the full HTML meta tag.')
        return token

    def clean_robots_txt_content(self):
        content = sanitize_robots_txt(self.cleaned_data.get('robots_txt_content'))
        if not content:
            return SAFE_ROBOTS_TXT
        warnings = robots_txt_warnings(content)
        if warnings:
            raise forms.ValidationError(' '.join(warnings))
        return content

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.cleaned_data.get('remove_default_image'):
            if instance.default_image:
                instance.default_image.delete(save=False)
            instance.default_image = None
        if commit:
            instance.save()
        return instance


class PageSEOForm(forms.ModelForm):
    remove_og_image = forms.BooleanField(
        required=False,
        label='Remove current image',
        help_text='Clear this page image and fall back to the configured default.',
    )

    class Meta:
        model = PageSEO
        fields = (
            'seo_title',
            'meta_description',
            'og_title',
            'og_description',
            'og_image',
            'og_image_alt',
            'canonical_override',
            'index_mode',
            'follow_mode',
            'schema_mode',
            'schema_type',
            'schema_json',
        )
        widgets = {
            'seo_title': forms.TextInput(attrs={
                'class': 'gcpage-input',
                'data-page-counter': 'title',
                'maxlength': '120',
            }),
            'meta_description': forms.Textarea(attrs={
                'class': 'gcpage-textarea',
                'rows': 4,
                'data-page-counter': 'description',
                'maxlength': '320',
            }),
            'og_title': forms.TextInput(attrs={
                'class': 'gcpage-input',
                'data-page-og': 'title',
                'maxlength': '120',
            }),
            'og_description': forms.Textarea(attrs={
                'class': 'gcpage-textarea',
                'rows': 3,
                'data-page-og': 'description',
                'maxlength': '320',
            }),
            'og_image': forms.ClearableFileInput(attrs={
                'class': 'gcpage-file',
                'accept': 'image/png,image/jpeg,image/webp',
                'data-page-og': 'image',
            }),
            'og_image_alt': forms.TextInput(attrs={
                'class': 'gcpage-input',
                'data-page-og': 'alt',
                'maxlength': '160',
            }),
            'canonical_override': forms.URLInput(attrs={
                'class': 'gcpage-input',
                'maxlength': '500',
                'placeholder': 'https://example.com/page/',
            }),
            'index_mode': forms.Select(attrs={'class': 'gcpage-select'}),
            'follow_mode': forms.Select(attrs={'class': 'gcpage-select'}),
            'schema_mode': forms.Select(attrs={'class': 'gcpage-select', 'data-page-schema-mode': ''}),
            'schema_type': forms.Select(attrs={'class': 'gcpage-select', 'data-page-schema-type': ''}),
            'schema_json': forms.Textarea(attrs={
                'class': 'gcpage-code',
                'rows': 10,
                'spellcheck': 'false',
                'data-page-schema-json': '',
                'placeholder': '{\n  "@context": "https://schema.org",\n  "@type": "WebPage"\n}',
            }),
        }
        help_texts = {
            'seo_title': 'Recommended: 30–60 characters. Leave blank to use the inherited title.',
            'meta_description': 'Recommended: 120–160 characters. Leave blank to use the inherited description.',
            'og_title': 'Optional. Falls back to this page SEO title, then the inherited title.',
            'og_description': 'Optional. Falls back to this page description, then the inherited description.',
            'og_image': 'PNG, JPG, or WebP up to 2 MB. Leave blank to use the configured default image.',
            'og_image_alt': 'Optional descriptive text for the sharing image.',
            'canonical_override': 'Optional absolute http(s) URL. Automatically generated when blank.',
            'index_mode': 'Inherit uses the Global SEO Settings value. Noindex applies only to this page.',
            'follow_mode': 'Inherit uses the Global SEO Settings value. Nofollow applies only to this page.',
            'schema_mode': 'Generated schema uses only real page data. Custom JSON-LD is validated before saving.',
            'schema_type': 'WebPage is available for all pages. Product is available for product detail pages only.',
            'schema_json': 'Valid JSON object or array only. Other schema types require custom JSON-LD with real page data.',
        }

    def __init__(self, *args, page=None, **kwargs):
        self.page = page
        super().__init__(*args, **kwargs)
        self.fields['index_mode'].required = False
        self.fields['follow_mode'].required = False
        self.fields['schema_mode'].required = False
        self.fields['schema_type'].required = False

    def clean_seo_title(self):
        return sanitize_text(self.cleaned_data.get('seo_title'), 120)

    def clean_meta_description(self):
        return sanitize_text(self.cleaned_data.get('meta_description'), 320)

    def clean_og_title(self):
        return sanitize_text(self.cleaned_data.get('og_title'), 120)

    def clean_og_description(self):
        return sanitize_text(self.cleaned_data.get('og_description'), 320)

    def clean_og_image_alt(self):
        return sanitize_text(self.cleaned_data.get('og_image_alt'), 160)

    def clean_canonical_override(self):
        value = sanitize_text(self.cleaned_data.get('canonical_override'), 500)
        if value and not is_valid_canonical_url(value):
            raise forms.ValidationError('Use a full http(s) URL without credentials, query strings, or fragments.')
        return value

    def clean_schema_type(self):
        value = self.cleaned_data.get('schema_type') or 'webpage'
        mode = self.cleaned_data.get('schema_mode') or 'inherit'
        if mode == 'generated':
            if value not in {'webpage', 'product'}:
                raise forms.ValidationError('Select WebPage or Product for generated schema. Other types require custom JSON-LD.')
            if value == 'product' and not (self.page and self.page.is_product_page):
                raise forms.ValidationError('Product schema is available for product pages only.')
        return value

    def clean_schema_json(self):
        mode = self.cleaned_data.get('schema_mode') or 'inherit'
        value = self.cleaned_data.get('schema_json') or ''
        if mode != 'custom':
            return ''
        validate_jsonld(value)
        return sanitize_jsonld(value)

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.cleaned_data.get('remove_og_image'):
            if instance.og_image:
                instance.og_image.delete(save=False)
            instance.og_image = None
        if not instance.index_mode:
            instance.index_mode = 'inherit'
        if not instance.follow_mode:
            instance.follow_mode = 'inherit'
        if not instance.schema_mode:
            instance.schema_mode = 'inherit'
        if not instance.schema_type:
            instance.schema_type = 'webpage'
        if commit:
            instance.save()
        return instance


class CampaignForm(forms.ModelForm):
    class Meta:
        model = Campaign
        fields = (
            'name',
            'description',
            'objective',
            'destination_url',
            'utm_source',
            'utm_medium',
            'utm_campaign',
            'utm_term',
            'utm_content',
            'start_date',
            'end_date',
            'status',
            'notes',
        )
        widgets = {
            'name': forms.TextInput(attrs={'class': 'gccamp-input', 'placeholder': 'Summer Sale 2026', 'maxlength': '150'}),
            'description': forms.Textarea(attrs={'class': 'gccamp-textarea', 'rows': 3, 'maxlength': '1000'}),
            'objective': forms.Select(attrs={'class': 'gccamp-select'}),
            'destination_url': forms.URLInput(attrs={
                'class': 'gccamp-input',
                'data-builder': 'destination',
                'placeholder': 'https://themehaven.in/products/wordpress/',
            }),
            'utm_source': forms.TextInput(attrs={
                'class': 'gccamp-input',
                'data-builder': 'source',
                'placeholder': 'google',
                'maxlength': '120',
            }),
            'utm_medium': forms.TextInput(attrs={
                'class': 'gccamp-input',
                'data-builder': 'medium',
                'placeholder': 'cpc',
                'maxlength': '120',
            }),
            'utm_campaign': forms.TextInput(attrs={
                'class': 'gccamp-input',
                'data-builder': 'campaign',
                'placeholder': 'summer_sale_2026',
                'maxlength': '120',
            }),
            'utm_term': forms.TextInput(attrs={
                'class': 'gccamp-input',
                'data-builder': 'term',
                'placeholder': 'premium wordpress theme',
                'maxlength': '120',
            }),
            'utm_content': forms.TextInput(attrs={
                'class': 'gccamp-input',
                'data-builder': 'content',
                'placeholder': 'hero_button',
                'maxlength': '120',
            }),
            'start_date': forms.DateInput(attrs={'class': 'gccamp-input', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'gccamp-input', 'type': 'date'}),
            'status': forms.Select(attrs={'class': 'gccamp-select'}),
            'notes': forms.Textarea(attrs={'class': 'gccamp-textarea', 'rows': 3}),
        }
        help_texts = {
            'destination_url': 'Full http(s) page URL. Existing query parameters are preserved.',
            'utm_campaign': 'Used to attribute visits in Analytics. Must be unique across campaigns.',
            'utm_term': 'Optional keyword, mainly for paid search campaigns.',
            'utm_content': 'Optional label for ads, creatives, buttons, or variations.',
        }

    def clean_name(self):
        return sanitize_text(self.cleaned_data.get('name'), 150)

    def clean_description(self):
        return sanitize_text(self.cleaned_data.get('description'), 1000)

    def clean_objective(self):
        return self.cleaned_data.get('objective') or 'traffic'

    def clean_destination_url(self):
        value = strip_utm_params(self.cleaned_data.get('destination_url'))
        parsed = urlsplit(value)
        if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
            raise forms.ValidationError('Use a full http(s) URL with a domain.')
        return value

    def clean_utm_source(self):
        value = sanitize_text(self.cleaned_data.get('utm_source'), 120)
        if not value:
            raise forms.ValidationError('UTM Source is required.')
        return value

    def clean_utm_medium(self):
        value = sanitize_text(self.cleaned_data.get('utm_medium'), 120)
        if not value:
            raise forms.ValidationError('UTM Medium is required.')
        return value

    def clean_utm_campaign(self):
        value = sanitize_text(self.cleaned_data.get('utm_campaign'), 120)
        if not value:
            raise forms.ValidationError('UTM Campaign is required.')
        queryset = Campaign.objects.filter(utm_campaign__iexact=value)
        if self.instance and self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise forms.ValidationError('A campaign with this UTM Campaign already exists.')
        return value

    def clean_utm_term(self):
        return sanitize_text(self.cleaned_data.get('utm_term'), 120)

    def clean_utm_content(self):
        return sanitize_text(self.cleaned_data.get('utm_content'), 120)

    def clean_notes(self):
        return sanitize_text(self.cleaned_data.get('notes'), 2000)

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('start_date')
        end = cleaned.get('end_date')
        if start and end and end < start:
            self.add_error('end_date', 'End date must be on or after the start date.')
        return cleaned
