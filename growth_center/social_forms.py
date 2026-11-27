from datetime import datetime

from django import forms
from django.utils import timezone

from .campaign_urls import strip_utm_params
from .models import Campaign, SocialMediaAsset, SocialPost, SocialPostPlatform, SocialPostTemplate
from .social_platforms import PLATFORMS, PLATFORM_BY_KEY, STATUSES
from .social_validators import detect_media_type, reset_upload
from .validators import sanitize_text
from PIL import Image, UnidentifiedImageError

WORKFLOW_ACTIONS = (
    ('save_draft', 'Save Draft'),
    ('mark_ready', 'Mark Ready'),
    ('schedule', 'Schedule'),
)


class SocialPostForm(forms.Form):
    WORKFLOW_CHOICES = WORKFLOW_ACTIONS

    title = forms.CharField(max_length=150, widget=forms.TextInput(attrs={'class': 'gcsmm-input', 'placeholder': 'Internal post title'}))
    content = forms.CharField(widget=forms.Textarea(attrs={'class': 'gcsmm-input gcsmm-content', 'rows': 8, 'data-content-editor': ''}))
    content_type = forms.ChoiceField(choices=SocialPost.CONTENT_TYPE_CHOICES, widget=forms.Select(attrs={'class': 'gcsmm-input'}))
    platforms = forms.MultipleChoiceField(
        choices=tuple((platform['key'], platform['label']) for platform in PLATFORMS),
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'gcsmm-platform-checks'}),
    )
    campaign = forms.ModelChoiceField(queryset=Campaign.objects.none(), required=False, widget=forms.Select(attrs={'class': 'gcsmm-input'}))
    media = forms.ModelMultipleChoiceField(queryset=SocialMediaAsset.objects.none(), required=False, widget=forms.CheckboxSelectMultiple(attrs={'class': 'gcsmm-media-checks'}))
    destination_url = forms.URLField(required=False, widget=forms.URLInput(attrs={'class': 'gcsmm-input', 'data-tracking': 'destination', 'placeholder': 'https://themehaven.in/'}))
    utm_source = forms.CharField(max_length=120, required=False, widget=forms.TextInput(attrs={'class': 'gcsmm-input', 'data-tracking': 'source'}))
    utm_medium = forms.CharField(max_length=120, required=False, widget=forms.TextInput(attrs={'class': 'gcsmm-input', 'data-tracking': 'medium'}))
    utm_campaign = forms.CharField(max_length=120, required=False, widget=forms.TextInput(attrs={'class': 'gcsmm-input', 'data-tracking': 'campaign'}))
    utm_term = forms.CharField(max_length=120, required=False, widget=forms.TextInput(attrs={'class': 'gcsmm-input', 'data-tracking': 'term'}))
    utm_content = forms.CharField(max_length=120, required=False, widget=forms.TextInput(attrs={'class': 'gcsmm-input', 'data-tracking': 'content'}))
    hashtags = forms.CharField(max_length=500, required=False, widget=forms.Textarea(attrs={'class': 'gcsmm-input', 'rows': 2, 'data-hashtags': ''}))
    notes = forms.CharField(max_length=2000, required=False, widget=forms.Textarea(attrs={'class': 'gcsmm-input', 'rows': 3}))
    status = forms.ChoiceField(choices=STATUSES, widget=forms.Select(attrs={'class': 'gcsmm-input'}))
    scheduled_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'class': 'gcsmm-input', 'type': 'date'}))
    scheduled_time = forms.TimeField(required=False, widget=forms.TimeInput(attrs={'class': 'gcsmm-input', 'type': 'time'}))
    workflow_action = forms.ChoiceField(choices=WORKFLOW_ACTIONS, widget=forms.HiddenInput())

    def __init__(self, *args, instance=None, workflow_action='save_draft', **kwargs):
        self.instance = instance
        self.workflow_action = workflow_action
        super().__init__(*args, **kwargs)
        self.fields['campaign'].queryset = Campaign.objects.all()
        self.fields['media'].queryset = SocialMediaAsset.objects.all()
        self.warnings = []

        for platform in PLATFORMS:
            key = platform['key']
            self.fields[f'platform_content_{key}'] = forms.CharField(
                required=False,
                max_length=max(platform['limit'], 1),
                widget=forms.Textarea(attrs={
                    'class': 'gcsmm-input gcsmm-platform-content',
                    'rows': 5,
                    'data-platform-content': key,
                    'maxlength': platform['limit'],
                }),
            )
            if platform['title_limit']:
                self.fields[f'platform_title_{key}'] = forms.CharField(
                    required=False,
                    max_length=platform['title_limit'],
                    widget=forms.TextInput(attrs={'class': 'gcsmm-input', 'maxlength': platform['title_limit']}),
                )
            self.fields[f'platform_time_{key}'] = forms.TimeField(
                required=False,
                widget=forms.TimeInput(attrs={'class': 'gcsmm-input', 'type': 'time', 'data-platform-time': key}),
            )

        if self.is_bound:
            if self.data.get('workflow_action') in dict(WORKFLOW_ACTIONS):
                self.workflow_action = self.data['workflow_action']
            return

        if not instance:
            self.initial.setdefault('content_type', 'post')
            self.initial.setdefault('status', 'Draft')
            self.initial.setdefault('workflow_action', 'save_draft')
            return

        local_start = timezone.localtime(instance.scheduled_at) if instance.scheduled_at else None
        self.initial.update({
            'title': instance.title,
            'content': instance.content,
            'content_type': instance.content_type,
            'campaign': instance.campaign_id,
            'media': list(instance.media.values_list('id', flat=True)),
            'destination_url': instance.destination_url,
            'utm_source': instance.utm_source,
            'utm_medium': instance.utm_medium,
            'utm_campaign': instance.utm_campaign,
            'utm_term': instance.utm_term,
            'utm_content': instance.utm_content,
            'hashtags': instance.hashtags,
            'notes': instance.notes,
            'status': instance.status,
            'scheduled_date': local_start.date() if local_start else None,
            'scheduled_time': local_start.time() if local_start else None,
            'workflow_action': 'save_draft',
            'platforms': instance.platform_keys,
        })
        for entry in instance.platform_entries.all():
            key = entry.platform
            self.initial[f'platform_content_{key}'] = entry.content
            if PLATFORM_BY_KEY.get(key, {}).get('title_limit'):
                self.initial[f'platform_title_{key}'] = entry.platform_title
            if entry.scheduled_at:
                self.initial[f'platform_time_{key}'] = timezone.localtime(entry.scheduled_at).time()

    def clean(self):
        cleaned = super().clean()
        platforms = cleaned.get('platforms') or []
        if not platforms:
            self.add_error('platforms', 'Select at least one platform.')

        cleaned['title'] = sanitize_text(cleaned.get('title'), 150)
        if not cleaned['title']:
            self.add_error('title', 'Enter an internal post title.')

        base_content = sanitize_text(cleaned.get('content'), 10000)
        if not base_content:
            self.add_error('content', 'Enter post content.')
        cleaned['content'] = base_content

        target_status = dict(STATUSES)[cleaned.get('status') or 'Draft']
        if self.workflow_action == 'save_draft':
            target_status = 'Draft'
        elif self.workflow_action == 'mark_ready':
            target_status = 'Ready'
        elif self.workflow_action == 'schedule':
            target_status = 'Scheduled'
        cleaned['target_status'] = target_status

        scheduled_date = cleaned.get('scheduled_date')
        scheduled_time = cleaned.get('scheduled_time')
        if bool(scheduled_date) != bool(scheduled_time):
            self.add_error('scheduled_date', 'Select both a date and a time, or leave both empty.')
        cleaned['scheduled_at'] = None
        if scheduled_date and scheduled_time:
            cleaned['scheduled_at'] = timezone.make_aware(
                datetime.combine(scheduled_date, scheduled_time),
                timezone.get_current_timezone(),
            )
        if target_status == 'Scheduled' and not cleaned['scheduled_at']:
            self.add_error('scheduled_date', 'Choose a date and time before scheduling.')
        if target_status == 'Scheduled' and cleaned['scheduled_at'] and cleaned['scheduled_at'] <= timezone.now():
            self.add_error('scheduled_date', 'Scheduled posts need a future date and time.')

        cleaned['platform_values'] = {}
        for key in platforms:
            platform = PLATFORM_BY_KEY.get(key)
            if not platform:
                self.add_error('platforms', 'Unknown platform selected.')
                continue
            content = sanitize_text(self.data.get(f'platform_content_{key}') or '', platform['limit']) or base_content
            if len(content) > platform['limit']:
                self.add_error(f'platform_content_{key}', f'{platform["label"]} allows {platform["limit"]} characters.')
            title = sanitize_text(self.data.get(f'platform_title_{key}') or '', platform['title_limit'] or 120)
            if platform['title_limit'] and len(title) > platform['title_limit']:
                self.add_error(f'platform_title_{key}', f'{platform["label"]} titles allow {platform["title_limit"]} characters.')
            if platform['title_limit'] and not title:
                title = cleaned['title'][:platform['title_limit']]
            cleaned['platform_values'][key] = {
                'content': content,
                'title': title if platform['title_limit'] else '',
                'time': cleaned.get(f'platform_time_{key}'),
            }

        media = cleaned.get('media') or []
        for key in platforms:
            platform = PLATFORM_BY_KEY.get(key)
            if not platform:
                continue
            if key == 'youtube' and not any(asset.media_type == 'Video' for asset in media):
                self.warnings.append('YouTube posts normally need a video attachment.')
            elif key != 'youtube' and not media:
                self.warnings.append(f'{platform["label"]} posts usually perform better with an image or video.')
                break

        cleaned['hashtags'] = sanitize_text(cleaned.get('hashtags'), 500)
        cleaned['notes'] = sanitize_text(cleaned.get('notes'), 2000)
        cleaned['destination_url'] = strip_utm_params(cleaned.get('destination_url') or '')
        cleaned['utm_source'] = sanitize_text(cleaned.get('utm_source'), 120)
        cleaned['utm_medium'] = sanitize_text(cleaned.get('utm_medium'), 120)
        cleaned['utm_campaign'] = sanitize_text(cleaned.get('utm_campaign'), 120)
        cleaned['utm_term'] = sanitize_text(cleaned.get('utm_term'), 120)
        cleaned['utm_content'] = sanitize_text(cleaned.get('utm_content'), 120)
        return cleaned

    def save(self, commit=True):
        cleaned = self.cleaned_data
        post = self.instance or SocialPost()
        post.title = cleaned['title']
        post.content = cleaned['content']
        post.content_type = cleaned['content_type']
        post.status = cleaned['target_status']
        post.scheduled_at = cleaned['scheduled_at']
        post.campaign = cleaned.get('campaign')
        post.destination_url = cleaned['destination_url']
        post.utm_source = cleaned['utm_source']
        post.utm_medium = cleaned['utm_medium']
        post.utm_campaign = cleaned['utm_campaign'] or (post.campaign.utm_campaign if post.campaign else '')
        post.utm_term = cleaned['utm_term']
        post.utm_content = cleaned['utm_content']
        post.hashtags = cleaned['hashtags']
        post.notes = cleaned['notes']
        if not post.pk:
            post.created_by = getattr(self, 'created_by', None)
        if commit:
            post.save()
            post.media.set(cleaned.get('media') or [])

            selected = set(cleaned['platform_values'])
            post.platform_entries.exclude(platform__in=selected).delete()
            for key, values in cleaned['platform_values'].items():
                scheduled_at = None
                if cleaned['scheduled_at']:
                    override_time = values['time']
                    scheduled_at = timezone.make_aware(
                        datetime.combine(cleaned['scheduled_at'].date(), override_time or cleaned['scheduled_at'].time()),
                        timezone.get_current_timezone(),
                    )
                entry, _created = SocialPostPlatform.objects.update_or_create(
                    post=post,
                    platform=key,
                    defaults={
                        'content': values['content'],
                        'platform_title': values['title'],
                        'status': cleaned['target_status'],
                        'scheduled_at': scheduled_at if cleaned['target_status'] == 'Scheduled' else None,
                    },
                )
                if cleaned['target_status'] != 'Scheduled':
                    entry.scheduled_at = None
                    entry.save(update_fields=['scheduled_at'])
        return post


