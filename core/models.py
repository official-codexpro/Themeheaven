from django.conf import settings
from django.db import models


class FooterSettings(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)

    brand_description = models.TextField(
        'Brand Description',
        max_length=320,
        default='Premium website themes and templates to bring your ideas to life. Find flexible, ready-to-use resources for modern websites and growing ideas.',
    )

    help_heading = models.CharField('Help & Support Heading', max_length=60, default='Help & Support')
    help_intro = models.CharField(
        'Help & Support Introduction',
        max_length=240,
        default='Need a hand finding the right theme or template?',
    )
    support_button_label = models.CharField('Support Button Text', max_length=60, default='Contact Support')
    support_url = models.CharField(
        'Support Page URL',
        max_length=200,
        default='/support/',
        help_text='Use an internal path such as /support/ or a full http(s) URL.',
    )

    policies_heading = models.CharField('Policies Heading', max_length=60, default='Policies')
    privacy_label = models.CharField('Privacy Policy Title', max_length=80, default='Privacy Policy')
    privacy_url = models.CharField(
        'Privacy Policy URL',
        max_length=200,
        default='/privacy-policy/',
        help_text='Use an internal path or a full http(s) URL.',
    )
    terms_label = models.CharField('Terms & Conditions Title', max_length=80, default='Terms & Conditions')
    terms_url = models.CharField(
        'Terms & Conditions URL',
        max_length=200,
        default='/terms-conditions/',
        help_text='Use an internal path or a full http(s) URL.',
    )
    refund_label = models.CharField('Refund Policy Title', max_length=80, default='Refund Policy')
    refund_url = models.CharField(
        'Refund Policy URL',
        max_length=200,
        default='/refund-cancellation-policy/',
        help_text='Use an internal path or a full http(s) URL.',
    )
    agreement_label = models.CharField('User Agreement Title', max_length=80, default='User Agreement')
    agreement_url = models.CharField(
        'User Agreement URL',
        max_length=200,
        default='/shipping-delivery-policy/',
        help_text='Use an internal path or a full http(s) URL.',
    )

    contact_heading = models.CharField('Contact Heading', max_length=60, default='Get in Touch')
    contact_email = models.EmailField('Contact Email', blank=True)
    contact_phone = models.CharField('Contact Phone Number', max_length=60, blank=True)
    contact_message = models.CharField(
        'Empty Contact Message',
        max_length=160,
        default='Contact details have not been configured yet.',
        help_text='Shown only when both email and phone are empty.',
    )
    whatsapp_url = models.URLField('WhatsApp URL', blank=True, help_text='Icon appears only when set.')
    instagram_url = models.URLField('Instagram URL', blank=True, help_text='Icon appears only when set.')
    x_url = models.URLField('X / Twitter URL', blank=True, help_text='Icon appears only when set.')
    linkedin_url = models.URLField('LinkedIn URL', blank=True, help_text='Icon appears only when set.')

    copyright_text = models.CharField(
        'Copyright Text',
        max_length=160,
        default='© 2026 ThemeHaven. All Rights Reserved.',
    )

    class Meta:
        verbose_name = 'Footer Settings'
        verbose_name_plural = 'Footer Settings'

    def __str__(self):
        return 'Footer Settings'

    def save(self, *args, **kwargs):
        self.pk = 1
        return super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        configured = getattr(settings, 'SOCIAL_LINKS', {})
        defaults = {
            'whatsapp_url': configured.get('whatsapp', ''),
            'instagram_url': configured.get('instagram', ''),
            'x_url': configured.get('x', ''),
            'linkedin_url': configured.get('linkedin', ''),
        }
        obj, _created = cls.objects.get_or_create(pk=1, defaults=defaults)
        return obj
