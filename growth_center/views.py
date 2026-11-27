from django.contrib import admin, messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.templatetags.static import static

from .forms import SEOSettingsForm
from .robots import render_robots_txt, robots_absolute_url, sitemap_absolute_url
from .seo import SAFE_DESCRIPTION, SAFE_TITLE, site_origin
from .seo_health import seo_health_summary
from .seo_settings import get_seo_settings, reset_seo_settings
from .services import build_analytics_context
from .sitemaps import PublicSitemap
from .validators import SAFE_ROBOTS_TXT, sanitize_text


@staff_member_required
def analytics_dashboard(request):
    context = build_analytics_context(request)
    context = {**admin.site.each_context(request), **context}

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.GET.get('format') == 'json':
        return JsonResponse({
            'html': render_to_string(
                'admin/growth_center/dashboard_content.html',
                context,
                request=request,
            ),
            'range': {
                'key': context['range']['key'],
                'start': context['range']['start_iso'],
                'end': context['range']['end_iso'],
            },
        })

    return render(request, 'admin/growth_center/dashboard.html', context)


@staff_member_required
def seo_settings_dashboard(request):
    instance = get_seo_settings()
    url = 'admin:growth-center-seo-settings'

    if request.method == 'POST' and request.POST.get('reset'):
        reset_seo_settings()
        messages.success(request, 'SEO settings were reset to safe defaults. Analytics and website content were not changed.')
        return redirect(url)

    if request.method == 'POST':
        form = SEOSettingsForm(request.POST, request.FILES, instance=instance)
        if form.is_valid():
            form.save()
            messages.success(request, 'SEO settings saved successfully.')
            return redirect(url)
        messages.error(request, 'Please correct the highlighted SEO settings errors.')
    else:
        form = SEOSettingsForm(instance=instance)

    health = seo_health_summary(instance)
    preview = {
        'domain': site_origin(instance=instance).split('://', 1)[-1],
        'title': sanitize_text(instance.seo_title, 120) or SAFE_TITLE,
        'description': sanitize_text(instance.meta_description, 320) or SAFE_DESCRIPTION,
        'favicon_url': static('img/logo.png'),
    }

    context = {
        'title': 'SEO Settings',
        'form': form,
        'instance': instance,
        'health': health,
        'preview': preview,
        'sitemap_url': sitemap_absolute_url(instance),
        'robots_url': robots_absolute_url(instance),
        'robots_preview': render_robots_txt(instance),
        'seo_config': {
            'domain': preview['domain'],
            'safeTitle': SAFE_TITLE,
            'safeDescription': SAFE_DESCRIPTION,
            'safeRobots': SAFE_ROBOTS_TXT,
            'faviconUrl': static('img/logo.png'),
            'sitemapUrl': sitemap_absolute_url(instance),
        },
    }
    context.update(admin.site.each_context(request))
    return render(request, 'admin/growth_center/seo_settings.html', context)


def robots_txt(request):
    return HttpResponse(render_robots_txt(), content_type='text/plain; charset=utf-8')


def sitemap_view(request):
    sitemap = PublicSitemap()
    urls = []
    for item in sitemap.items():
        urls.append({
            'location': sitemap.location(item),
            'lastmod': sitemap.lastmod(item),
            'changefreq': sitemap.changefreq(item),
            'priority': sitemap.priority(item),
        })
    return render(request, 'sitemap.xml', {'urlset': urls}, content_type='application/xml')
