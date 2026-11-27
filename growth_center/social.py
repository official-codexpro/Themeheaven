from calendar import monthrange
from datetime import datetime, timedelta

from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.urls import reverse
from django.utils import timezone

from .campaign_urls import build_campaign_url
from .models import AnalyticsSession, Campaign, PageView, SocialAccount, SocialMediaAsset, SocialPost, SocialPostPlatform, SocialPostTemplate
from .services import DATE_RANGES, GRAINS, _chart_series, _duration_display, _metrics, _range_dates
from .social_platforms import (
    CALENDAR_VIEWS,
    PLATFORM_BY_KEY,
    PLATFORM_KEYS,
    PLATFORM_SOURCE_HOSTS,
    PLATFORMS,
    POST_SORTS,
    SECTIONS,
    STATUSES,
    TEMPLATE_KINDS,
)
from .social_validators import reset_upload
from PIL import Image, UnidentifiedImageError

PAGE_SIZE = 15


def _parse_date(value):
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return timezone.localdate()


def _filters(request):
    section = request.GET.get('section', 'overview')
    if section not in dict(SECTIONS):
        section = 'overview'

    platform = request.GET.get('platform', '')
    if platform and platform not in PLATFORM_KEYS:
        platform = ''

    status = request.GET.get('status', 'all')
    if status not in {'all'} | {key for key, _label in STATUSES}:
        status = 'all'

    calendar_view = request.GET.get('view', 'month')
    if calendar_view not in dict(CALENDAR_VIEWS):
        calendar_view = 'month'

    sort = request.GET.get('sort', 'scheduled')
    if sort not in dict(POST_SORTS):
        sort = 'scheduled'

    direction = request.GET.get('dir', 'desc' if sort in {'scheduled', 'created'} else 'asc')
    if direction not in {'asc', 'desc'}:
        direction = 'asc'

    query = (request.GET.get('q') or '').strip()[:120]
    selected_date = _parse_date(request.GET.get('date'))
    return {
        'section': section,
        'platform': platform,
        'status': status,
        'calendar_view': calendar_view,
        'sort': sort,
        'direction': direction,
        'query': query,
        'selected_date': selected_date,
        'compare': request.GET.get('compare', '1') != '0',
    }


def build_post_tracking_url(post, platform_key=None):
    destination = post.destination_url or (post.campaign.destination_url if post.campaign else '')
    if not destination:
        return ''

    platform = PLATFORM_BY_KEY.get(platform_key or '', {})
    source = post.utm_source or platform_key or 'social'
    medium = post.utm_medium or ('organic_social' if platform_key else 'social')
    campaign = post.utm_campaign or (post.campaign.utm_campaign if post.campaign else post.post_key.lower())
    content = post.utm_content or post.post_key
    url, _error = build_campaign_url(
        destination,
        source,
        medium,
        campaign,
        post.utm_term,
        content,
    )
    return url


def sync_post_tracking_urls(post):
    for entry in post.platform_entries.all():
        url = build_post_tracking_url(post, entry.platform)
        if entry.tracking_url != url:
            entry.tracking_url = url
            entry.save(update_fields=['tracking_url'])


def _effective_schedule(entry):
    return entry.scheduled_at or entry.post.scheduled_at


def _account_rows():
    stored = {account.platform: account for account in SocialAccount.objects.all()}
    rows = []
    for platform in PLATFORMS:
        account = stored.get(platform['key'])
        status = account.status if account else 'Not Connected'
        connected = status == 'Connected'
        rows.append({
            'key': platform['key'],
            'label': platform['label'],
            'icon': platform['icon'],
            'status': status,
            'connected': connected,
            'account_name': account.account_name if connected and account else '—',
            'connected_at': account.connected_at if connected and account else None,
            'capabilities': account.capabilities if connected and account else '',
            'notes': account.notes if account else '',
            'home_url': platform['home_url'],
        })
    return rows


def _calendar_window(filters):
    selected = filters['selected_date']
    view = filters['calendar_view']
    if view == 'day':
        start = end = selected
    elif view == 'week':
        start = selected - timedelta(days=selected.weekday())
        end = start + timedelta(days=6)
    elif view == 'list':
        start = selected
        end = selected + timedelta(days=29)
    else:
        start = selected.replace(day=1)
        last_day = monthrange(selected.year, selected.month)[1]
        end = selected.replace(day=last_day)
        start -= timedelta(days=start.weekday())
        end += timedelta(days=6 - end.weekday())
    span = (end - start).days
    previous = start - timedelta(days=min(span + 1, 30 if view == 'list' else 7 if view == 'week' else 1 if view == 'day' else 30))
    next_date = end + timedelta(days=1)
    return start, end, previous, next_date


