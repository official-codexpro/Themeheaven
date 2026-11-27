from django.contrib import admin, messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .campaign_urls import build_campaign_url
from .campaigns import build_campaign_context, build_campaign_detail_context
from .forms import CampaignForm, PageSEOForm, SEOSettingsForm
from .models import AnalyticsSession, Campaign, PageSEO, PageView
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
from .tracking import decode_tracking_token
from .validators import SAFE_ROBOTS_TXT, sanitize_text


@staff_member_required
def analytics_dashboard(request):
    context = build_analytics_context(request)
    campaign_urls = {
        campaign.utm_campaign: reverse('admin:growth-center-campaign-detail', args=[campaign.campaign_key])
        for campaign in Campaign.objects.all()
    }
    for row in context['acquisition']['campaigns']:
        row['url'] = campaign_urls.get(row.get('utm_campaign'))
    context['campaign_links'] = campaign_urls
    context = {**admin.site.each_context(request), **context}

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.GET.get('format') == 'json':
        return JsonResponse({
            'html': render_to_string(
                'admin/growth_center/analytics_content.html',
                context,
                request=request,
            ),
            'range': {
                'key': context['range']['key'],
                'start': context['range']['start_iso'],
                'end': context['range']['end_iso'],
            },
        })

    return render(request, 'admin/growth_center/analytics.html', context)


@staff_member_required
def campaigns_dashboard(request):
    context = build_campaign_context(request)
    context = {**admin.site.each_context(request), **context}

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.GET.get('format') == 'json':
        return JsonResponse({
            'html': render_to_string(
                'admin/growth_center/campaigns_content.html',
                context,
                request=request,
            ),
            'range': {
                'key': context['range']['key'],
                'start': context['range']['start_iso'],
                'end': context['range']['end_iso'],
            },
        })

    return render(request, 'admin/growth_center/campaigns.html', context)


@staff_member_required
def campaign_editor(request, campaign_key=None):
    campaign = None
    if campaign_key:
        campaign = Campaign.objects.filter(campaign_key=campaign_key).first()
        if not campaign:
            messages.error(request, 'That campaign no longer exists.')
            return redirect('admin:growth-center-campaigns')

    if request.method == 'POST':
        form = CampaignForm(request.POST, instance=campaign)
        if form.is_valid():
            instance = form.save(commit=False)
            if not instance.pk:
                instance.created_by = request.user
            instance.save()
            messages.success(request, f'Campaign “{instance.name}” saved successfully.')
            return redirect('admin:growth-center-campaign-detail', instance.campaign_key)
        messages.error(request, 'Please correct the highlighted campaign fields.')
    else:
        form = CampaignForm(instance=campaign)

    preview_values = form.data if form.is_bound else {
        'destination_url': campaign.destination_url if campaign else '',
        'utm_source': campaign.utm_source if campaign else '',
        'utm_medium': campaign.utm_medium if campaign else '',
        'utm_campaign': campaign.utm_campaign if campaign else '',
        'utm_term': campaign.utm_term if campaign else '',
        'utm_content': campaign.utm_content if campaign else '',
    }
    preview, _error = build_campaign_url(
        preview_values.get('destination_url'),
        preview_values.get('utm_source'),
        preview_values.get('utm_medium'),
        preview_values.get('utm_campaign'),
        preview_values.get('utm_term'),
        preview_values.get('utm_content'),
    )

    context = {
        'title': f'Edit {campaign.name}' if campaign else 'Create Campaign',
        'form': form,
        'campaign': campaign,
        'is_edit': bool(campaign),
        'url_preview': preview,
    }
    context.update(admin.site.each_context(request))
    return render(request, 'admin/growth_center/campaign_editor.html', context)


