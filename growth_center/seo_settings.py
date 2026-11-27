import time

from .models import SEOSettings

_cache = {'instance': None, 'expires': 0.0}
CACHE_SECONDS = 300


def clear_seo_settings_cache():
    _cache['instance'] = None
    _cache['expires'] = 0.0


def get_seo_settings():
    now = time.monotonic()
    instance = _cache['instance']
    if instance is not None and now < _cache['expires']:
        return instance

    instance, _created = SEOSettings.objects.get_or_create(
        pk=1,
        defaults=SEOSettings.safe_defaults(),
    )
    if not instance.robots_txt_content:
        instance.robots_txt_content = SEOSettings.safe_defaults()['robots_txt_content']
        type(instance).objects.filter(pk=1).update(robots_txt_content=instance.robots_txt_content)

    _cache['instance'] = instance
    _cache['expires'] = now + CACHE_SECONDS
    return instance


def reset_seo_settings():
    instance = SEOSettings.objects.get_or_create(pk=1, defaults=SEOSettings.safe_defaults())[0]
    if instance.default_image:
        instance.default_image.delete(save=False)
    for field, value in SEOSettings.safe_defaults().items():
        setattr(instance, field, value)
    instance.save()
    clear_seo_settings_cache()
    return instance
