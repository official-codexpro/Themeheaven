from .seo import build_seo_context
from .tracking import build_tracking_config


def seo(request):
    try:
        return {'seo': build_seo_context(request)}
    except Exception:
        return {'seo': {}}


def analytics_tracking(request):
    try:
        return {'growth_tracking': build_tracking_config(request)}
    except Exception:
        return {'growth_tracking': None}