@staff_member_required
def campaign_detail(request, campaign_key):
    campaign = Campaign.objects.filter(campaign_key=campaign_key).first()
    if not campaign:
        messages.error(request, 'That campaign no longer exists.')
        return redirect('admin:growth-center-campaigns')

    context = build_campaign_detail_context(request, campaign)
    context = {**admin.site.each_context(request), **context}
    return render(request, 'admin/growth_center/campaign_detail.html', context)


@staff_member_required
@require_POST
def campaign_action(request, campaign_key):
    campaign = Campaign.objects.filter(campaign_key=campaign_key).first()
    if not campaign:
        messages.error(request, 'That campaign no longer exists.')
        return redirect('admin:growth-center-campaigns')

    action = request.POST.get('action')
    if action == 'duplicate':
        base = f'{campaign.utm_campaign}-copy'
        candidate = base
        counter = 2
        while Campaign.objects.filter(utm_campaign__iexact=candidate).exists():
            candidate = f'{base}-{counter}'
            counter += 1
        copy = Campaign(
            name=f'{campaign.name} (Copy)',
            description=campaign.description,
            objective=campaign.objective,
            destination_url=campaign.destination_url,
            utm_source=campaign.utm_source,
            utm_medium=campaign.utm_medium,
            utm_campaign=candidate,
            utm_term=campaign.utm_term,
            utm_content=campaign.utm_content,
            start_date=campaign.start_date,
            end_date=campaign.end_date,
            status='Draft',
            notes=campaign.notes,
            created_by=request.user,
        )
        copy.save()
        messages.success(request, f'Duplicated campaign as “{copy.name}”.')
        return redirect('admin:growth-center-campaign-detail', copy.campaign_key)

    if action in {'pause', 'resume', 'archive'}:
        target = {'pause': 'Paused', 'resume': 'Active', 'archive': 'Archived'}[action]
        campaign.status = target
        campaign.save(update_fields=['status', 'updated_at'])
        messages.success(request, f'Campaign status changed to {target}.')
        return redirect('admin:growth-center-campaign-detail', campaign.campaign_key)

    if action == 'delete':
        if request.POST.get('confirm') != '1':
            messages.error(request, 'Confirm campaign deletion before removing it.')
            return redirect('admin:growth-center-campaign-detail', campaign.campaign_key)
        name = campaign.name
        campaign.delete()
        messages.success(request, f'Campaign “{name}” deleted.')
        return redirect('admin:growth-center-campaigns')

    messages.error(request, 'Unknown campaign action.')
    return redirect('admin:growth-center-campaign-detail', campaign.campaign_key)


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


@require_POST
def analytics_beacon(request):
    payload = decode_tracking_token(request.POST.get('token'))
    if not payload:
        return HttpResponse(status=204)

    session = AnalyticsSession.objects.filter(
        session_key=payload['s'],
        visitor__visitor_key=payload['v'],
        ended_at__isnull=True,
    ).first()
    if not session:
        return HttpResponse(status=204)

    now = timezone.now()
    try:
        client_seconds = max(0, int(request.POST.get('duration_ms', 0)) // 1000)
    except (TypeError, ValueError):
        client_seconds = 0
    client_seconds = min(client_seconds, 86400)
    maximum_seconds = max(0, int((now - session.started_at).total_seconds()))
    duration_seconds = min(client_seconds, maximum_seconds)
    if not duration_seconds:
        duration_seconds = max(0, int((session.last_seen_at - session.started_at).total_seconds()))

    last_view = PageView.objects.filter(session=session, path=payload['p']).order_by('-viewed_at').first()
    if last_view and last_view.duration_seconds is None:
        view_duration = min(client_seconds, max(0, int((now - last_view.viewed_at).total_seconds())))
        PageView.objects.filter(pk=last_view.pk).update(duration_seconds=view_duration)

    AnalyticsSession.objects.filter(pk=session.pk, ended_at__isnull=True).update(
        ended_at=now,
        duration_seconds=min(duration_seconds, maximum_seconds),
        exit_path=payload['p'][:500],
    )
    return HttpResponse(status=204)