class SocialMediaAssetForm(forms.ModelForm):
    class Meta:
        model = SocialMediaAsset
        fields = ('title', 'media_type', 'file', 'alt_text')
        widgets = {
            'title': forms.TextInput(attrs={'class': 'gcsmm-input', 'maxlength': '150'}),
            'media_type': forms.Select(attrs={'class': 'gcsmm-input'}),
            'file': forms.ClearableFileInput(attrs={'class': 'gcsmm-file', 'accept': 'image/*,video/mp4,video/webm,video/quicktime'}),
            'alt_text': forms.TextInput(attrs={'class': 'gcsmm-input', 'maxlength': '200'}),
        }

    def clean_title(self):
        return sanitize_text(self.cleaned_data.get('title'), 150)

    def clean_alt_text(self):
        return sanitize_text(self.cleaned_data.get('alt_text'), 200)

    def clean(self):
        cleaned = super().clean()
        upload = cleaned.get('file')
        media_type = cleaned.get('media_type')
        if not upload:
            return cleaned
        detected = detect_media_type(upload)
        if detected and detected != media_type:
            self.add_error('media_type', f'This file is a {detected.lower()}, not a {media_type.lower()}.')
        if media_type == 'Image':
            try:
                position = upload.tell()
                image = Image.open(upload)
                cleaned['width'], cleaned['height'] = image.size
                reset_upload(upload)
                upload.seek(position)
            except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
                self.add_error('file', 'The image file could not be read.')
        else:
            cleaned['width'] = None
            cleaned['height'] = None
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.width = self.cleaned_data.get('width')
        instance.height = self.cleaned_data.get('height')
        if commit:
            instance.save()
        return instance


class SocialPostTemplateForm(forms.ModelForm):
    class Meta:
        model = SocialPostTemplate
        fields = ('name', 'kind', 'platform', 'content', 'hashtags')
        widgets = {
            'name': forms.TextInput(attrs={'class': 'gcsmm-input', 'maxlength': '120'}),
            'kind': forms.Select(attrs={'class': 'gcsmm-input'}),
            'platform': forms.Select(attrs={'class': 'gcsmm-input'}),
            'content': forms.Textarea(attrs={'class': 'gcsmm-input', 'rows': 4}),
            'hashtags': forms.TextInput(attrs={'class': 'gcsmm-input', 'maxlength': '500'}),
        }

    def clean_name(self):
        return sanitize_text(self.cleaned_data.get('name'), 120)

    def clean_content(self):
        return sanitize_text(self.cleaned_data.get('content'), 10000)

    def clean_hashtags(self):
        return sanitize_text(self.cleaned_data.get('hashtags'), 500)