def _calendar_entries(filters):
    queryset = SocialPostPlatform.objects.select_related('post').exclude(status='Cancelled')
    if filters['platform']:
        queryset = queryset.filter(platform=filters['platform'])
    if filters['status'] != 'all':
        queryset = queryset.filter(status=filters['status'])
    else:
        queryset = queryset.filter(Q(scheduled_at__isnull=False) | Q(post__scheduled_at__isnull=False))

    entries = []
    for entry in queryset:
        scheduled = _effective_schedule(entry)
        if not scheduled:
            continue
        local = timezone.localtime(scheduled)
        post = entry.post
        query = filters['query'].lower()
        if query and query not in f'{post.title} {entry.content} {entry.platform}'.lower():
            continue
        entries.append({
            'entry': entry,
            'post': post,
            'platform': PLATFORM_BY_KEY.get(entry.platform, {'label': entry.platform, 'icon': 'share-2'}),
            'scheduled_at': scheduled,
            'date': local.date(),
            'time': local.strftime('%H:%M'),
            'content_type': post.get_content_type_display(),
            'detail_url': reverse('admin:growth-center-social-post-detail', args=[post.post_key]),
            'edit_url': reverse('admin:growth-center-social-post-edit', args=[post.post_key]),
        })
    return entries


def build_calendar_context(request, filters):
    start, end, previous, next_date = _calendar_window(filters)
    entries = _calendar_entries(filters)
    visible = [row for row in entries if start <= row['date'] <= end]
    days = []
    current = start
    while current <= end:
        days.append({
            'date': current,
            'iso': current.isoformat(),
            'in_period': not (filters['calendar_view'] == 'month' and current.month != filters['selected_date'].month),
            'is_today': current == timezone.localdate(),
            'entries': [row for row in visible if row['date'] == current],
            'create_url': (
                reverse('admin:growth-center-social-post-create')
                + f'?date={current.isoformat()}&time=09:00'
            ),
        })
        current += timedelta(days=1)

    groups = []
    for row in sorted(visible, key=lambda item: (item['date'], item['time'])):
        if not groups or groups[-1]['date'] != row['date']:
            groups.append({'date': row['date'], 'entries': []})
        groups[-1]['entries'].append(row)

    return {
        'calendar_start': start,
        'calendar_end': end,
        'calendar_previous': previous.isoformat(),
        'calendar_next': next_date.isoformat(),
        'calendar_today': timezone.localdate().isoformat(),
        'calendar_days': days,
        'calendar_groups': groups,
        'calendar_entry_count': len(visible),
        'calendar_weekdays': ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
    }


def _post_rows(queryset):
    rows = []
    for post in queryset:
        entries = list(post.platform_entries.all())
        scheduled = post.scheduled_at or min((entry.scheduled_at for entry in entries if entry.scheduled_at), default=None)
        rows.append({
            'post': post,
            'platforms': [PLATFORM_BY_KEY.get(entry.platform, {'label': entry.platform}) for entry in entries],
            'media_count': post.media.count(),
            'scheduled_at': scheduled,
            'detail_url': reverse('admin:growth-center-social-post-detail', args=[post.post_key]),
            'edit_url': reverse('admin:growth-center-social-post-edit', args=[post.post_key]),
        })
    return rows


