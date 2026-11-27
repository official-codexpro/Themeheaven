import mimetypes
from datetime import date, datetime, time
from pathlib import Path
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib import admin, messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .campaign_urls import build_campaign_url
from .campaigns import build_campaign_context, build_campaign_detail_context
from .forms import CampaignForm, PageSEOForm, SEOSettingsForm
from .models import (
    AnalyticsSession,
    Campaign,
    PageSEO,
    PageView,
    SocialMediaAsset,
    SocialPost,
    SocialPostPlatform,
    SocialPostTemplate,
)
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
from .social import build_asset_preview_metadata, build_post_detail_context, build_social_context, sync_post_tracking_urls
from .social_forms import SocialMediaAssetForm, SocialPostForm, SocialPostTemplateForm
from .social_platforms import PLATFORMS, PLATFORM_KEYS
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


def _parse_social_datetime(date_value, time_value):
    try:
        parsed_date = date.fromisoformat(date_value)
        parsed_time = time.fromisoformat(time_value)
        return timezone.make_aware(datetime.combine(parsed_date, parsed_time), timezone.get_current_timezone())
    except (TypeError, ValueError):
        return None


def _safe_publication_url(value):
    url = sanitize_text(value or '', 500)
    if not url:
        return ''
    parts = urlsplit(url)
    if parts.scheme not in {'http', 'https'} or not parts.netloc:
        return ''
    return url


@staff_member_required
def social_media_manager_dashboard(request):
    asset_form = None
    template_form = None

    if request.method == 'POST':
        intent = request.POST.get('intent')
        section = request.POST.get('section', 'overview')
        if intent == 'upload_asset':
            asset_form = SocialMediaAssetForm(request.POST, request.FILES)
            if asset_form.is_valid():
                asset = asset_form.save(commit=False)
                asset.uploaded_by = request.user
                asset.save()
                uploaded_file = asset_form.cleaned_data.get('file')
                if uploaded_file and hasattr(uploaded_file, 'seek'):
                    width, height = build_asset_preview_metadata(asset)
                    if width and height:
                        asset.width = width
                        asset.height = height
                        asset.save(update_fields=['width', 'height'])
                messages.success(request, f'Media asset “{asset.title}” added to the library.')
                return redirect(f'{reverse("admin:growth-center-social")}?section=media')
            messages.error(request, 'Please correct the highlighted media upload errors.')
        elif intent == 'save_template':
            template_form = SocialPostTemplateForm(request.POST)
            if template_form.is_valid():
                template = template_form.save(commit=False)
                template.created_by = request.user
                template.save()
                messages.success(request, f'Template “{template.name}” saved.')
                return redirect(f'{reverse("admin:growth-center-social")}?section=templates')
            messages.error(request, 'Please correct the highlighted template errors.')
        else:
            messages.error(request, 'Unknown social media action.')

    context = build_social_context(
        request,
        asset_form=asset_form or SocialMediaAssetForm(),
        template_form=template_form or SocialPostTemplateForm(),
    )
    context = {**admin.site.each_context(request), **context}

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.GET.get('format') == 'json':
        return JsonResponse({
            'html': render_to_string(
                'admin/growth_center/social_media_content.html',
                context,
                request=request,
            ),
            'section': context['section'],
        })

    return render(request, 'admin/growth_center/social_media.html', context)


@staff_member_required
def social_post_editor(request, post_key=None):
    post = None
    if post_key:
        post = get_object_or_404(SocialPost, post_key=post_key)

    workflow_action = request.POST.get('workflow_action', 'save_draft') if request.method == 'POST' else 'save_draft'
    if request.method == 'POST':
        form = SocialPostForm(request.POST, instance=post, workflow_action=workflow_action)
        form.created_by = request.user
        if form.is_valid():
            instance = form.save()
            sync_post_tracking_urls(instance)
            messages.success(request, f'Post “{instance.title}” saved with status {instance.status}.')
            for warning in form.warnings:
                messages.warning(request, warning)
            return redirect('admin:growth-center-social-post-detail', instance.post_key)
        messages.error(request, 'Please correct the highlighted post fields.')
        for warning in form.warnings:
            messages.warning(request, warning)
    else:
        form = SocialPostForm(instance=post)
        if not post:
            if request.GET.get('date'):
                form.initial['scheduled_date'] = request.GET.get('date')
            if request.GET.get('time'):
                form.initial['scheduled_time'] = request.GET.get('time')
            template_key = request.GET.get('template')
            if template_key:
                template = SocialPostTemplate.objects.filter(template_key=template_key).first()
                if template:
                    form.initial['content'] = template.content
                    form.initial['hashtags'] = template.hashtags
                    if template.platform:
                        form.initial['platforms'] = [template.platform]

    platform_fields = []
    for platform in PLATFORMS:
        title_name = f'platform_title_{platform["key"]}'
        content_name = f'platform_content_{platform["key"]}'
        time_name = f'platform_time_{platform["key"]}'
        platform_fields.append({
            'config': platform,
            'title_field': form[title_name] if title_name in form.fields else None,
            'content_field': form[content_name] if content_name in form.fields else None,
            'time_field': form[time_name] if time_name in form.fields else None,
        })

    context = {
        'title': f'Edit {post.title}' if post else 'Create Social Post',
        'form': form,
        'post': post,
        'is_edit': bool(post),
        'platforms': form.fields['platforms'].choices,
        'platform_fields': platform_fields,
        'media_assets': [
            {
                'asset': asset,
                'preview_url': reverse('admin:growth-center-social-media-asset-file', args=[asset.id]),
            }
            for asset in SocialMediaAsset.objects.all()
        ],
    }
    context.update(admin.site.each_context(request))
    return render(request, 'admin/growth_center/social_post_editor.html', context)


