from .seo import build_seo_context


def seo(request):
    try:
        return {'seo': build_seo_context(request)}
    except Exception:
        return {'seo': {}}