def _performance(request, filters):
    range_info = _range_dates(request)
    social_query = Q(source_category='Social')
    social_query |= Q(utm_medium__in=['social', 'social_media', 'organic_social', 'paid_social'])
    social_query |= Q(utm_source__in=PLATFORM_KEYS)
    for hosts in PLATFORM_SOURCE_HOSTS.values():
        for host in hosts:
            social_query |= Q(referrer_host__icontains=host) | Q(utm_source__icontains=host)

    sessions = AnalyticsSession.objects.filter(
        social_query,
        started_at__gte=range_info['start_dt'],
        started_at__lt=range_info['end_dt'],
    )
    pageviews = PageView.objects.filter(
        session__in=sessions,
        viewed_at__gte=range_info['start_dt'],
        viewed_at__lt=range_info['end_dt'],
    )
    metrics = _metrics(sessions, pageviews)
    platform_rows = []
    for platform in PLATFORMS:
        hosts = PLATFORM_SOURCE_HOSTS.get(platform['key'], ())
        query = Q(utm_source__iexact=platform['key'])
        for host in hosts:
            query |= Q(utm_source__icontains=host) | Q(referrer_host__icontains=host)
        count = sessions.filter(query).count()
        platform_rows.append({
            'key': platform['key'],
            'label': platform['label'],
            'icon': platform['icon'],
            'visits': count,
        })

    post_codes = list(SocialPost.objects.values_list('post_key', flat=True))
    post_rows = list(
        sessions.filter(utm_content__in=post_codes)
        .values('utm_content')
        .annotate(visits=Count('id'), visitors=Count('visitor_id', distinct=True))
        .order_by('-visits')[:12]
    )
    post_map = {post.post_key: post for post in SocialPost.objects.filter(post_key__in=[row['utm_content'] for row in post_rows])}
    for row in post_rows:
        post = post_map.get(row['utm_content'])
        row['title'] = post.title if post else row['utm_content']
        row['url'] = reverse('admin:growth-center-social-post-detail', args=[row['utm_content']]) if post else ''

    campaign_codes = list(Campaign.objects.values_list('utm_campaign', flat=True))
    campaign_rows = list(
        sessions.filter(utm_campaign__in=campaign_codes)
        .values('utm_campaign')
        .annotate(visits=Count('id'))
        .order_by('-visits')[:12]
    )
    campaign_map = {campaign.utm_campaign: campaign for campaign in Campaign.objects.filter(utm_campaign__in=[row['utm_campaign'] for row in campaign_rows])}
    for row in campaign_rows:
        campaign = campaign_map.get(row['utm_campaign'])
        row['name'] = campaign.name if campaign else row['utm_campaign']
        row['url'] = reverse('admin:growth-center-campaign-detail', args=[campaign.campaign_key]) if campaign else ''

    return {
        'range': range_info,
        'range_choices': DATE_RANGES,
        'grain': request.GET.get('grain', 'daily') if request.GET.get('grain') in dict(GRAINS) else 'daily',
        'grain_choices': GRAINS,
        'kpis': {
            'visits': metrics['total_sessions'],
            'visitors': metrics['unique_visitors'],
            'page_views': metrics['page_views'],
            'avg_duration': _duration_display(metrics['avg_duration_seconds']),
            'bounce_rate': metrics['bounce_rate'],
        },
        'charts': _chart_series(sessions, pageviews, range_info, 'daily'),
        'platform_rows': platform_rows,
        'post_rows': post_rows,
        'campaign_rows': campaign_rows,
        'has_web_data': bool(metrics['total_sessions'] or metrics['page_views']),
        'native_metrics_available': False,
    }


