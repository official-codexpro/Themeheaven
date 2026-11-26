from django.db import migrations, models


OLD_BRAND = 'Premium website themes and templates to bring your ideas to life.'
NEW_BRAND = (
    'Premium website themes and templates to bring your ideas to life. '
    'Find flexible, ready-to-use resources for modern websites and growing ideas.'
)


def update_defaults(apps, schema_editor):
    FooterSettings = apps.get_model('core', 'FooterSettings')
    for obj in FooterSettings.objects.all():
        fields = []
        if obj.brand_description == OLD_BRAND:
            obj.brand_description = NEW_BRAND
            fields.append('brand_description')
        if obj.contact_heading == 'Contact':
            obj.contact_heading = 'Get in Touch'
            fields.append('contact_heading')
        if obj.refund_label in {'Refund & Cancellation Policy', 'Refund & Cancellation'}:
            obj.refund_label = 'Refund Policy'
            fields.append('refund_label')
        if obj.agreement_label in {'Shipping & Delivery Policy', 'Shipping & Delivery'}:
            obj.agreement_label = 'User Agreement'
            fields.append('agreement_label')
        if obj.copyright_text == 'ThemeHaven. All rights reserved.':
            obj.copyright_text = '© 2026 ThemeHaven. All Rights Reserved.'
            fields.append('copyright_text')
        if fields:
            obj.save(update_fields=fields)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_footersettings_privacy_label_and_more'),
    ]

    operations = [
        migrations.RenameField(
            model_name='footersettings',
            old_name='tagline',
            new_name='brand_description',
        ),
        migrations.RenameField(
            model_name='footersettings',
            old_name='support_heading',
            new_name='help_heading',
        ),
        migrations.RenameField(
            model_name='footersettings',
            old_name='support_text',
            new_name='help_intro',
        ),
        migrations.RenameField(
            model_name='footersettings',
            old_name='shipping_label',
            new_name='agreement_label',
        ),
        migrations.RunPython(update_defaults, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='footersettings',
            name='connect_heading',
        ),
        migrations.RemoveField(
            model_name='footersettings',
            name='support_link_label',
        ),
        migrations.RemoveField(
            model_name='footersettings',
            name='bottom_note',
        ),
        migrations.RemoveField(
            model_name='footersettings',
            name='hashtags',
        ),
        migrations.AddField(
            model_name='footersettings',
            name='support_button_label',
            field=models.CharField(default='Contact Support', max_length=60, verbose_name='Support Button Text'),
        ),
        migrations.AddField(
            model_name='footersettings',
            name='support_url',
            field=models.CharField(
                default='/support/',
                help_text='Use an internal path such as /support/ or a full http(s) URL.',
                max_length=200,
                verbose_name='Support Page URL',
            ),
        ),
        migrations.AddField(
            model_name='footersettings',
            name='privacy_url',
            field=models.CharField(
                default='/privacy-policy/',
                help_text='Use an internal path or a full http(s) URL.',
                max_length=200,
                verbose_name='Privacy Policy URL',
            ),
        ),
        migrations.AddField(
            model_name='footersettings',
            name='terms_url',
            field=models.CharField(
                default='/terms-conditions/',
                help_text='Use an internal path or a full http(s) URL.',
                max_length=200,
                verbose_name='Terms & Conditions URL',
            ),
        ),
        migrations.AddField(
            model_name='footersettings',
            name='refund_url',
            field=models.CharField(
                default='/refund-cancellation-policy/',
                help_text='Use an internal path or a full http(s) URL.',
                max_length=200,
                verbose_name='Refund Policy URL',
            ),
        ),
        migrations.AddField(
            model_name='footersettings',
            name='agreement_url',
            field=models.CharField(
                default='/shipping-delivery-policy/',
                help_text='Use an internal path or a full http(s) URL.',
                max_length=200,
                verbose_name='User Agreement URL',
            ),
        ),
        migrations.AlterField(
            model_name='footersettings',
            name='brand_description',
            field=models.TextField(
                default=NEW_BRAND,
                max_length=320,
                verbose_name='Brand Description',
            ),
        ),
        migrations.AlterField(
            model_name='footersettings',
            name='help_heading',
            field=models.CharField(default='Help & Support', max_length=60, verbose_name='Help & Support Heading'),
        ),
        migrations.AlterField(
            model_name='footersettings',
            name='help_intro',
            field=models.CharField(
                default='Need a hand finding the right theme or template?',
                max_length=240,
                verbose_name='Help & Support Introduction',
            ),
        ),
        migrations.AlterField(
            model_name='footersettings',
            name='contact_heading',
            field=models.CharField(default='Get in Touch', max_length=60, verbose_name='Contact Heading'),
        ),
        migrations.AlterField(
            model_name='footersettings',
            name='policies_heading',
            field=models.CharField(default='Policies', max_length=60, verbose_name='Policies Heading'),
        ),
        migrations.AlterField(
            model_name='footersettings',
            name='privacy_label',
            field=models.CharField(default='Privacy Policy', max_length=80, verbose_name='Privacy Policy Title'),
        ),
        migrations.AlterField(
            model_name='footersettings',
            name='terms_label',
            field=models.CharField(default='Terms & Conditions', max_length=80, verbose_name='Terms & Conditions Title'),
        ),
        migrations.AlterField(
            model_name='footersettings',
            name='refund_label',
            field=models.CharField(default='Refund Policy', max_length=80, verbose_name='Refund Policy Title'),
        ),
        migrations.AlterField(
            model_name='footersettings',
            name='agreement_label',
            field=models.CharField(default='User Agreement', max_length=80, verbose_name='User Agreement Title'),
        ),
        migrations.AlterField(
            model_name='footersettings',
            name='contact_email',
            field=models.EmailField(blank=True, max_length=254, verbose_name='Contact Email'),
        ),
        migrations.AlterField(
            model_name='footersettings',
            name='contact_phone',
            field=models.CharField(blank=True, max_length=60, verbose_name='Contact Phone Number'),
        ),
        migrations.AlterField(
            model_name='footersettings',
            name='contact_message',
            field=models.CharField(
                default='Contact details have not been configured yet.',
                help_text='Shown only when both email and phone are empty.',
                max_length=160,
                verbose_name='Empty Contact Message',
            ),
        ),
        migrations.AlterField(
            model_name='footersettings',
            name='whatsapp_url',
            field=models.URLField(blank=True, help_text='Icon appears only when set.', verbose_name='WhatsApp URL'),
        ),
        migrations.AlterField(
            model_name='footersettings',
            name='instagram_url',
            field=models.URLField(blank=True, help_text='Icon appears only when set.', verbose_name='Instagram URL'),
        ),
        migrations.AlterField(
            model_name='footersettings',
            name='x_url',
            field=models.URLField(blank=True, help_text='Icon appears only when set.', verbose_name='X / Twitter URL'),
        ),
        migrations.AlterField(
            model_name='footersettings',
            name='linkedin_url',
            field=models.URLField(blank=True, help_text='Icon appears only when set.', verbose_name='LinkedIn URL'),
        ),
        migrations.AlterField(
            model_name='footersettings',
            name='copyright_text',
            field=models.CharField(
                default='© 2026 ThemeHaven. All Rights Reserved.',
                max_length=160,
                verbose_name='Copyright Text',
            ),
        ),
    ]
