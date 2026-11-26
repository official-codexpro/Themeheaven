from django.contrib import admin

from .models import FooterSettings


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