def build_social_context(request, post_form=None, asset_form=None, template_form=None):
    filters = _filters(request)
    posts = SocialPost.objects.select_related('campaign').prefetch_related('media', 'platform_entries')
    entries = SocialPostPlatform.objects.select_related('post')

    query = filters['query'].lower()
    post_queryset = posts
    if filters['platform']:
        post_queryset = post_queryset.filter(platform_entries__platform=filters['platform']).distinct()
    if filters['status'] != 'all':
        post_queryset = post_queryset.filter(status=filters['status'])
    if query:
        post_queryset = post_queryset.filter(Q(title__icontains=query) | Q(content__icontains=query) | Q(hashtags__icontains=query))

    order_field = {
        'scheduled': 'scheduled_at',
        'created': 'created_at',
        'title': 'title',
        'status': 'status',
    }[filters['sort']]
    post_queryset = post_queryset.order_by(f'{"-" if filters["direction"] == "desc" else ""}{order_field}')
    post_page = Paginator(_post_rows(post_queryset), PAGE_SIZE).get_page(request.GET.get('page'))

    asset_queryset = SocialMediaAsset.objects.all()
    if query:
        asset_queryset = asset_queryset.filter(Q(title__icontains=query) | Q(alt_text__icontains=query))
    assets = Paginator(asset_queryset, PAGE_SIZE).get_page(request.GET.get('media_page'))

    templates = SocialPostTemplate.objects.all()
    if filters['platform']:
        templates = templates.filter(Q(platform=filters['platform']) | Q(platform=''))
    if query:
        templates = templates.filter(Q(name__icontains=query) | Q(content__icontains=query))

    now = timezone.now()
    upcoming = [
        {
            'entry': entry,
            'post': entry.post,
            'platform': PLATFORM_BY_KEY.get(entry.platform, {'label': entry.platform}),
            'scheduled_at': _effective_schedule(entry),
            'detail_url': reverse('admin:growth-center-social-post-detail', args=[entry.post.post_key]),
        }
        for entry in entries.filter(
            status='Scheduled',
        ).filter(Q(scheduled_at__gte=now) | Q(post__scheduled_at__gte=now)).select_related('post').order_by('scheduled_at')[:8]
    ]
    recent_published = [
        {
            'entry': entry,
            'post': entry.post,
            'platform': PLATFORM_BY_KEY.get(entry.platform, {'label': entry.platform}),
            'detail_url': reverse('admin:growth-center-social-post-detail', args=[entry.post.post_key]),
        }
        for entry in entries.filter(status='Published').select_related('post').order_by('-published_at')[:8]
    ]

    today = timezone.localdate()
    accounts = _account_rows()
    connected_count = sum(1 for account in accounts if account['connected'])

    query_params = request.GET.copy()
    query_params.pop('page', None)
    query_params.pop('media_page', None)

    context = {
        'title': 'Social Media Manager',
        'sections': SECTIONS,
        'section': filters['section'],
        'filters': filters,
        'statuses': STATUSES,
        'platforms': PLATFORMS,
        'calendar_views': CALENDAR_VIEWS,
        'sorts': POST_SORTS,
        'kinds': TEMPLATE_KINDS,
        'query': filters['query'],
        'platform': filters['platform'],
        'status': filters['status'],
        'sort': filters['sort'],
        'sort_direction': filters['direction'],
        'view': filters['calendar_view'],
        'selected_date': filters['selected_date'],
        'compare': filters['compare'],
        'query_params': query_params.urlencode(),
        'post_form': post_form,
        'asset_form': asset_form,
        'template_form': template_form,
        'posts': post_page,
        'recent_posts': _post_rows(posts.order_by('-created_at')[:6]),
        'assets': assets,
        'templates': list(templates),
        'accounts': accounts,
        'connected_count': connected_count,
        'total_posts': posts.count(),
        'published_posts': posts.filter(status='Published').count(),
        'scheduled_posts': posts.filter(status='Scheduled').count(),
        'draft_posts': posts.filter(status='Draft').count(),
        'posts_this_month': posts.filter(created_at__date__gte=today.replace(day=1)).count(),
        'upcoming_posts': upcoming,
        'recent_published': recent_published,
        'summary_text': f'{posts.count()} posts in the content workflow. Scheduling is a reminder workflow unless a platform account is genuinely connected.',
    }
    context.update(build_calendar_context(request, filters))
    context.update(_performance(request, filters))
    return context


def build_post_detail_context(request, post):
    sync_post_tracking_urls(post)
    media = []
    for asset in post.media.all():
        media.append({
            'asset': asset,
            'preview_url': reverse('admin:growth-center-social-media-asset-file', args=[asset.id]),
            'download_url': reverse('admin:growth-center-social-media-asset-file', args=[asset.id]) + '?download=1',
        })

    platform_rows = []
    for entry in post.platform_entries.select_related('published_by').all():
        platform = PLATFORM_BY_KEY.get(entry.platform, {'label': entry.platform, 'limit': 0, 'home_url': '', 'icon': 'share-2'})
        platform_rows.append({
            'entry': entry,
            'platform': platform,
            'copy_content': entry.content or post.content,
            'scheduled_at': _effective_schedule(entry),
            'action_url': reverse('admin:growth-center-social-post-action', args=[post.post_key]),
        })

    return {
        'title': post.title,
        'post': post,
        'platform_rows': platform_rows,
        'media_rows': media,
        'statuses': STATUSES,
        'hashtags': [tag.strip() for tag in post.hashtags.replace(',', '\n').splitlines() if tag.strip()],
        'summary_text': 'Manual publishing workflow. Posts are never marked published automatically.',
    }


def build_asset_preview_metadata(asset):
    if asset.media_type != 'Image' or not asset.file:
        return asset.width, asset.height
    if asset.width and asset.height:
        return asset.width, asset.height
    try:
        position = asset.file.tell()
        image = Image.open(asset.file)
        size = image.size
        reset_upload(asset.file)
        asset.file.seek(position)
        return size
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return None, None
