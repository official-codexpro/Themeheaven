from django import forms

from .models import SEOSettings
from .seo import normalize_domain
from .validators import (
    SAFE_ROBOTS_TXT,
    is_valid_google_token,
    robots_txt_warnings,
    sanitize_google_token,
    sanitize_robots_txt,
    sanitize_text,
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