@staff_member_required
def social_post_detail(request, post_key):
    post = get_object_or_404(SocialPost, post_key=post_key)
    context = build_post_detail_context(request, post)
    context = {**admin.site.each_context(request), **context}
    return render(request, 'admin/growth_center/social_post_detail.html', context)


@staff_member_required
@require_POST
def social_post_action(request, post_key):
    post = get_object_or_404(SocialPost, post_key=post_key)
    action = request.POST.get('action')

    if action == 'duplicate':
        copy = SocialPost(
            title=f'{post.title} (Copy)',
            content=post.content,
            content_type=post.content_type,
            status='Draft',
            campaign=post.campaign,
            destination_url=post.destination_url,
            utm_source=post.utm_source,
            utm_medium=post.utm_medium,
            utm_campaign=post.utm_campaign,
            utm_term=post.utm_term,
            utm_content=post.utm_content,
            hashtags=post.hashtags,
            notes=post.notes,
            created_by=request.user,
        )
        copy.save()
        copy.media.set(post.media.all())
        for entry in post.platform_entries.all():
            SocialPostPlatform.objects.create(
                post=copy,
                platform=entry.platform,
                content=entry.content,
                platform_title=entry.platform_title,
                status='Draft',
            )
        sync_post_tracking_urls(copy)
        messages.success(request, f'Duplicated post as “{copy.title}”.')
        return redirect('admin:growth-center-social-post-detail', copy.post_key)

    if action == 'delete':
        if request.POST.get('confirm') != '1':
            messages.error(request, 'Confirm post deletion before removing it.')
            return redirect('admin:growth-center-social-post-detail', post.post_key)
        title = post.title
        post.delete()
        messages.success(request, f'Post “{title}” deleted.')
        return redirect('admin:growth-center-social')

    if action == 'sync_tracking':
        sync_post_tracking_urls(post)
        messages.success(request, 'Tracking URLs regenerated from the current campaign and UTM settings.')
        return redirect('admin:growth-center-social-post-detail', post.post_key)

    platform_key = request.POST.get('platform')
    entry = post.platform_entries.filter(platform=platform_key).first() if platform_key in PLATFORM_KEYS else None
    if not entry:
        messages.error(request, 'Select a valid platform for this action.')
        return redirect('admin:growth-center-social-post-detail', post.post_key)

    if action == 'mark_published':
        published_at = _parse_social_datetime(
            request.POST.get('published_date'),
            request.POST.get('published_time'),
        ) or timezone.now()
        entry.status = 'Published'
        entry.scheduled_at = None
        entry.published_at = published_at
        entry.published_by = request.user
        entry.publication_url = _safe_publication_url(request.POST.get('publication_url'))
        entry.save()
        published_entries = post.platform_entries.filter(status='Published')
        post.status = 'Published'
        post.published_at = max(published_entries.values_list('published_at', flat=True))
        post.save(update_fields=['status', 'published_at', 'updated_at'])
        messages.success(request, f'Marked “{post.title}” as published on {entry.get_platform_display()} by staff confirmation.')
        return redirect('admin:growth-center-social-post-detail', post.post_key)

    if action == 'mark_failed':
        entry.status = 'Failed'
        entry.save(update_fields=['status'])
        post.status = 'Failed'
        post.save(update_fields=['status', 'updated_at'])
        messages.success(request, f'Marked “{post.title}” as failed on {entry.get_platform_display()}.')
        return redirect('admin:growth-center-social-post-detail', post.post_key)

    if action == 'mark_ready':
        entry.status = 'Ready'
        entry.scheduled_at = None
        entry.published_at = None
        entry.save()
        post.status = 'Ready'
        post.published_at = None
        post.save(update_fields=['status', 'published_at', 'updated_at'])
        messages.success(request, f'Marked “{post.title}” ready for manual publishing.')
        return redirect('admin:growth-center-social-post-detail', post.post_key)

    if action == 'cancel_schedule':
        entry.status = 'Draft'
        entry.scheduled_at = None
        entry.save(update_fields=['status', 'scheduled_at'])
        if not post.platform_entries.filter(status='Scheduled').exists():
            post.scheduled_at = None
            post.status = 'Draft' if not post.platform_entries.filter(status='Published').exists() else 'Published'
            post.save(update_fields=['status', 'scheduled_at', 'updated_at'])
        messages.success(request, 'Schedule cancelled. The post remains available in the workflow.')
        return redirect('admin:growth-center-social-post-detail', post.post_key)

    if action == 'reschedule':
        scheduled_at = _parse_social_datetime(request.POST.get('scheduled_date'), request.POST.get('scheduled_time'))
        if not scheduled_at:
            messages.error(request, 'Provide a valid date and time to reschedule this platform.')
            return redirect('admin:growth-center-social-post-detail', post.post_key)
        entry.status = 'Scheduled'
        entry.scheduled_at = scheduled_at
        entry.published_at = None
        entry.save()
        post.status = 'Scheduled'
        post.scheduled_at = scheduled_at
        post.published_at = None
        post.save(update_fields=['status', 'scheduled_at', 'published_at', 'updated_at'])
        messages.success(request, 'Post reminder rescheduled. No platform was contacted.')
        return redirect('admin:growth-center-social-post-detail', post.post_key)

    messages.error(request, 'Unknown post action.')
    return redirect('admin:growth-center-social-post-detail', post.post_key)


