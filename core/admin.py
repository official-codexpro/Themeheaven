from django import forms
from django.contrib import admin

from .models import AppearanceSettings, FooterSettings

COLOR_FIELDS = (
    'dark_bg_primary', 'dark_bg_secondary', 'dark_bg_card', 'dark_header_bg',
    'dark_footer_bg', 'dark_text_primary', 'dark_text_secondary', 'dark_heading_color',
    'dark_border_color', 'dark_button_bg', 'dark_button_text', 'dark_input_bg',
    'dark_input_text', 'dark_link_color', 'dark_accent_color',
    'light_bg_primary', 'light_bg_secondary', 'light_bg_card', 'light_header_bg',
    'light_footer_bg', 'light_text_primary', 'light_text_secondary', 'light_heading_color',
    'light_border_color', 'light_button_bg', 'light_button_text', 'light_input_bg',
    'light_input_text', 'light_link_color', 'light_accent_color',
    'desktop_background_color', 'desktop_icon_color',
    'mobile_background_color', 'mobile_icon_color',
    'background_color', 'icon_color', 'global_accent_color',
)

COLOR_WIDGETS = {name: forms.TextInput(attrs={'type': 'color'}) for name in COLOR_FIELDS}
NUMBER_WIDGETS = {
    name: forms.NumberInput(attrs={'min': 0})
    for name in (
        'desktop_icon_size', 'desktop_button_size', 'desktop_border_radius',
        'mobile_icon_size', 'mobile_button_size', 'mobile_border_radius',
        'icon_size', 'button_size', 'border_radius', 'horizontal_offset',
        'vertical_offset', 'z_index', 'global_border_radius',
    )
}


class AppearanceSettingsAdminForm(forms.ModelForm):
    class Meta:
        model = AppearanceSettings
        fields = '__all__'
        widgets = {
            **COLOR_WIDGETS,
            **NUMBER_WIDGETS,
            'phone_number': forms.TextInput(attrs={'type': 'tel', 'dir': 'ltr'}),
            'default_message': forms.Textarea(attrs={'rows': 3}),
        }


@admin.register(FooterSettings)
class FooterSettingsAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'contact_email', 'contact_phone')
    fieldsets = (
        ('Column 1 – Brand', {
            'fields': ('brand_description',),
            'description': 'The ThemeHaven logo uses the current static brand asset.',
        }),
        ('Column 2 – Help & Support', {
            'fields': ('help_heading', 'help_intro', 'support_button_label', 'support_url'),
            'description': 'The single support button uses the configured Support page URL.',
        }),
        ('Column 3 – Policies', {
            'fields': (
                'policies_heading',
                'privacy_label',
                'privacy_url',
                'terms_label',
                'terms_url',
                'refund_label',
                'refund_url',
                'agreement_label',
                'agreement_url',
            ),
        }),
        ('Column 4 – Contact', {
            'fields': (
                'contact_heading',
                'contact_email',
                'contact_phone',
                'contact_message',
                'whatsapp_url',
                'instagram_url',
                'x_url',
                'linkedin_url',
            ),
            'description': 'Social icons appear only when their URL is configured.',
        }),
        ('Bottom Section', {
            'fields': ('copyright_text',),
        }),
    )

    def has_add_permission(self, request):
        return not FooterSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AppearanceSettings)
class AppearanceSettingsAdmin(admin.ModelAdmin):
    form = AppearanceSettingsAdminForm
    list_display = ('__str__', 'theme_mode', 'default_theme', 'whatsapp_enabled')
    fieldsets = (
        ('General Appearance', {
            'fields': ('preference_policy', 'switch_behavior'),
            'description': 'Controls how visitor theme preferences and switching behave site-wide.',
        }),
        ('Theme Mode', {
            'fields': (
                'theme_mode',
                'dark_theme_enabled',
                'light_theme_enabled',
                'allow_visitor_switching',
                'show_theme_switchers',
            ),
            'description': 'Single Theme Mode forces one theme for everyone and removes both theme buttons. If only one theme is available, switching is disabled automatically.',
        }),
        ('Default Theme', {
            'fields': ('default_theme',),
            'description': 'Applied to new visitors and used as the forced theme in Single Theme Mode.',
        }),
        ('Dark Theme Colors', {
            'fields': (
                'dark_bg_primary', 'dark_bg_secondary', 'dark_bg_card', 'dark_header_bg',
                'dark_footer_bg', 'dark_text_primary', 'dark_text_secondary',
                'dark_heading_color', 'dark_border_color', 'dark_button_bg',
                'dark_button_text', 'dark_input_bg', 'dark_input_text',
                'dark_link_color', 'dark_accent_color',
            ),
            'classes': ('collapse',),
        }),
        ('Light Theme Colors', {
            'fields': (
                'light_bg_primary', 'light_bg_secondary', 'light_bg_card', 'light_header_bg',
                'light_footer_bg', 'light_text_primary', 'light_text_secondary',
                'light_heading_color', 'light_border_color', 'light_button_bg',
                'light_button_text', 'light_input_bg', 'light_input_text',
                'light_link_color', 'light_accent_color',
            ),
            'classes': ('collapse',),
        }),
        ('Desktop Theme Switcher', {
            'fields': (
                'desktop_enabled',
                'desktop_background_enabled',
                'desktop_background_color',
                'desktop_icon_color',
                'desktop_custom_svg',
                'desktop_icon_size',
                'desktop_button_size',
                'desktop_border_radius',
                'desktop_position',
                'desktop_tooltip_enabled',
                'desktop_tooltip_text',
                'desktop_hover_effects',
                'desktop_transition',
            ),
            'description': 'Manages the existing lamp switcher in the desktop navbar. Disabling removes it from the page.',
        }),
        ('Mobile Theme Switcher', {
            'fields': (
                'mobile_enabled',
                'mobile_background_enabled',
                'mobile_background_color',
                'mobile_icon_color',
                'mobile_custom_svg',
                'mobile_icon_size',
                'mobile_button_size',
                'mobile_border_radius',
                'mobile_position',
                'mobile_tooltip_enabled',
                'mobile_tooltip_text',
                'mobile_hover_effects',
                'mobile_transition',
            ),
            'description': 'Manages the existing theme button in the mobile menu. Disabling removes it from the page.',
        }),
        ('WhatsApp Floating Button', {
            'fields': (
                'whatsapp_enabled',
                'phone_number',
                'default_message',
                'background_color',
                'icon_color',
                'custom_svg',
                'icon_size',
                'button_size',
                'border_radius',
                'position',
                'horizontal_offset',
                'vertical_offset',
                'z_index',
                'tooltip_enabled',
                'tooltip_text',
                'animation',
                'show_on_mobile',
                'show_on_desktop',
            ),
            'description': 'Controls the existing floating WhatsApp button. Uploaded SVGs are sanitized; clear the field to restore the default icon.',
        }),
        ('Global UI Settings', {
            'fields': (
                'global_animations_enabled',
                'global_hover_enabled',
                'global_transitions_enabled',
                'global_border_radius',
                'global_accent_color',
                'global_button_style',
                'font_family',
            ),
            'description': 'Site-wide motion, radius, accent, button and font controls. Existing layouts are preserved.',
        }),
    )

    def has_add_permission(self, request):
        return not AppearanceSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
