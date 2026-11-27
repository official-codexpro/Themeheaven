from django.contrib import admin, messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.templatetags.static import static

from .forms import PageSEOForm, SEOSettingsForm
from .models import PageSEO
from .page_registry import discover_pages, get_managed_page
from .page_seo import (
    build_page_seo_context,
    get_page_instance,
    page_matches_filter,
    page_seo_status,
)
from .robots import render_robots_txt, robots_absolute_url, sitemap_absolute_url
from .seo import SAFE_DESCRIPTION, SAFE_TITLE, absolute_url, build_canonical_url, build_seo_context, site_origin
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


PAGE_SEO_FILTERS = (
    ('all', 'All Pages'),
    ('configured', 'SEO Configured'),
    ('missing', 'Missing SEO'),
    ('indexed', 'Indexed'),
    ('noindex', 'Noindex'),
    ('missing_description', 'Missing Meta Description'),
    ('missing_image', 'Missing Social Image'),
)

BULK_PAGE_SEO_ACTIONS = {
    'index': 'Set selected pages to Index',
    'noindex': 'Set selected pages to Noindex',
    'inherit': 'Reset selected pages to global inheritance',
}


@staff_member_required
def page_seo_dashboard(request):
    url = 'admin:growth-center-page-seo'
    global_instance = get_seo_settings()
    pages = discover_pages()
    statuses = [page_seo_status(page, global_instance) for page in pages]

    if request.method == 'POST':
        action = request.POST.get('bulk_action')
        keys = [key for key in request.POST.getlist('page_keys') if key]
        if action not in BULK_PAGE_SEO_ACTIONS or not keys:
            messages.error(request, 'Select pages and a valid bulk action.')
            return redirect(url)
        if request.POST.get('confirm') != '1':
            messages.error(request, 'Confirm the bulk indexing change before applying it.')
            return redirect(url)

        valid_keys = {page.key for page in pages}
        selected = [key for key in keys if key in valid_keys]
        for key in selected:
            instance, _ = PageSEO.objects.get_or_create(page_key=key)
            instance.index_mode = action if action in {'index', 'noindex'} else 'inherit'
            instance.save()
        messages.success(request, f'Updated indexing settings for {len(selected)} page(s). Website content was not changed.')
        return redirect(url)

    query = (request.GET.get('q') or '').strip()
    filter_key = request.GET.get('filter', 'all')
    if filter_key not in {key for key, _ in PAGE_SEO_FILTERS}:
        filter_key = 'all'

    filtered = []
    for status in statuses:
        page = status['page']
        if query and query.lower() not in f'{page.title} {page.path}'.lower():
            continue
        if page_matches_filter(status, filter_key):
            filtered.append(status)

    paginator = Paginator(filtered, 15)
    page_obj = paginator.get_page(request.GET.get('page'))
    context = {
        'title': 'Page SEO',
        'subtitle': 'Manage search visibility, metadata, social previews, and indexing for individual website pages.',
        'filters': PAGE_SEO_FILTERS,
        'bulk_actions': BULK_PAGE_SEO_ACTIONS,
        'filter_key': filter_key,
        'query': query,
        'page_obj': page_obj,
        'total_pages': len(pages),
        'configured_count': sum(1 for status in statuses if status['configured']),
        'noindex_count': sum(1 for status in statuses if status['index_status'] == 'noindex'),
    }
    context.update(admin.site.each_context(request))
    return render(request, 'admin/growth_center/page_seo.html', context)


@staff_member_required
def page_seo_editor(request, page_key):
    url = 'admin:growth-center-page-seo'
    managed_page = get_managed_page(page_key)
    if not managed_page:
        messages.error(request, 'That page is no longer available for SEO management.')
        return redirect(url)

    global_instance = get_seo_settings()
    instance = get_page_instance(page_key) or PageSEO(page_key=page_key)
    redirect_url = 'admin:growth-center-page-seo-edit'

    if request.method == 'POST':
        form = PageSEOForm(request.POST, request.FILES, instance=instance, page=managed_page)
        if form.is_valid():
            instance = form.save(commit=False)
            if request.POST.get('reset_canonical') == '1':
                instance.canonical_override = ''
            instance.save()
            messages.success(request, f'SEO settings saved for {managed_page.title}.')
            return redirect(redirect_url, page_key)
        messages.error(request, 'Please correct the highlighted page SEO errors.')
    else:
        form = PageSEOForm(instance=instance, page=managed_page)

    base_seo = build_seo_context(None)
    resolved_seo = {
        **base_seo,
        **build_page_seo_context(None, base_seo, global_instance, page=managed_page),
    }
    default_image = absolute_url(global_instance.default_image.url, None, global_instance) if global_instance.default_image else ''
    generated_canonical = build_canonical_url(None, managed_page.path, global_instance)
    status = page_seo_status(managed_page, global_instance)

    config = {
        'pageKey': managed_page.key,
        'pagePath': managed_page.path,
        'generatedCanonical': generated_canonical,
        'defaultTitle': managed_page.default_title or global_instance.seo_title or SAFE_TITLE,
        'defaultDescription': managed_page.default_description or global_instance.meta_description or SAFE_DESCRIPTION,
        'defaultImage': default_image,
        'resolvedTitle': resolved_seo.get('title', ''),
        'resolvedDescription': resolved_seo.get('description', ''),
        'resolvedCanonical': resolved_seo.get('canonical_url', ''),
        'safeTitle': SAFE_TITLE,
        'safeDescription': SAFE_DESCRIPTION,
    }

    context = {
        'title': 'Page SEO',
        'subtitle': 'Manage search visibility, metadata, social previews, and indexing for individual website pages.',
        'page': managed_page,
        'instance': instance,
        'form': form,
        'status': status,
        'seo': resolved_seo,
        'seo_config': config,
        'default_image': default_image,
        'generated_canonical': generated_canonical,
    }
    context.update(admin.site.each_context(request))
    return render(request, 'admin/growth_center/page_seo_editor.html', context)


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