@staff_member_required
@require_POST
def social_calendar_reschedule(request):
    post_key = request.POST.get('post_key')
    platform_key = request.POST.get('platform')
    scheduled_at = _parse_social_datetime(request.POST.get('date'), request.POST.get('time'))
    if platform_key not in PLATFORM_KEYS or not scheduled_at:
        return JsonResponse({'ok': False, 'error': 'Invalid platform or schedule.'}, status=400)

    entry = SocialPostPlatform.objects.filter(post__post_key=post_key, platform=platform_key).first()
    if not entry:
        return JsonResponse({'ok': False, 'error': 'Post platform entry not found.'}, status=404)

    entry.status = 'Scheduled'
    entry.scheduled_at = scheduled_at
    entry.save(update_fields=['status', 'scheduled_at'])
    post = entry.post
    post.status = 'Scheduled'
    post.scheduled_at = scheduled_at
    post.save(update_fields=['status', 'scheduled_at', 'updated_at'])
    return JsonResponse({
        'ok': True,
        'iso': scheduled_at.isoformat(),
        'label': timezone.localtime(scheduled_at).strftime('%d %b %H:%M'),
    })


@staff_member_required
@require_POST
def social_media_asset_action(request, asset_id):
    asset = get_object_or_404(SocialMediaAsset, id=asset_id)
    action = request.POST.get('action')
    if action == 'delete':
        if request.POST.get('confirm') != '1':
            messages.error(request, 'Confirm media deletion before removing it.')
            return redirect(f'{reverse("admin:growth-center-social")}?section=media')
        if asset.posts.filter(status='Published').exists():
            messages.error(request, 'This asset is used by a published post and cannot be deleted.')
            return redirect(f'{reverse("admin:growth-center-social")}?section=media')
        title = asset.title
        asset.delete()
        messages.success(request, f'Media asset “{title}” deleted.')
        return redirect(f'{reverse("admin:growth-center-social")}?section=media')
    messages.error(request, 'Unknown media action.')
    return redirect(f'{reverse("admin:growth-center-social")}?section=media')


@staff_member_required
def social_media_asset_file(request, asset_id):
    asset = get_object_or_404(SocialMediaAsset, id=asset_id)
    root = Path(settings.SOCIAL_MEDIA_ROOT).resolve()
    file_path = Path(asset.file.path).resolve()
    if root != file_path and root not in file_path.parents:
        raise Http404('File not found.')

    content_type = mimetypes.guess_type(file_path.name)[0] or asset.mime_type or 'application/octet-stream'
    download = request.GET.get('download') == '1'
    try:
        opened = asset.file.open('rb')
        return FileResponse(
            opened,
            content_type=content_type,
            as_attachment=download,
            filename=file_path.name if download else None,
        )
    except (OSError, ValueError):
        raise Http404('File not found.')


@staff_member_required
@require_POST
def social_template_action(request, template_key):
    template = get_object_or_404(SocialPostTemplate, template_key=template_key)
    if request.POST.get('action') == 'delete':
        if request.POST.get('confirm') != '1':
            messages.error(request, 'Confirm template deletion before removing it.')
            return redirect(f'{reverse("admin:growth-center-social")}?section=templates')
        name = template.name
        template.delete()
        messages.success(request, f'Template “{name}” deleted.')
        return redirect(f'{reverse("admin:growth-center-social")}?section=templates')
    messages.error(request, 'Unknown template action.')
    return redirect(f'{reverse("admin:growth-center-social")}?section=templates')


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
