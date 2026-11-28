from django import forms

from .conversion_constants import (
    CONVERSION_EVENT_TYPES,
    CONVERSION_SECTIONS,
    CONVERSION_SORTS,
    GOAL_STATUSES,
    REPORT_VIEWS,
    TRACKING_RULE_STATUSES,
)
from .conversion_validators import clean_event_name, clean_path, is_safe_event_name, validate_tracking_selector
from .models import CampaignCost, ConversionEvent, ConversionFunnel, ConversionGoal, TrackingRule
from .services import DATE_RANGES
from .validators import sanitize_text

INPUT = 'ctc-input'
TEXTAREA = 'ctc-input ctc-textarea'


class ConversionGoalForm(forms.ModelForm):
    class Meta:
        model = ConversionGoal
        fields = ['name', 'description', 'goal_type', 'event_name', 'target_page', 'target_url', 'status', 'value', 'notes']
        widgets = {
            'name': forms.TextInput(attrs={'class': INPUT}),
            'description': forms.Textarea(attrs={'class': TEXTAREA, 'rows': 3}),
            'goal_type': forms.Select(attrs={'class': INPUT}),
            'event_name': forms.TextInput(attrs={'class': INPUT, 'placeholder': 'get_started'}),
            'target_page': forms.TextInput(attrs={'class': INPUT, 'placeholder': '/support/'}),
            'target_url': forms.URLInput(attrs={'class': INPUT}),
            'status': forms.Select(attrs={'class': INPUT}),
            'value': forms.NumberInput(attrs={'class': INPUT, 'step': '0.01', 'min': '0'}),
            'notes': forms.Textarea(attrs={'class': TEXTAREA, 'rows': 3}),
        }

    def clean_event_name(self):
        value = clean_event_name(self.cleaned_data.get('event_name'))
        if self.cleaned_data.get('goal_type') != 'Page Visit' and not is_safe_event_name(value):
            raise forms.ValidationError('Use lowercase letters, numbers, dots, dashes, or underscores.')
        return value

    def clean_target_page(self):
        return clean_path(self.cleaned_data.get('target_page'))

    def clean(self):
        cleaned = super().clean()
        cleaned['name'] = sanitize_text(cleaned.get('name'), 150)
        cleaned['description'] = sanitize_text(cleaned.get('description'), 3000)
        cleaned['notes'] = sanitize_text(cleaned.get('notes'), 4000)
        if not cleaned.get('name'):
            self.add_error('name', 'Enter a goal name.')
        if cleaned.get('goal_type') == 'Page Visit' and not (cleaned.get('target_page') or cleaned.get('target_url')):
            self.add_error('target_page', 'Enter a target page or URL for a page visit goal.')
        return cleaned


class ConversionFunnelForm(forms.ModelForm):
    class Meta:
        model = ConversionFunnel
        fields = ['name', 'description', 'status']
        widgets = {
            'name': forms.TextInput(attrs={'class': INPUT}),
            'description': forms.Textarea(attrs={'class': TEXTAREA, 'rows': 3}),
            'status': forms.Select(attrs={'class': INPUT}),
        }

    def clean(self):
        cleaned = super().clean()
        cleaned['name'] = sanitize_text(cleaned.get('name'), 150)
        cleaned['description'] = sanitize_text(cleaned.get('description'), 3000)
        if not cleaned.get('name'):
            self.add_error('name', 'Enter a funnel name.')
        return cleaned


