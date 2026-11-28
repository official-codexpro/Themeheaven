from django import forms

from .content_constants import (
    CONTENT_CALENDAR_VIEWS,
    CONTENT_PRIORITIES,
    CONTENT_SECTIONS,
    CONTENT_SORTS,
    CONTENT_STATUSES,
    CONTENT_TYPES,
    IDEA_SOURCES,
    REFRESH_STATUSES,
)
from .models import (
    Campaign,
    ContentBrief,
    ContentCategory,
    ContentIdea,
    ContentRefreshTask,
    ContentTag,
    ContentTemplate,
    MarketingContent,
)
from .validators import sanitize_text

INPUT = 'gcm-input'
TEXTAREA = 'gcm-input gcm-textarea'
RANGE_CHOICES = (
    ('7d', 'Last 7 days'),
    ('30d', 'Last 30 days'),
    ('90d', 'Last 90 days'),
    ('all', 'All time'),
)


def _widgets(mapping):
    return {field: forms.TextInput(attrs={'class': INPUT}) for field in mapping}


class ContentItemForm(forms.ModelForm):
    publication_confirmed = forms.BooleanField(
        required=False,
        label='I confirm this content is published',
        widget=forms.CheckboxInput(attrs={'class': 'gcm-checkbox'}),
    )

    class Meta:
        model = MarketingContent
        fields = [
            'title', 'slug', 'content_type', 'description', 'brief', 'body',
            'target_audience', 'search_intent', 'primary_keyword', 'secondary_keywords',
            'topic', 'category', 'tags', 'author', 'assigned_to', 'priority', 'status',
            'target_publication_date', 'publication_url', 'campaign', 'seo_title',
            'meta_description', 'canonical_url', 'og_title', 'og_description',
            'og_image_alt', 'heading_structure', 'internal_links', 'image_alt_text',
            'cta', 'seo_notes', 'internal_notes',
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': INPUT, 'placeholder': 'Content title', 'data-slug-source': ''}),
            'slug': forms.TextInput(attrs={'class': INPUT, 'placeholder': 'url-friendly-slug'}),
            'content_type': forms.Select(attrs={'class': INPUT}),
            'description': forms.Textarea(attrs={'class': TEXTAREA, 'rows': 3}),
            'brief': forms.Textarea(attrs={'class': TEXTAREA, 'rows': 5}),
            'body': forms.Textarea(attrs={'class': f'{TEXTAREA} gcm-content-editor', 'rows': 16, 'data-content-editor': ''}),
            'target_audience': forms.TextInput(attrs={'class': INPUT}),
            'search_intent': forms.TextInput(attrs={'class': INPUT}),
            'primary_keyword': forms.TextInput(attrs={'class': INPUT}),
            'secondary_keywords': forms.TextInput(attrs={'class': INPUT}),
            'topic': forms.TextInput(attrs={'class': INPUT}),
            'category': forms.Select(attrs={'class': INPUT}),
            'tags': forms.CheckboxSelectMultiple(attrs={'class': 'gcm-checks'}),
            'author': forms.TextInput(attrs={'class': INPUT}),
            'assigned_to': forms.TextInput(attrs={'class': INPUT}),
            'priority': forms.Select(attrs={'class': INPUT}),
            'status': forms.Select(attrs={'class': INPUT}),
            'target_publication_date': forms.DateInput(attrs={'class': INPUT, 'type': 'date'}),
            'publication_url': forms.URLInput(attrs={'class': INPUT, 'placeholder': 'https://themehaven.in/...'}),
            'campaign': forms.Select(attrs={'class': INPUT}),
            'seo_title': forms.TextInput(attrs={'class': INPUT, 'maxlength': 160, 'data-seo-title': ''}),
            'meta_description': forms.Textarea(attrs={'class': TEXTAREA, 'rows': 3, 'maxlength': 360, 'data-seo-description': ''}),
            'canonical_url': forms.URLInput(attrs={'class': INPUT}),
            'og_title': forms.TextInput(attrs={'class': INPUT}),
            'og_description': forms.Textarea(attrs={'class': TEXTAREA, 'rows': 2}),
            'og_image_alt': forms.TextInput(attrs={'class': INPUT}),
            'heading_structure': forms.Textarea(attrs={'class': f'{TEXTAREA} gcm-monospace', 'rows': 5}),
            'internal_links': forms.Textarea(attrs={'class': f'{TEXTAREA} gcm-monospace', 'rows': 4}),
            'image_alt_text': forms.Textarea(attrs={'class': TEXTAREA, 'rows': 3}),
            'cta': forms.TextInput(attrs={'class': INPUT}),
            'seo_notes': forms.Textarea(attrs={'class': TEXTAREA, 'rows': 3}),
            'internal_notes': forms.Textarea(attrs={'class': TEXTAREA, 'rows': 3}),
        }

    def __init__(self, *args, instance=None, user=None, **kwargs):
        super().__init__(*args, instance=instance, **kwargs)
        self.fields['category'].queryset = ContentCategory.objects.all()
        self.fields['tags'].queryset = ContentTag.objects.all()
        self.fields['campaign'].queryset = Campaign.objects.all()
        self.fields['publication_confirmed'].initial = bool(instance and instance.publication_url)
        self.user = user

    def clean(self):
        cleaned = super().clean()
        limits = {
            'title': 180, 'description': 2000, 'brief': 12000, 'body': 60000,
            'target_audience': 200, 'search_intent': 120, 'primary_keyword': 120,
            'secondary_keywords': 500, 'topic': 120, 'author': 120, 'assigned_to': 120,
            'seo_title': 160, 'meta_description': 360, 'og_title': 160,
            'og_description': 360, 'og_image_alt': 200, 'heading_structure': 6000,
            'internal_links': 6000, 'image_alt_text': 6000, 'cta': 300,
            'seo_notes': 4000, 'internal_notes': 4000,
        }
        for field, limit in limits.items():
            cleaned[field] = sanitize_text(cleaned.get(field), limit)

        if not cleaned.get('title'):
            self.add_error('title', 'Enter a content title.')

        status = cleaned.get('status')
        if status == 'Scheduled' and not cleaned.get('target_publication_date'):
            self.add_error('target_publication_date', 'Select a publication date for scheduled content.')

        if status == 'Published':
            if not cleaned.get('publication_url'):
                self.add_error('publication_url', 'Add a publication URL before marking content as published.')
            if not cleaned.get('publication_confirmed'):
                self.add_error('publication_confirmed', 'Confirm that this content is actually published.')

        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        if instance.status == 'Published' and instance.publication_url and self.cleaned_data.get('publication_confirmed'):
            if self.instance._state.adding or not self.instance.published_at:
                from django.utils import timezone
                instance.published_at = timezone.now()
        elif instance.status != 'Published':
            instance.published_at = None
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class ContentIdeaForm(forms.ModelForm):
    class Meta:
        model = ContentIdea
        fields = [
            'title', 'description', 'topic', 'category', 'target_audience',
            'potential_keywords', 'content_type', 'priority', 'notes', 'source',
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': INPUT, 'placeholder': 'Idea title'}),
            'description': forms.Textarea(attrs={'class': TEXTAREA, 'rows': 4}),
            'topic': forms.TextInput(attrs={'class': INPUT}),
            'category': forms.Select(attrs={'class': INPUT}),
            'target_audience': forms.TextInput(attrs={'class': INPUT}),
            'potential_keywords': forms.TextInput(attrs={'class': INPUT}),
            'content_type': forms.Select(attrs={'class': INPUT}),
            'priority': forms.Select(attrs={'class': INPUT}),
            'notes': forms.Textarea(attrs={'class': TEXTAREA, 'rows': 3}),
            'source': forms.Select(attrs={'class': INPUT}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = ContentCategory.objects.all()

    def clean(self):
        cleaned = super().clean()
        limits = {
            'title': 180, 'description': 4000, 'topic': 120, 'target_audience': 200,
            'potential_keywords': 500, 'notes': 4000,
        }
        for field, limit in limits.items():
            cleaned[field] = sanitize_text(cleaned.get(field), limit)
        if not cleaned.get('title'):
            self.add_error('title', 'Enter an idea title.')
        return cleaned


class ContentBriefForm(forms.ModelForm):
    class Meta:
        model = ContentBrief
        fields = [
            'working_title', 'content', 'content_type', 'objective', 'target_audience',
            'audience_pain_points', 'search_intent', 'primary_keyword', 'secondary_keywords',
            'topic', 'proposed_slug', 'suggested_headings', 'outline', 'questions_to_answer',
            'internal_links', 'external_references', 'cta', 'desired_length',
            'competitor_urls', 'notes', 'is_reusable',
        ]
        widgets = {
            'working_title': forms.TextInput(attrs={'class': INPUT}),
            'content': forms.Select(attrs={'class': INPUT}),
            'content_type': forms.Select(attrs={'class': INPUT}),
            'objective': forms.Textarea(attrs={'class': TEXTAREA, 'rows': 3}),
            'target_audience': forms.TextInput(attrs={'class': INPUT}),
            'audience_pain_points': forms.Textarea(attrs={'class': TEXTAREA, 'rows': 3}),
            'search_intent': forms.TextInput(attrs={'class': INPUT}),
            'primary_keyword': forms.TextInput(attrs={'class': INPUT}),
            'secondary_keywords': forms.TextInput(attrs={'class': INPUT}),
            'topic': forms.TextInput(attrs={'class': INPUT}),
            'proposed_slug': forms.TextInput(attrs={'class': INPUT}),
            'suggested_headings': forms.Textarea(attrs={'class': f'{TEXTAREA} gcm-monospace', 'rows': 6}),
            'outline': forms.Textarea(attrs={'class': TEXTAREA, 'rows': 6}),
            'questions_to_answer': forms.Textarea(attrs={'class': TEXTAREA, 'rows': 4}),
            'internal_links': forms.Textarea(attrs={'class': f'{TEXTAREA} gcm-monospace', 'rows': 4}),
            'external_references': forms.Textarea(attrs={'class': f'{TEXTAREA} gcm-monospace', 'rows': 4}),
            'cta': forms.TextInput(attrs={'class': INPUT}),
            'desired_length': forms.TextInput(attrs={'class': INPUT}),
            'competitor_urls': forms.Textarea(attrs={'class': f'{TEXTAREA} gcm-monospace', 'rows': 3}),
            'notes': forms.Textarea(attrs={'class': TEXTAREA, 'rows': 3}),
            'is_reusable': forms.CheckboxInput(attrs={'class': 'gcm-checkbox'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['content'].queryset = MarketingContent.objects.all()

    def clean(self):
        cleaned = super().clean()
        limits = {
            'working_title': 180, 'objective': 5000, 'target_audience': 200,
            'audience_pain_points': 4000, 'search_intent': 120, 'primary_keyword': 120,
            'secondary_keywords': 500, 'topic': 120, 'proposed_slug': 180,
            'suggested_headings': 8000, 'outline': 12000, 'questions_to_answer': 6000,
            'internal_links': 6000, 'external_references': 6000, 'cta': 300,
            'desired_length': 80, 'competitor_urls': 6000, 'notes': 5000,
        }
        for field, limit in limits.items():
            cleaned[field] = sanitize_text(cleaned.get(field), limit)
        if not cleaned.get('working_title'):
            self.add_error('working_title', 'Enter a working title.')
        return cleaned


class ContentTemplateForm(forms.ModelForm):
    class Meta:
        model = ContentTemplate
        fields = ['name', 'content_type', 'structure', 'headings', 'brief_fields', 'cta', 'seo_checklist', 'notes']
        widgets = {
            'name': forms.TextInput(attrs={'class': INPUT}),
            'content_type': forms.Select(attrs={'class': INPUT}),
            'structure': forms.Textarea(attrs={'class': TEXTAREA, 'rows': 4}),
            'headings': forms.Textarea(attrs={'class': f'{TEXTAREA} gcm-monospace', 'rows': 5}),
            'brief_fields': forms.Textarea(attrs={'class': TEXTAREA, 'rows': 4}),
            'cta': forms.TextInput(attrs={'class': INPUT}),
            'seo_checklist': forms.Textarea(attrs={'class': TEXTAREA, 'rows': 4}),
            'notes': forms.Textarea(attrs={'class': TEXTAREA, 'rows': 3}),
        }

    def clean(self):
        cleaned = super().clean()
        limits = {
            'name': 150, 'structure': 6000, 'headings': 8000, 'brief_fields': 6000,
            'cta': 300, 'seo_checklist': 4000, 'notes': 4000,
        }
        for field, limit in limits.items():
            cleaned[field] = sanitize_text(cleaned.get(field), limit)
        if not cleaned.get('name'):
            self.add_error('name', 'Enter a template name.')
        return cleaned


class ContentRefreshForm(forms.ModelForm):
    class Meta:
        model = ContentRefreshTask
        fields = ['content', 'reason', 'due_date', 'priority', 'status', 'update_notes']
        widgets = {
            'content': forms.Select(attrs={'class': INPUT}),
            'reason': forms.Textarea(attrs={'class': TEXTAREA, 'rows': 3}),
            'due_date': forms.DateInput(attrs={'class': INPUT, 'type': 'date'}),
            'priority': forms.Select(attrs={'class': INPUT}),
            'status': forms.Select(attrs={'class': INPUT}),
            'update_notes': forms.Textarea(attrs={'class': TEXTAREA, 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['content'].queryset = MarketingContent.objects.filter(status='Published')

    def clean(self):
        cleaned = super().clean()
        cleaned['reason'] = sanitize_text(cleaned.get('reason'), 4000)
        cleaned['update_notes'] = sanitize_text(cleaned.get('update_notes'), 4000)
        if cleaned.get('status') == 'Completed' and not cleaned.get('update_notes'):
            self.add_error('update_notes', 'Add notes describing the completed refresh.')
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        if instance.status == 'Completed' and not instance.completed_at:
            from django.utils import timezone
            instance.completed_at = timezone.now()
        elif instance.status != 'Completed':
            instance.completed_at = None
        if commit:
            instance.save()
        return instance


class ContentCategoryForm(forms.ModelForm):
    class Meta:
        model = ContentCategory
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': INPUT}),
            'description': forms.TextInput(attrs={'class': INPUT}),
        }

    def clean(self):
        cleaned = super().clean()
        cleaned['name'] = sanitize_text(cleaned.get('name'), 120)
        cleaned['description'] = sanitize_text(cleaned.get('description'), 300)
        if not cleaned.get('name'):
            self.add_error('name', 'Enter a category name.')
        return cleaned


class ContentTagForm(forms.ModelForm):
    class Meta:
        model = ContentTag
        fields = ['name']
        widgets = {'name': forms.TextInput(attrs={'class': INPUT})}

    def clean(self):
        cleaned = super().clean()
        cleaned['name'] = sanitize_text(cleaned.get('name'), 80)
        if not cleaned.get('name'):
            self.add_error('name', 'Enter a tag name.')
        return cleaned


class ContentFilterForm(forms.Form):
    section = forms.ChoiceField(choices=CONTENT_SECTIONS, required=False)
    status = forms.ChoiceField(choices=CONTENT_STATUSES, required=False)
    content_type = forms.ChoiceField(choices=CONTENT_TYPES, required=False)
    category = forms.ModelChoiceField(queryset=ContentCategory.objects.none(), required=False, empty_label='All categories')
    tag = forms.ModelChoiceField(queryset=ContentTag.objects.none(), required=False, empty_label='All tags')
    priority = forms.ChoiceField(choices=CONTENT_PRIORITIES, required=False)
    query = forms.CharField(max_length=200, required=False, widget=forms.TextInput(attrs={'class': INPUT, 'placeholder': 'Search content, ideas, keywords...'}))
    sort = forms.ChoiceField(choices=CONTENT_SORTS, required=False)
    direction = forms.ChoiceField(choices=(('asc', 'Ascending'), ('desc', 'Descending')), required=False)
    view = forms.ChoiceField(choices=CONTENT_CALENDAR_VIEWS, required=False)
    date = forms.DateField(required=False, widget=forms.DateInput(attrs={'class': INPUT, 'type': 'date'}))
    date_range = forms.ChoiceField(choices=RANGE_CHOICES, required=False)
    refresh_status = forms.ChoiceField(choices=REFRESH_STATUSES, required=False)
    idea_source = forms.ChoiceField(choices=IDEA_SOURCES, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = ContentCategory.objects.all()
        self.fields['tag'].queryset = ContentTag.objects.all()
        for field in self.fields.values():
            if not isinstance(field.widget, forms.TextInput):
                field.widget.attrs.setdefault('class', INPUT)
