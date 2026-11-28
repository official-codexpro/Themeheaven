from django.db import migrations


TEMPLATE_NAMES = (
    'SEO Blog Post',
    'How-To Guide',
    'Tutorial',
    'Case Study',
    'Product/Feature Announcement',
    'Comparison Article',
    'FAQ Article',
    'Landing Page',
    'Newsletter',
)


def create_starter_templates(apps, schema_editor):
    ContentTemplate = apps.get_model('growth_center', 'ContentTemplate')
    from growth_center.content_constants import DEFAULT_CONTENT_TEMPLATES

    for index, template in enumerate(DEFAULT_CONTENT_TEMPLATES, start=1):
        defaults = {'template_key': f'CTPL-{index:04d}', **template}
        ContentTemplate.objects.get_or_create(name=template['name'], defaults=defaults)


def remove_starter_templates(apps, schema_editor):
    ContentTemplate = apps.get_model('growth_center', 'ContentTemplate')
    ContentTemplate.objects.filter(name__in=TEMPLATE_NAMES).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('growth_center', '0007_add_content_marketing'),
    ]

    operations = [
        migrations.RunPython(create_starter_templates, remove_starter_templates),
    ]