class ConversionFunnelStepForm(forms.ModelForm):
    class Meta:
        from .models import ConversionFunnelStep
        model = ConversionFunnelStep
        fields = ['order', 'label', 'step_type', 'event_name', 'target_path', 'goal']
        widgets = {
            'order': forms.NumberInput(attrs={'class': INPUT, 'min': 1}),
            'label': forms.TextInput(attrs={'class': INPUT}),
            'step_type': forms.Select(attrs={'class': INPUT, 'data-step-type': ''}),
            'event_name': forms.TextInput(attrs={'class': INPUT, 'placeholder': 'cta_click'}),
            'target_path': forms.TextInput(attrs={'class': INPUT, 'placeholder': '/'}),
            'goal': forms.Select(attrs={'class': INPUT}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['goal'].queryset = ConversionGoal.objects.all()
        self.fields['goal'].required = False

    def clean_event_name(self):
        return clean_event_name(self.cleaned_data.get('event_name'))

    def clean_target_path(self):
        return clean_path(self.cleaned_data.get('target_path'))

    def clean(self):
        cleaned = super().clean()
        cleaned['label'] = sanitize_text(cleaned.get('label'), 150)
        if not cleaned.get('label'):
            self.add_error('label', 'Enter a step label.')
        if cleaned.get('step_type') == 'conversion' and not (cleaned.get('event_name') or cleaned.get('goal')):
            self.add_error('event_name', 'Select an event name or goal for this step.')
        if cleaned.get('step_type') == 'page_view' and not cleaned.get('target_path'):
            self.add_error('target_path', 'Enter a page path for a page visit step.')
        return cleaned


def funnel_step_formset(data=None, instance=None, extra=1):
    from django.forms import inlineformset_factory
    from .models import ConversionFunnelStep

    factory = inlineformset_factory(
        ConversionFunnel,
        ConversionFunnelStep,
        form=ConversionFunnelStepForm,
        extra=extra,
        can_delete=True,
        min_num=1,
        validate_min=True,
    )
    return factory(data, instance=instance)


class TrackingRuleForm(forms.ModelForm):
    class Meta:
        model = TrackingRule
        fields = ['name', 'selector', 'event_type', 'event_name', 'target_path', 'goal', 'status', 'notes']
        widgets = {
            'name': forms.TextInput(attrs={'class': INPUT}),
            'selector': forms.TextInput(attrs={'class': INPUT, 'placeholder': '[data-track-name="get_started"]'}),
            'event_type': forms.Select(attrs={'class': INPUT}),
            'event_name': forms.TextInput(attrs={'class': INPUT}),
            'target_path': forms.TextInput(attrs={'class': INPUT, 'placeholder': '/'}),
            'goal': forms.Select(attrs={'class': INPUT}),
            'status': forms.Select(attrs={'class': INPUT}),
            'notes': forms.Textarea(attrs={'class': TEXTAREA, 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['goal'].queryset = ConversionGoal.objects.all()

    def clean_selector(self):
        try:
            return validate_tracking_selector(self.cleaned_data.get('selector'))
        except ValueError as exc:
            raise forms.ValidationError(str(exc))

    def clean_event_name(self):
        value = clean_event_name(self.cleaned_data.get('event_name'))
        if not is_safe_event_name(value):
            raise forms.ValidationError('Use lowercase letters, numbers, dots, dashes, or underscores.')
        return value

    def clean_target_path(self):
        return clean_path(self.cleaned_data.get('target_path'))

    def clean(self):
        cleaned = super().clean()
        cleaned['name'] = sanitize_text(cleaned.get('name'), 150)
        cleaned['notes'] = sanitize_text(cleaned.get('notes'), 4000)
        if not cleaned.get('name'):
            self.add_error('name', 'Enter a rule name.')
        return cleaned


class CampaignCostForm(forms.ModelForm):
    class Meta:
        model = CampaignCost
        fields = ['campaign', 'cost_amount', 'currency', 'cost_period', 'notes']
        widgets = {
            'campaign': forms.Select(attrs={'class': INPUT}),
            'cost_amount': forms.NumberInput(attrs={'class': INPUT, 'step': '0.01', 'min': '0'}),
            'currency': forms.TextInput(attrs={'class': INPUT, 'maxlength': 3}),
            'cost_period': forms.Select(attrs={'class': INPUT}),
            'notes': forms.Textarea(attrs={'class': TEXTAREA, 'rows': 3}),
        }

    def clean_currency(self):
        value = ' '.join(str(self.cleaned_data.get('currency') or '').split()).upper()
        if len(value) != 3 or not value.isalpha():
            raise forms.ValidationError('Enter a three-letter currency code.')
        return value

    def clean_notes(self):
        return sanitize_text(self.cleaned_data.get('notes'), 4000)


class ConversionFilterForm(forms.Form):
    section = forms.ChoiceField(choices=CONVERSION_SECTIONS, required=False)
    report = forms.ChoiceField(choices=REPORT_VIEWS, required=False)
    range = forms.ChoiceField(choices=DATE_RANGES, required=False)
    start_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'class': INPUT, 'type': 'date'}))
    end_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'class': INPUT, 'type': 'date'}))
    compare = forms.TypedChoiceField(choices=(('1', 'Compare'), ('0', 'No comparison')), required=False, coerce=lambda value: value == '1')
    event = forms.CharField(max_length=80, required=False, widget=forms.TextInput(attrs={'class': INPUT}))
    goal = forms.ModelChoiceField(queryset=ConversionGoal.objects.none(), required=False, empty_label='All goals')
    page = forms.CharField(max_length=500, required=False, widget=forms.TextInput(attrs={'class': INPUT}))
    source = forms.ChoiceField(choices=(), required=False)
    medium = forms.CharField(max_length=120, required=False, widget=forms.TextInput(attrs={'class': INPUT}))
    campaign = forms.CharField(max_length=120, required=False, widget=forms.TextInput(attrs={'class': INPUT}))
    device = forms.ChoiceField(choices=(), required=False)
    query = forms.CharField(max_length=200, required=False, widget=forms.TextInput(attrs={'class': INPUT, 'placeholder': 'Search events...'}))
    event_type = forms.ChoiceField(choices=CONVERSION_EVENT_TYPES, required=False)
    goal_status = forms.ChoiceField(choices=GOAL_STATUSES, required=False)
    funnel_status = forms.ChoiceField(choices=GOAL_STATUSES, required=False)
    rule_status = forms.ChoiceField(choices=TRACKING_RULE_STATUSES, required=False)
    sort = forms.ChoiceField(choices=CONVERSION_SORTS, required=False)
    direction = forms.ChoiceField(choices=(('asc', 'Ascending'), ('desc', 'Descending')), required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['goal'].queryset = ConversionGoal.objects.all()
        sources = list(ConversionEvent.objects.values_list('source_category', flat=True).distinct().order_by('source_category'))
        devices = list(ConversionEvent.objects.values_list('device_category', flat=True).distinct().order_by('device_category'))
        self.fields['source'].choices = [('', 'All sources')] + [(item, item) for item in sources if item]
        self.fields['device'].choices = [('', 'All devices')] + [(item, item) for item in devices if item]
        for field in self.fields.values():
            if not isinstance(field.widget, (forms.TextInput, forms.DateInput)):
                field.widget.attrs.setdefault('class', INPUT)

    def clean_event(self):
        return clean_event_name(self.cleaned_data.get('event'))

    def clean_page(self):
        return clean_path(self.cleaned_data.get('page'))

    def clean_query(self):
        return sanitize_text(self.cleaned_data.get('query'), 200)
